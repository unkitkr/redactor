# Redactor engineering conventions

## Scope

This repository implements the PHI pseudonymization assignment in `ASSIGNMENT.pdf`.
Project-specific instructions for other applications in parent directories do not
define Redactor's product, dependencies, milestones, or architecture.

Implement the agreed pipeline in small, tested milestones: durable contracts and
execution, model adapters, a complete CSV path, native-format adapters, and measured
container validation. Never report a placeholder or an incomplete verifier as a
working clinical publication path.

## Decision record

- Keep `notes.md` as a short, evaluator-facing architecture and decision log.
  Read it before making architectural choices or selecting models and dependencies.
- Group concise, one-line bullets under `Architecture`, `Stack`, and `Choices`.
  Record system design, selected technologies, and policy decisions respectively.
  Include assumptions that materially affect correctness. Use natural, neutral language
  without first-person wording, introductory prose, or em dashes.
- Record high-level decisions already made, with a brief reason where useful.
  Keep coding principles, style rules, module layouts, development procedures,
  task lists, undecided proposals, and model shortlists out of `notes.md`.
- Include relevant known limitations and only tradeoffs deliberately accepted.
  Distinguish a chosen design from implemented capability without adding a roadmap.
- Update the notes when an architectural decision is made or changes. Replace
  superseded points so the log stays short and accurate.
- Keep coding conventions in this file. Use no em dashes here either, and never
  include secrets, raw PHI, or prompts containing input data in either document.
- Keep exploratory research artifacts out of commits. Before any push, inspect
  outgoing history as well as the current tree so unwanted research is not published.

## Code

- Write functional, composable, reusable, readable Python with explicit inputs and
  outputs, descriptive names, type annotations, and proper spacing.
- Keep business logic in functions. Use declarative, frozen Pydantic models for
  structured data. Do not introduce manager, service, repository, or factory
  classes. Worker-facing persistence APIs must also use functions, not client
  classes. Keep transaction and state-transition logic in the queue functions.
- Introduce an abstraction only when it solves a concrete problem. Reuse shared
  behavior without creating a framework or splitting cohesive code unnecessarily.
- Group code by domain and responsibility. Keep domain-specific logic with the
  package that owns it; reserve utility functions for shared functionality.
  Centralize constants as described below. Do not create broad registries or move
  unrelated code together merely because it uses the same mechanism.
- Keep mutable state local and pass dependencies explicitly. No mutable global
  variables, global connections, clients, registries, or import-time I/O.
- Put named constants in `src/redactor/utils/constants.py`, grouped by domain or
  responsibility within that file. Do not create separate domain constants files.
  Import constants where needed. Keep error codes and their allowed-value lists
  in `utils/errors.py`.
  Do not scatter magic status strings, error codes, filenames, timeouts,
  limits, or configuration
  defaults through implementation code. SQL syntax, docstrings, and illustrative
  test data may remain literal where that improves readability.
- Prefer standard-library implementations unless a dependency removes meaningful
  complexity. Support Python 3.11 and later on Linux; development also uses macOS.
- Use `pathlib.Path`, small modules with clear responsibilities, and immutable
  inputs. Never modify the supplied input files.
- Keep shared data schemas in `src/redactor/schemas/`, grouped by responsibility
  (for example, `persistence.py` for queue and checkpoint records).
- Do not hide errors. Preserve structured, PHI-free failure codes. Do not place
  raw clinical content, identifiers, model prompts, or secrets in logs or reports.

## Persistence and execution

- Group persistence by responsibility: `queue/` for task state and scheduling,
  `files/` for registration, artifacts, checkpoints, results, and publication,
  `runs/` for frozen inventories and manifests, and `models/` for request accounting
  and replay. Keep connection setup and the functional worker API at the root.
- SQLite is the authoritative queue and execution ledger. Local worker messages
  are disposable delivery, not the durable source of truth.
- Keep schema changes in numbered SQL files under `src/redactor/migrations/`.
  That package owns discovery, filename validation, and execution, and derives
  the schema version from its SQL files. Keep migration naming constants grouped
  in `utils/constants.py`. Do not maintain a shared migration registry.
  Append migrations instead of rewriting applied files. Migration SQL preserves
  historical values; it must not interpolate today's application constants.
- Coordinator-related code belongs in `src/redactor/coordinator/`. Keep its files
  small and split startup, inventory, ownership, and worker supervision by their
  responsibilities. Worker execution belongs in `src/redactor/workers/`.
- The coordinator owns startup and recovery. Workers claim and complete tasks
  through their own SQLite connections. Keep write transactions short; do not
  hold them while parsing, hashing files, or calling a model.
- Start workers in fresh interpreters; never inherit a database connection.
  Explicitly inherit only the run-lock descriptor so recovery remains blocked
  while any worker from the previous run survives. Release that lock by closing
  descriptors, never by explicitly unlocking or unlinking the lock file.
- Keep large artifacts on the private filesystem and references in SQLite.
- Persist artifact bytes before committing their checkpoint. Recover explicitly
  across the filesystem/database boundary; do not assume one atomic transaction
  covers both resources.
- Fence stale attempts, keep input/configuration identities stable, and make
  retries repeatable. Accept one logical result even when execution is repeated.
- Stream large files with bounded memory. Parser adapters must provide actual
  complete-record boundaries; buffered stream positions are not automatically
  safe CSV or JSON resume positions.
- A completed staged artifact is not a verified or published clinical file.
  Publication requires an independent verdict bound to the exact saved bytes,
  original input, identity snapshot, and verification policy. Unknown coverage,
  failed checks, and unresolved verifier errors prevent publication.
- Verification always runs. The external-model disable switch also disables remote
  judging. Judge findings need validated evidence and cannot override failed local
  checks or missing coverage. Never globally allowlist surrogate strings.
- Do not promise exactly-once model billing without an endpoint contract that
  supports it. Persist completed responses and account for uncertain requests.

## Agent code, when introduced

- Keep agent-specific implementations under `src/redactor/agents/<agent_name>/`.
- Separate prompts, runtime/transport, and the agent's orchestration logic. Keep
  structured output schemas in the shared `schemas/` package. Name modules plainly.
- Share runtime, validation, caching, and accounting only where there are actual
  common call sites. Keep provider details out of prompt and domain logic.
- Version prompts and validate structured outputs. Keep secrets in environment
  variables. Never call a paid model endpoint in tests.
- Add directories and abstractions when implemented; do not create empty research,
  chat, or other agents to anticipate future requirements.

## Tests and milestones

- Prefer a small number of meaningful integration tests using real files, SQLite,
  and subprocesses. Cover related behavior together rather than adding a test for
  every function. Include stale attempts, interruption, and deliberately broken
  outputs that the verifier must reject; avoid repetitive implementation tests.
- Annotate test parameters and return types as well as production functions.
  Ruff enforces annotation presence; a type checker validates their use.
- Run focused tests during implementation and the full applicable suite before
  every implementation milestone commit. Check formatting, linting, and types.
- Prefer real temporary files and SQLite databases over mocks of internal logic.
  Use controlled substitutes only at external boundaries.
- Commit each completed file or cohesive, tested chunk of related work so it can
  be rolled back independently. Do not accumulate unrelated changes into a large
  milestone commit. Use semantic messages such as
  `feat(queue): persist task claims and recovery` or
  `fix(durability): reject truncated checkpoint artifacts`.
- Never commit secrets, private runtime state, virtual environments, or generated
  benchmark files. The supplied synthetic inputs are assignment fixtures.
- Preserve user changes. Do not rewrite commit history for presentation.
- If a decision cannot be made pragmatically from the assignment and conversation,
  stop implementation and ask the user. Explain the concrete unresolved choice.

## Standard checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest -q
uv run pytest --cov=redactor --cov-report=term-missing
```
