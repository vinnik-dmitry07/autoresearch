# Parallel ladder eval: B4 + B1 + B0 match runs, merge search_score.
# Usage: powershell -File scripts\triage_ladder.ps1 -Eval quick -LogPath durak\triage.log
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('quick', 'medium', 'full')]
    [string]$Eval,
    [string]$SimPath = '',
    [string]$LogPath = '',
    [string]$BestB4 = '',
    [double]$RegressThresh = 0.005,
    [string]$SeedBase = '0'
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Sim = if ($SimPath) { $SimPath } else { Join-Path $Root 'durak\build\simulate.exe' }
if (-not (Test-Path $Sim)) { Write-Error "simulate.exe not found: $Sim" }

$batch = switch ($Eval) {
    'quick' { '50000' }
    'medium' { '100000' }
    'full' { '500000' }
}
$seeds = switch ($Eval) {
    'quick' { $null }
    'medium' { '500000' }
    'full' { $null }
}

$tmpdir = Join-Path $Root 'durak\triage_parts'
New-Item -ItemType Directory -Force -Path $tmpdir | Out-Null

function Start-MatchJob {
    param([string]$Opponent)
    $log = Join-Path $tmpdir "$Opponent`_$Eval`_$SeedBase.log"
    $job = Start-Job -ScriptBlock {
        param($Sim, $EvalName, $Batch, $Opponent, $Log, $SeedBaseArg, $SeedsArg)
        $args = @(
            '--mode', 'match',
            '--opponent', $Opponent,
            '--batch', $Batch,
            '--seed-base', $SeedBaseArg
        )
        if ($EvalName -eq 'quick') {
            $args += '--eval', 'quick'
        } else {
            $args += '--eval', 'full'
            if ($SeedsArg) { $args += '--seeds', $SeedsArg }
        }
        & $Sim @args 2>&1 | Out-File -FilePath $Log -Encoding utf8
        if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
    } -ArgumentList $Sim, $Eval, $batch, $Opponent, $log, $SeedBase, $seeds
    return @{ Job = $job; Log = $log }
}

function Read-PointRate {
    param([string]$LogFile)
    if (-not (Test-Path $LogFile)) { return $null }
    $last = $null
    foreach ($line in (Get-Content $LogFile -ErrorAction SilentlyContinue)) {
        if ($line -match 'point_rate=([0-9.]+)') { $last = [double]$matches[1] }
    }
    return $last
}

function Read-Complexity {
    param([string]$LogFile)
    if (-not (Test-Path $LogFile)) { return 100 }
    foreach ($line in (Get-Content $LogFile -ErrorAction SilentlyContinue | Select-Object -First 10)) {
        if ($line -match 'complexity=(\d+)') { return [int]$matches[1] }
    }
    return 100
}

Write-Host "=== Parallel ladder $Eval seed_base=$SeedBase (batch=$batch) ==="

$p4 = Start-MatchJob -Opponent 'B4'
$p1 = Start-MatchJob -Opponent 'B1'
$p0 = Start-MatchJob -Opponent 'B0'

Wait-Job $p4.Job | Out-Null
$code4 = Receive-Job $p4.Job
if ($code4 -ne 0) {
    Write-Host "B4 eval failed (exit $code4)"
    if (Test-Path $p4.Log) { Get-Content $p4.Log | Write-Host }
    Stop-Job $p1.Job, $p0.Job -ErrorAction SilentlyContinue
    Remove-Job $p1.Job, $p0.Job, $p4.Job -Force -ErrorAction SilentlyContinue
    exit 1
}

$b4pr = Read-PointRate -LogFile $p4.Log
$complexity = Read-Complexity -LogFile $p4.Log
$penalty = $complexity / 10000.0
$skipRest = $false

if ($BestB4 -and ($null -ne $b4pr)) {
    $bestB4d = [double]$BestB4
    if ($b4pr -lt ($bestB4d - $RegressThresh)) {
        Write-Host "Early exit: B4=$b4pr < best_B4-$RegressThresh ($($bestB4d - $RegressThresh))"
        Stop-Job $p1.Job, $p0.Job -ErrorAction SilentlyContinue
        $skipRest = $true
    }
}

$b1pr = 0.93451
$b0pr = 0.96803

if (-not $skipRest) {
    Wait-Job $p1.Job, $p0.Job | Out-Null
    $code1 = Receive-Job $p1.Job
    $code0 = Receive-Job $p0.Job
    if ($code1 -ne 0 -or $code0 -ne 0) {
        Write-Host "B1/B0 eval failed (B1=$code1 B0=$code0)"
        Remove-Job $p1.Job, $p0.Job, $p4.Job -Force -ErrorAction SilentlyContinue
        exit 1
    }
    $b1pr = Read-PointRate -LogFile $p1.Log
    $b0pr = Read-PointRate -LogFile $p0.Log
}

Remove-Job $p1.Job, $p0.Job, $p4.Job -Force -ErrorAction SilentlyContinue

$search = 0.50 * $b4pr + 0.30 * $b1pr + 0.20 * $b0pr - $penalty

$summary = @(
    '',
    "--- ladder results (parallel $Eval seed_base=$SeedBase) ---",
    ("B2 vs B4           point_rate={0:F5}  (complexity={1})" -f $b4pr, $complexity),
    ("B2 vs B1           point_rate={0:F5}" -f $b1pr),
    ("B2 vs B0           point_rate={0:F5}" -f $b0pr),
    ("search_score={0:F5}  (0.5*B4 + 0.3*B1 + 0.2*B0 - complexity/10000)" -f $search),
    ("reporting_point_rate_vs_B4={0:F5}  complexity={1}" -f $b4pr, $complexity)
)
if ($skipRest) { $summary += 'early_exit=B1/B0 skipped (B4 regression)' }

foreach ($line in $summary) { Write-Host $line }

if ($LogPath) {
    foreach ($line in $summary) { Add-Content -Path $LogPath -Value $line }
    foreach ($px in @($p4, $p1, $p0)) {
        if (Test-Path $px.Log) { Add-Content -Path $LogPath -Value (Get-Content $px.Log) }
    }
}

$scoreFile = Join-Path $tmpdir "search_score_${Eval}_${SeedBase}.txt"
Set-Content -Path $scoreFile -Value ('{0:F5}' -f $search) -NoNewline
