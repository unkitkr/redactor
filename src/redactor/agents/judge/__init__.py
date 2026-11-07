"""Hosted judging of saved-output evidence after local verification checks.

The judge is an additional reviewer, never an authority over local checks.
It runs only through the shared provider boundary, so LLM_ENABLED=0, a blank
judge model, a closed judge switch or an exhausted budget disables it with
zero remote calls. Its findings can only add failures: a leak, likely-leak or
unsure finding fails closed, and no judge result can clear a failed local
check, missing coverage or an unknown-coverage verdict. Judge errors,
timeouts, garbage output or unavailability degrade to the local-only verdict
with a recorded reason, and the pipeline keeps working without the model.

Integration contract. Expected call site: workers/verify.py, after the local
checks complete and before conclude_verification.

    residual: list[ResidualCheck] = []
    verify_text_changes(..., collect=residual.append)  # existing collector
    frames = saved image frames when settings.verification.judge_vision
    evidence = build_judge_evidence(residual, images=frames)
    outcome = judge_saved_evidence(
        connection,
        task,
        evidence,
        f"judge:{task.input_sha256}",
        settings=settings,
        mapping_key=mapping_key,
    )
    application = apply_judge_findings(checks, outcome)
    verdict = conclude_verification(
        context, producer.task_id, artifact, application.checks
    )
    # Record application.degradation in verdict or report data; it never
    # changes the verdict itself. Also record evidence.omitted_items and
    # evidence.omitted_images when coverage was bounded by policy caps.

Signatures:

    build_judge_evidence(
        checks: Sequence[ResidualCheck],
        images: Sequence[tuple[bytes, tuple[int, int], str]] = (),
    ) -> JudgeEvidence
    judge_saved_evidence(
        connection: sqlite3.Connection,
        claimed: Task,
        evidence: JudgeEvidence,
        context_id: str,
        *,
        settings: PipelineSettings,
        mapping_key: bytes,
        environment: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> JudgeOutcome
    apply_judge_findings(
        checks: Sequence[VerificationCheck], outcome: JudgeOutcome
    ) -> JudgeApplication

Each image is a (content, (width, height), media_type) tuple of one saved
frame; re-encode frames to PNG when the endpoint rejects the saved format,
which degrades with a recorded reason instead of failing the run. One bounded
request is sent per call, so call judge_saved_evidence once per verification
batch to judge larger files; replay is keyed per request.
"""
