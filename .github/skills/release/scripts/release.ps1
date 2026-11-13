param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [switch]$SkipPublish,
    [switch]$SkipGitHubRelease,
    [switch]$AllowNonMain
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:PythonCommand = "python"

function Write-Step {
    param([string]$Message)
    Write-Host "[release] $Message"
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$CommandArgs)
    & git @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git command failed: git $($CommandArgs -join ' ')"
    }
}

function Invoke-Python {
    param([Parameter(Mandatory = $true)][string[]]$CommandArgs)
    & $script:PythonCommand @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "python command failed: $script:PythonCommand $($CommandArgs -join ' ')"
    }
}

function Resolve-PythonCommand {
    if ($env:VIRTUAL_ENV) {
        $venvPython = Join-Path -Path $env:VIRTUAL_ENV -ChildPath "Scripts/python.exe"
        if (Test-Path $venvPython) {
            return $venvPython
        }
    }

    $repoVenvPython = Join-Path -Path (Join-Path -Path (Get-Location) -ChildPath ".venv") -ChildPath "Scripts/python.exe"
    if (Test-Path $repoVenvPython) {
        return $repoVenvPython
    }

    return "python"
}

function Normalize-CommandOutput {
    param($Value)

    if ($null -eq $Value) {
        return ""
    }

    if ($Value -is [array]) {
        return (($Value | ForEach-Object { [string]$_ }) -join "`n").Trim()
    }

    return ([string]$Value).Trim()
}

function Invoke-ValidationGate {
    Write-Step "Running mandatory validation gate (ruff, mypy, pytest)"
    Invoke-Python -CommandArgs @("-m", "ruff", "check", "src", "tests")
    Invoke-Python -CommandArgs @("-m", "mypy", "src")
    Invoke-Python -CommandArgs @("-m", "pytest", "-q")
}

function Replace-Single {
    param(
        [string]$Path,
        [string]$Pattern,
        [string]$Replacement
    )

    if (-not (Test-Path $Path)) {
        throw "File not found: $Path"
    }

    $content = Get-Content -Path $Path -Raw
    $matches = [regex]::Matches($content, $Pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one match in '$Path' for pattern '$Pattern', found $($matches.Count)."
    }

    $newContent = [regex]::Replace(
        $content,
        $Pattern,
        $Replacement,
        [System.Text.RegularExpressions.RegexOptions]::Multiline
    )

    Set-Content -Path $Path -Value $newContent -NoNewline
}

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Missing .env file at '$Path'."
    }

    $pairs = @{}
    foreach ($line in Get-Content -Path $Path) {
        $trim = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trim) -or $trim.StartsWith("#")) {
            continue
        }

        $eq = $trim.IndexOf("=")
        if ($eq -lt 1) {
            continue
        }

        $key = $trim.Substring(0, $eq).Trim()
        $value = $trim.Substring($eq + 1).Trim()

        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        $pairs[$key] = $value
    }

    return $pairs
}

function Set-TwineCredentialsFromEnv {
    param([hashtable]$EnvMap)

    if ($EnvMap.ContainsKey("TWINE_USERNAME") -and $EnvMap.ContainsKey("TWINE_PASSWORD")) {
        $env:TWINE_USERNAME = $EnvMap["TWINE_USERNAME"]
        $env:TWINE_PASSWORD = $EnvMap["TWINE_PASSWORD"]
        if ($EnvMap.ContainsKey("TWINE_REPOSITORY_URL")) {
            $env:TWINE_REPOSITORY_URL = $EnvMap["TWINE_REPOSITORY_URL"]
        }
        return
    }

    if ($EnvMap.ContainsKey("PYPI_USERNAME") -and $EnvMap.ContainsKey("PYPI_PASSWORD")) {
        $env:TWINE_USERNAME = $EnvMap["PYPI_USERNAME"]
        $env:TWINE_PASSWORD = $EnvMap["PYPI_PASSWORD"]
        if ($EnvMap.ContainsKey("TWINE_REPOSITORY_URL")) {
            $env:TWINE_REPOSITORY_URL = $EnvMap["TWINE_REPOSITORY_URL"]
        }
        return
    }

    if ($EnvMap.ContainsKey("PYPI_TOKEN")) {
        $env:TWINE_USERNAME = "__token__"
        $env:TWINE_PASSWORD = $EnvMap["PYPI_TOKEN"]
        if ($EnvMap.ContainsKey("TWINE_REPOSITORY_URL")) {
            $env:TWINE_REPOSITORY_URL = $EnvMap["TWINE_REPOSITORY_URL"]
        }
        return
    }

    throw "No PyPI credentials found in .env. Expected TWINE_USERNAME/TWINE_PASSWORD, PYPI_USERNAME/PYPI_PASSWORD, or PYPI_TOKEN."
}

# Accepted release formats (PEP 440 subset used by this project):
# - stable: 0.1.0
# - dev:    0.1.0.dev1
# - alpha:  0.1.0a1
# - beta:   0.1.0b1
# - rc:     0.1.0rc1
$versionPattern = '^\d+\.\d+\.\d+(?:\.dev\d+|a\d+|b\d+|rc\d+)?$'
if ($Version -notmatch $versionPattern) {
    throw "Invalid version '$Version'. Expected one of: 0.1.0, 0.1.0.dev1, 0.1.0a1, 0.1.0b1, 0.1.0rc1."
}

Require-Command git
Require-Command gh
$script:PythonCommand = Resolve-PythonCommand
if (-not (Test-Path $script:PythonCommand) -and -not (Get-Command $script:PythonCommand -ErrorAction SilentlyContinue)) {
    throw "Required command '$script:PythonCommand' was not found in PATH."
}

Write-Step "Validating git branch and working tree"
$branchRaw = & git rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Unable to determine current git branch."
}
$branch = Normalize-CommandOutput -Value $branchRaw

if (-not $AllowNonMain -and $branch -ne "main") {
    throw "Current branch is '$branch'. Switch to 'main' or pass -AllowNonMain."
}

$dirtyRaw = & git status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect git status."
}
$dirty = Normalize-CommandOutput -Value $dirtyRaw
if (-not [string]::IsNullOrWhiteSpace($dirty)) {
    throw "Working tree is not clean. Commit/stash changes before release."
}

Write-Step "Checking release tag availability"
$tag = "v$Version"
$existingTagRaw = & git tag --list $tag
$existingTag = Normalize-CommandOutput -Value $existingTagRaw
if (-not [string]::IsNullOrWhiteSpace($existingTag)) {
    throw "Tag '$tag' already exists."
}

Invoke-ValidationGate

Write-Step "Bumping version in pyproject.toml and PKG-INFO"
Replace-Single -Path "pyproject.toml" -Pattern '^version\s*=\s*"[^"]+"\s*$' -Replacement "version = `"$Version`""
Replace-Single -Path "src/sive.egg-info/PKG-INFO" -Pattern '^Version:\s*.+$' -Replacement "Version: $Version"

Write-Step "Ensuring build and twine modules are available"
Invoke-Python -CommandArgs @("-m", "pip", "install", "--disable-pip-version-check", "--quiet", "build", "twine")

Write-Step "Cleaning dist directory"
if (Test-Path "dist") {
    Remove-Item -Path "dist/*" -Force -ErrorAction SilentlyContinue
}

Write-Step "Building package"
Invoke-Python -CommandArgs @("-m", "build")

Write-Step "Committing and tagging release"
Invoke-Git -CommandArgs @("add", "pyproject.toml")
Invoke-Git -CommandArgs @("add", "-f", "src/sive.egg-info/PKG-INFO")
Invoke-Git -CommandArgs @("commit", "-m", "chore(release): v$Version")

Invoke-Git -CommandArgs @("tag", "-a", $tag, "-m", $tag)

Write-Step "Pushing commit and tag"
Invoke-Git -CommandArgs @("push", "origin", $branch)
Invoke-Git -CommandArgs @("push", "origin", $tag)

if (-not $SkipGitHubRelease) {
    Write-Step "Creating GitHub release"
    & gh release create $tag --title $tag --generate-notes
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub release creation failed for tag '$tag'."
    }
}

if (-not $SkipPublish) {
    Write-Step "Loading credentials from .env"
    $envMap = Import-DotEnv -Path ".env"
    Set-TwineCredentialsFromEnv -EnvMap $envMap

    Write-Step "Uploading package to PyPI with twine"
    if ([string]::IsNullOrWhiteSpace($env:TWINE_REPOSITORY_URL)) {
        Invoke-Python -CommandArgs @("-m", "twine", "upload", "dist/*")
    }
    else {
        Invoke-Python -CommandArgs @("-m", "twine", "upload", "--repository-url", $env:TWINE_REPOSITORY_URL, "dist/*")
    }
}

Write-Step "Release workflow completed for $Version"
