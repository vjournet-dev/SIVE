---
name: release-version
description: 'Release a new version of sive. Use when the user types /release <version>, asks to bump the package version, tag a release, or publish to PyPI. Bumps the version, pushes a v<version> tag, and monitors the "Publish to PyPI" GitHub Actions workflow that builds, publishes to PyPI, and creates the GitHub release.'
argument-hint: '<version>'
user-invocable: true
---

# Release Version Skill

Releases `<version>` by pushing a `v<version>` git tag. Publishing is done exclusively by the
GitHub Actions workflow `.github/workflows/publish-pypi.yml` (trusted publishing, no local
credentials). The workflow builds the distributions, uploads them to PyPI, and creates the
GitHub release with generated notes and `dist/*` attached.

Never build or upload to PyPI locally, never use `twine`, and never ask for PyPI tokens.

## Triggers

- `/release <version>`
- "release version X.Y.Z", "bump version and publish", "publish to PyPI"

## Steps

Stop immediately on the first required-step failure and report it. Do not continue to later steps.
Optional E2E diagnostics are not a release gate; report their results separately.

### 1. Preconditions

- `<version>` must be a PEP 440 version without a `v` prefix (for example `1.2.3`, `1.2.3rc1`).
  If missing or invalid, ask the user for it.
- `<version>` must be greater than the current `[project].version` in `pyproject.toml`.
- Current branch must be `main` (`git branch --show-current`); otherwise stop and ask.
- Working tree must be clean (`git status --porcelain` empty); otherwise stop and ask.
- Local `main` must be up to date: `git fetch origin --tags` then
  `git status -sb` must not show `behind`.
- Tag must not exist locally or remotely:
  `git tag -l v<version>` and `git ls-remote --tags origin v<version>` must both be empty.
  If it exists, stop and ask the user how to proceed. Never delete or move tags on your own.
- `gh auth status` must succeed.

### 2. Validation gate (mandatory)

- Run these versioned repository gates sequentially, stopping on the first nonzero exit code:
  - `python -m ruff check src tests`
  - `python -m mypy src`
  - `python -m pytest -q`
- Use the project's Python environment. Retain each command's full stdout, stderr and
  exit code in session logs before summarizing; a missing result is not a pass.
- These commands, not an agent's prose verdict, determine the validation gate. Do not
  add generated inline drivers, ad hoc keyword assertions, external documentation URLs
  or a requirement for `dev-python-validation` to return `SUCCESS`.
- Only when explicitly requested, run `dev-python-validation` as a separate optional
  E2E diagnostic. Report passed, failed, blocked and unexecuted checks distinctly.
  Its tooling failures, external-service availability or diagnostic verdict do not
  replace or override the required gates. Do not claim E2E success from pytest alone.
- If an optional diagnostic demonstrates a reproducible application regression, report
  the evidence and ask the user whether to address it before publishing; do not silently
  ignore a known defect or label a harness failure as an application regression.

### 3. Bump the version

Update the version string in both files (and nothing else):

- `pyproject.toml` -> `[project].version = "<version>"`
- `src/sive.egg-info/PKG-INFO` -> `Version: <version>`

Verify with `git --no-pager diff` that only those two lines changed.

### 4. Commit, tag, and push

```powershell
git add pyproject.toml src/sive.egg-info/PKG-INFO
git commit -m "chore(release): v<version>"
git tag -a v<version> -m "Release v<version>"
git push origin main
git push origin v<version>
```

Pushing the tag triggers the `Publish to PyPI` workflow.

### 5. Monitor the pipeline

- Find the run triggered by the tag (it can take a few seconds to appear):
  `gh run list --workflow publish-pypi.yml --branch v<version> --limit 1 --json databaseId,status,url`
- Watch it until completion: `gh run watch <run-id> --exit-status`
- On failure, fetch the failing logs with `gh run view <run-id> --log-failed`, summarize the cause,
  and stop. Do not delete the tag or re-push without user confirmation.

### 6. Report

On success, report:

- Released version and tag `v<version>`
- Workflow run URL
- GitHub release: `gh release view v<version> --json url -q .url`
- PyPI page: `https://pypi.org/project/sive/<version>/`

## Safety rules

- Never print, request, or store secrets; PyPI auth is handled by the workflow (OIDC trusted publishing).
- Never force-push, rewrite history, or delete/move existing tags without explicit user approval.
- Never create the GitHub release manually; the workflow creates it.
