"""Real HTTP requests expose only public measurements and committed metadata."""

import hashlib
import json
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Thread
from wsgiref.simple_server import make_server

import httpx
from PIL import Image

from redactor.monitoring.server import create_application
from redactor.persistence.database import open_database
from redactor.persistence.queue.tasks import enqueue_task
from redactor.schemas.persistence import TaskSpec
from redactor.utils.constants import MONITOR_STATIC_FILES


@contextmanager
def dashboard(state: Path, benchmarks: Path, images: Path) -> Generator[httpx.Client]:
    application = create_application(state, benchmarks, images)
    with make_server("127.0.0.1", 0, application) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
            ) as client:
                yield client
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()


def test_dashboard_reads_wal_and_serves_only_allowlisted_assets(tmp_path: Path) -> None:
    state = tmp_path / "state"
    benchmarks = Path(__file__).resolve().parents[1] / "benchmarks"
    with closing(open_database(state)) as connection:
        enqueue_task(
            connection,
            TaskSpec(
                task_id="a" * 64,
                input_path=Path("/private/Patient Alice Stone.csv"),
                input_sha256="b" * 64,
                input_size=10,
                step="inspect",
                processing_version="c" * 64,
                temporary_directory=Path("/private/secret"),
            ),
        )
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE tasks SET status = 'running'")
        with dashboard(state, benchmarks, tmp_path / "images") as client:
            response = client.get("/")
            assert response.status_code == 200
            assert "Pipeline monitor" in response.text
            assert "default-src 'self'" in response.headers["content-security-policy"]
            for name, content_type in MONITOR_STATIC_FILES:
                asset = client.get(f"/static/{name}")
                assert asset.status_code == 200
                assert asset.headers["content-type"] == content_type
            response = client.get("/api/queue")
            assert response.json()["tasks"][0]["status"] == "pending"
            assert "Patient" not in response.text and "/private" not in response.text
            assert client.get("/api/queue").json() == response.json()
            measurements = client.get("/api/benchmarks").json()
            assert measurements["status"] == "ready"
            assert {report["kind"] for report in measurements["reports"]} == {
                "text",
                "ocr",
                "throughput",
                "diagnostic",
            }
            assert measurements["images"] == []
            head = client.head("/api/queue")
            assert head.status_code == 200 and head.content == b""
            assert head.headers["content-length"] == response.headers["content-length"]
            for route in ("/state/queue.sqlite3", "/.env", "/static/%2e%2e/.env"):
                assert client.get(route).status_code == 404
            assert client.post("/api/queue").status_code == 405
            assert client.get("/api/queue?run=private").status_code == 400
            assert client.get("/api/queue?path=/private").status_code == 400
            assert (
                client.get(f"/api/queue?run={'a' * 64}&run={'b' * 64}").status_code
                == 400
            )
            assert client.get("/" + "x" * 300).status_code == 414
        connection.rollback()
        assert connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def test_reference_images_are_confined_and_missing_state_is_not_created(
    tmp_path: Path,
) -> None:
    state, images, benchmarks = (
        tmp_path / name for name in ("state", "images", "benchmarks")
    )
    images.mkdir()
    (benchmarks / "results").mkdir(parents=True)
    case_id = "synthetic-1-clean"
    image = images / f"{case_id}.png"
    Image.new("RGB", (1, 1)).save(image)
    manifest = json.dumps(
        [{"case_id": case_id, "image": "/private/ignored.png"}]
    ).encode()
    (images / "manifest.json").write_bytes(manifest)
    source = Path(__file__).resolve().parents[1] / "benchmarks/results/ppocr-en.json"
    report = json.loads(source.read_bytes())
    report["corpus_sha256"] = hashlib.sha256(manifest).hexdigest()
    (benchmarks / "results/ppocr-en.json").write_text(json.dumps(report))
    with dashboard(state, benchmarks, images) as client:
        assert client.get("/api/queue").json()["status"] == "missing"
        assert not state.exists()
        gallery = client.get("/api/benchmarks").json()["images"]
        assert len(gallery) == 1
        assert client.get(gallery[0]["url"]).content == image.read_bytes()
        private = tmp_path / "private.png"
        private.write_bytes(image.read_bytes())
        image.unlink()
        image.symlink_to(private)
        assert client.get(gallery[0]["url"]).status_code == 404
        assert client.get("/benchmark-images/unknown.png").status_code == 404
