<#
.SYNOPSIS
  MediCall AI worktree startup script (Windows / PowerShell).
  Prepares a clean, verified working state: git repo + optional worktree,
  backend/.env scaffold, stdlib test suites, syntax check, optional infra.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File start-worktree.ps1
  powershell -ExecutionPolicy Bypass -File start-worktree.ps1 -Branch g4-voice
  powershell -ExecutionPolicy Bypass -File start-worktree.ps1 -Branch g4-voice -WithInfra
#>
[CmdletBinding()]
param(
  [string]$ProjectRoot = 'C:\Users\vigilare\OneDrive - Vigilare BP PVT LTD\Documents\MediCall-AI',
  [string]$Branch = '',
  [string]$WorktreeDir = '',
  [switch]$WithInfra,
  [switch]$SkipGit
)
$ErrorActionPreference = 'Stop'

function Step($msg) { Write-Host "==> $msg" }
function Warn($msg) { Write-Host "!!  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "XX  $msg" -ForegroundColor Red; exit 1 }

# 1. Sanity: must be the MediCall project (never the Talkbyte originals)
if (-not (Test-Path (Join-Path $ProjectRoot 'backend\main.py'))) {
  Fail "Not a MediCall project root (backend\main.py missing): $ProjectRoot"
}
if (-not (Test-Path (Join-Path $ProjectRoot '.opencode\spec-idea-refinement-gaps.md'))) {
  Fail "Spec tracker missing (.opencode\spec-idea-refinement-gaps.md): $ProjectRoot"
}
Step "Project root OK: $ProjectRoot"
Set-Location $ProjectRoot

# 2. Git repo + optional worktree (one isolated tree per task/branch)
$repoRoot = $ProjectRoot
if ($SkipGit) {
  Step 'Skipping git setup (-SkipGit)'
} else {
  $git = Get-Command git -ErrorAction SilentlyContinue
  if (-not $git) {
    Warn 'git not found — skipping repo/worktree setup'
  } else {
    if (-not (Test-Path (Join-Path $ProjectRoot '.git'))) {
      Step 'git init + baseline commit'
      git init | Out-Null
      git add -A
      git commit -m 'MediCall AI baseline (from Talkbyte_clone)' | Out-Null
    } else {
      Step 'git repo already present'
    }
    if ($Branch -ne '') {
      $safe = ($Branch -replace '[^A-Za-z0-9_.-]', '-')
      if ($WorktreeDir -eq '') {
        $WorktreeDir = Join-Path $ProjectRoot ".worktrees\$safe"
      }
      if (-not (Test-Path $WorktreeDir)) {
        Step "Creating worktree '$Branch' at $WorktreeDir"
        git worktree add -b $Branch $WorktreeDir 2>$null
        if ($LASTEXITCODE -ne 0) { git worktree add $WorktreeDir $Branch }
      } else {
        Step "Worktree already exists: $WorktreeDir"
      }
      $repoRoot = $WorktreeDir
      Set-Location $repoRoot
    }
  }
}

# 3. Env scaffold (never overwrite an existing .env)
$example = Join-Path $repoRoot 'backend\.env.example'
$envFile = Join-Path $repoRoot 'backend\.env'
if ((Test-Path $example) -and (-not (Test-Path $envFile))) {
  Copy-Item $example $envFile
  Step 'Created backend\.env from .env.example — fill in secrets'
} else {
  Step 'backend\.env already present (or no example to copy)'
}

# 4. Verify: test suites + syntax (must be GREEN before work starts)
$py = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) { Fail 'Python not found on PATH' }
Step "Python: $(python3 --version 2>&1)"
$allOk = $true
Push-Location (Join-Path $repoRoot 'backend')
foreach ($t in @('tests\test_g1_g2.py', 'tests\test_g3_state_machine.py')) {
  if (Test-Path $t) {
    python3 $t
    if ($LASTEXITCODE -ne 0) { $allOk = $false; Warn "$t FAILED" }
    else { Step "$t GREEN" }
  } else {
    Warn "$t not found — skipping"
  }
}
python3 -m py_compile main.py app/models/call.py app/db/postgres.py
if ($LASTEXITCODE -ne 0) { $allOk = $false; Warn 'py_compile FAILED' }
else { Step 'py_compile clean' }
Pop-Location

# 5. Optional infra (postgres + redis only; never auto-starts app/containers)
if ($WithInfra) {
  Step 'Starting infra: postgres + redis'
  Set-Location $repoRoot
  docker compose up -d postgres redis
}

if ($allOk) { Step 'STARTUP GREEN — ready to work' }
else { Fail 'STARTUP RED — fix the failures above before working' }
