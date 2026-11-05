# Redactor engineering conventions

## Scope

This repository implements the PHI pseudonymization assignment in `ASSIGNMENT.pdf`.
Project-specific instructions for other applications in parent directories do not
define Redactor's product, dependencies, milestones, or architecture.

Build only the current agreed milestone. The initial milestone is a local SQLite
queue and checkpoint-state persistence. Do not implement the runtime, coordinator,
worker scheduling, file processing, or automatic recovery in this bootstrap.
The current file-storage chunk adds registration and explicit artifact helpers;
checkpoint save/resume and coordinator execution remain separate milestones.

## Code

- Write functional, composable, reusable, readable Python with explicit inputs and
  outputs, descriptive names, type annotations, and proper spacing.
- Keep business logic in functions. Use declarative, frozen Pydantic models for
  structured data. Do not introduce manager, service, repository, or factory
  classes when ordinary functions suffice.
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

- SQLite is the authoritative queue and execution ledger. Local worker messages
  are disposable delivery, not the durable source of truth.
- Keep schema changes in numbered SQL files under `src/redactor/migrations/`.
  That package owns discovery, filename validation, and execution, and derives
  the schema version from its SQL files. Keep migration naming constants grouped
  in `utils/constants.py`. Do not maintain a shared migration registry.
  Append migrations instead of rewriting applied files. Migration SQL preserves
  historical values; it must not interpolate today's application constants.
- Coordinator-related code belongs in `src/redactor/coordinator/`. The planned
  coordinator will own database writes and the state-directory lock. That runtime
  will be implemented separately. Keep write transactions short; do not hold them
  while parsing, hashing files, or calling a model. Use process-local connections
  and spawn workers rather than inheriting the coordinator's connection or lock.
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
  Publication requires the independent verifier in a later milestone.
- Do not promise exactly-once model billing without an endpoint contract that
  supports it. Persist completed responses and account for uncertain requests.

## Agent code, when introduced

- Keep agent-specific implementations under `src/redactor/agents/<agent_name>/`.
- Separate prompts, structured output schemas, runtime/transport, and the agent's
  orchestration logic. Name modules plainly, for example `prompts.py`,
  `schemas.py`, and `run.py`.
- Share runtime, validation, caching, and accounting only where there are actual
  common call sites. Keep provider details out of prompt and domain logic.
- Version prompts and validate structured outputs. Keep secrets in environment
  variables. Never call a paid model endpoint in tests.
- Add directories and abstractions when implemented; do not create empty research,
  chat, or other agents to anticipate future requirements.

## Tests and milestones

- Add meaningful tests with each significant behavior and discovered regression.
  Test failures, invalid state transitions, stale attempts, and actual subprocess
  interruption, not just the happy path.
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
