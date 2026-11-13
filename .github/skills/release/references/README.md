# Release Skill References

## Usage

From chat:

- `/release 1.6.1`

From terminal (manual equivalent):

- `pwsh ./.github/skills/release/scripts/release.ps1 -Version 1.6.1`

Validation is mandatory before release:

- Chat workflow must run agent `dev-python-validation` and continue only on final `SUCCESS`.
- Script workflow always runs `ruff`, `mypy`, and `pytest` before version bump/build/tag/publish.

## Expected .env keys

Supported credentials patterns:

1. `TWINE_USERNAME` and `TWINE_PASSWORD`
2. `PYPI_USERNAME` and `PYPI_PASSWORD`
3. `PYPI_TOKEN` (token auth with username set to `__token__`)

Optional key:

- `TWINE_REPOSITORY_URL` for custom repository target

## Notes

- Script fails fast on dirty git tree by design.
- Script enforces branch `main` by default.
- Use `-AllowNonMain` only for exceptional workflows.
- Script has no tests-skip mode: failing tests block release.
