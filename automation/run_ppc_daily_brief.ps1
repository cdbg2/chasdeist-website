$ErrorActionPreference = "Stop"

$repo = "C:\Users\chasd\Documents\ProgrammingProjects\claude-code-fun"
$python = "C:\Users\chasd\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$cli = "C:\Users\chasd\.local\bin\save-to-spotify.exe"
$opml = "C:\Users\chasd\AppData\Local\Temp\subscriptions.opml"
$outDir = Join-Path $repo "ppc_daily_brief"
$deps = Join-Path $repo ".codex-tmp\pydeps"
$logDir = Join-Path $repo "ppc_daily_brief\logs"
$date = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $logDir "$date.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log {
  param([string]$Message)
  $line = "$(Get-Date -Format o) $Message"
  Write-Host $line
  Add-Content -LiteralPath $log -Value $line
}

Set-Location $repo
Write-Log "Starting Chas's PPC Daily Brief automation"

if (!(Test-Path -LiteralPath $python)) {
  throw "Bundled Python not found at $python"
}

if (!(Test-Path -LiteralPath $cli)) {
  throw "Save to Spotify CLI not found at $cli"
}

if (!(Test-Path -LiteralPath $opml)) {
  throw "Feedly OPML not found at $opml. Export Feedly OPML again or update this path."
}

if (!(Test-Path -LiteralPath (Join-Path $deps "edge_tts"))) {
  Write-Log "Installing Edge TTS dependencies into workspace"
  & $python -m pip install --target $deps edge-tts | Tee-Object -FilePath $log -Append
}

$env:PYTHONPATH = $deps

Write-Log "Generating script, cover, and audio"
& $python (Join-Path $repo "automation\generate_ppc_daily_brief.py") `
  --opml $opml `
  --out-dir $outDir `
  --voice "en-US-AriaNeural" | Tee-Object -FilePath $log -Append

$latestRun = Get-Content -LiteralPath (Join-Path $outDir "latest_run.json") -Raw | ConvertFrom-Json
$summary = Get-Content -LiteralPath $latestRun.summary -Raw
$titleDate = Get-Date -Format "MMMM d, yyyy"
$title = "PPC Daily Brief - $titleDate"

Write-Log "Checking Save to Spotify authentication"
& $cli auth status | Tee-Object -FilePath $log -Append

Write-Log "Uploading $title"
& $cli --json upload $latestRun.latest_audio `
  --title $title `
  --summary $summary `
  --image $latestRun.cover `
  --language en | Tee-Object -FilePath $log -Append

Write-Log "Done"
