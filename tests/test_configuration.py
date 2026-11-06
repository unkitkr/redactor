"""Configuration integration: TOML, environment precedence and safe failures."""

import base64
from pathlib import Path

import pytest

from redactor.configuration import (
    load_settings,
    processing_fingerprint,
    read_mapping_key,
)
from redactor.utils.errors import ERROR_CONFIGURATION, ERROR_MAPPING_KEY


def test_configuration_resolves_environment_without_persisting_secrets(
    tmp_path: Path,
) -> None:
    configuration = tmp_path / "settings.toml"
    configuration.write_text(
        '[remote]\nenabled = true\nmodel = "detector"\n'
        '[verification]\njudge_model = "independent-judge"\n'
    )
    settings = load_settings(configuration, environment={})
    offline = load_settings(
        configuration, environment={"LLM_ENABLED": "0", "LLM_API_KEY": "secret"}
    )
    assert not offline.remote.enabled
    assert offline.verification.judge_model == "independent-judge"
    assert "secret" not in offline.model_dump_json()
    assert processing_fingerprint(settings) == processing_fingerprint(offline)

    changed = load_settings(configuration, environment={"LLM_MODEL": "different"})
    assert processing_fingerprint(changed) != processing_fingerprint(settings)


def test_configuration_rejects_unknown_settings_and_bad_keys(tmp_path: Path) -> None:
    configuration = tmp_path / "settings.toml"
    configuration.write_text("[verification]\nenabled = false\n")
    with pytest.raises(ValueError, match=ERROR_CONFIGURATION):
        load_settings(configuration, environment={})
    with pytest.raises(ValueError, match=ERROR_MAPPING_KEY):
        read_mapping_key({})
    expected = bytes(range(32))
    assert (
        read_mapping_key({"REDACTOR_SECRET_KEY": base64.b64encode(expected).decode()})
        == expected
    )
