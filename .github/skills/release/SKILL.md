---
name: release
description: 'Automate release workflow for this project. Use when user types /release <version>, asks to bump package version, create git tag, create GitHub release, and publish to PyPI using credentials from .env.'
argument-hint: '<version>'
user-invocable: true
---

# Release Skill

Automates a full release for this repository from a single version argument.

## Triggers

- `/release <version>`
- "prepare release"
- "bump version + tag + GitHub release + publish PyPI"

## Behavior

Given `<version>`, this skill must:

1. Run validation agent gate (mandatory):
- Launch agent `dev-python-validation` first.
- Continue only if the agent final outcome is exactly `SUCCESS`.
- If outcome is `FAILED` or unclear, stop immediately and do not bump version, tag, create GitHub release, or publish to PyPI.

1. Update package version in:
- `pyproject.toml` (`[project].version`)
- `src/sive.egg-info/PKG-INFO` (`Version: ...`)

2. Validate and prepare release:
- Ensure git working tree is clean before starting.
- Ensure branch is `main` by default (fail fast otherwise).
- Run release validation gate commands (`ruff`, `mypy`, `pytest`) with no bypass.

3. Build and publish:
- Build artifacts with `python -m build`.
- Load PyPI credentials from `.env` without printing secrets.
- Upload using `python -m twine upload dist/*`.

4. Git and GitHub release:
- Commit version bump (`chore(release): v<version>`).
- Create annotated tag `v<version>`.
- Push branch and tag.
- Create GitHub release with generated notes.

## Command to run

Use the helper script:

`pwsh ./.github/skills/release/scripts/release.ps1 -Version <version>`

Optional flags:

- `-SkipPublish`
- `-SkipGitHubRelease`
- `-AllowNonMain`

## Credentials expected in .env

Any one of these patterns is supported:

- `TWINE_USERNAME` + `TWINE_PASSWORD`
- `PYPI_USERNAME` + `PYPI_PASSWORD`
- `PYPI_TOKEN` (mapped to `TWINE_USERNAME=__token__`)

Optional:

- `TWINE_REPOSITORY_URL`

## Safety rules

- Never print or echo secret values.
- Stop immediately on first failure.
- Do not continue to tag/publish if validation/build fails.
- If tag already exists, abort and ask user whether to delete/retry.
