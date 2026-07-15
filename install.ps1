[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $repoRoot "orthogonal-research-skill"

if (-not $Destination) {
    $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
    $Destination = Join-Path $codexHome "skills\orthogonal-research-skill"
}

if (-not (Test-Path -LiteralPath (Join-Path $source "SKILL.md"))) {
    throw "Skill source not found: $source"
}

if (Test-Path -LiteralPath $Destination) {
    throw "Destination already exists: $Destination. Remove or rename it before installing."
}

$parent = Split-Path -Parent $Destination
New-Item -ItemType Directory -Force -Path $parent | Out-Null
Copy-Item -LiteralPath $source -Destination $Destination -Recurse

Write-Output "Installed orthogonal-research-skill to:"
Write-Output $Destination
