# Contributing to NyayaSetu

Thank you for helping make legal help accessible. Please read `CLAUDE.md` (project rules) and
`docs/LEGAL_SAFETY.md` first — they apply to human and AI contributors alike.

## Setup
See `README.md` for local setup (SQLite) or `docker compose up --build` for the full stack.

## Workflow
1. Branch from `main`.
2. Make the change with tests. For agent or legal changes, include tests for incomplete, conflicting
   and adversarial input.
3. Run all checks:
   ```bash
   cd backend && pytest -q && ruff check app tests alembic && mypy
   cd frontend && npm run lint && npm run typecheck && npm test && npm run build
   ```
4. Update the matching `docs/*.md`, `docs/IMPLEMENTATION_STATUS.md`, `docs/KNOWN_LIMITATIONS.md`,
   `docs/API_SPECIFICATION.md` (if the API changed), `.env.example` and `CHANGELOG.md`.
5. Open a pull request describing behaviour changes and how you verified them.

## Legal content
- Add sources only from official publishers, via the manifest, with metadata read from the document.
- Never encode a legal rule without citing the provision and adding a grounding test.
- New templates or rules need review by a qualified legal professional before release.

## UI text
All strings go through the i18n dictionaries (`frontend/src/lib/i18n/en.ts` and `hi.ts`). Keep
Hindi natural and simple; mark translations of law as explanations, not authoritative text.

## Data
Never commit real personal data, case details or credentials. Test fixtures must be clearly synthetic.

## Security issues
Do not open public issues for vulnerabilities; contact the maintainers privately.
