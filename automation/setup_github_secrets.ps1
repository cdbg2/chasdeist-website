param(
  [string]$Repo = "cdbg2/chasdeist-website",
  [string]$OpmlPath = "C:\Users\chasd\AppData\Local\Temp\subscriptions.opml",
  [string]$TokenPath = "C:\Users\chasd\.config\save-to-spotify\token.json",
  [string]$CliPath = "C:\Users\chasd\.local\bin\save-to-spotify.exe",
  [string]$ShowTitle = "Chas's PPC Daily Brief"
)

$ErrorActionPreference = "Stop"

function Assert-Command {
  param([string]$Name)
  if (!(Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing required command: $Name. Install GitHub CLI first: https://cli.github.com/"
  }
}

function Assert-LastExitCode {
  param([string]$CommandName)
  if ($LASTEXITCODE -ne 0) {
    throw "$CommandName failed with exit code $LASTEXITCODE"
  }
}

function Set-SecretFromFileBase64 {
  param(
    [string]$SecretName,
    [string]$Path
  )

  if (!(Test-Path -LiteralPath $Path)) {
    throw "File not found: $Path"
  }

  $bytes = [System.IO.File]::ReadAllBytes($Path)
  $encoded = [Convert]::ToBase64String($bytes)
  $encoded | gh secret set $SecretName --repo $Repo
  Assert-LastExitCode "gh secret set $SecretName"
}

Assert-Command "gh"

Write-Host "Checking GitHub CLI authentication..."
gh auth status | Out-Host
Assert-LastExitCode "gh auth status"

Write-Host "Setting FEEDLY_OPML_B64..."
Set-SecretFromFileBase64 -SecretName "FEEDLY_OPML_B64" -Path $OpmlPath

Write-Host "Setting SAVE_TO_SPOTIFY_TOKEN_JSON_B64..."
Set-SecretFromFileBase64 -SecretName "SAVE_TO_SPOTIFY_TOKEN_JSON_B64" -Path $TokenPath

if (Test-Path -LiteralPath $CliPath) {
  Write-Host "Looking for Spotify show ID for '$ShowTitle'..."
  try {
    $showsJson = & $CliPath --json shows
    $shows = $showsJson | ConvertFrom-Json
    if ($shows.shows) {
      $showsList = @($shows.shows)
    } elseif ($shows.items) {
      $showsList = @($shows.items)
    } else {
      $showsList = @($shows)
    }
    $matches = @($showsList | Where-Object { $_.title -eq $ShowTitle -or $_.name -eq $ShowTitle })
    if ($matches.Count -gt 0) {
      $showId = $matches[0].uri
      if (!$showId) { $showId = $matches[0].id }
      if ($showId) {
        $showId | gh secret set SAVE_TO_SPOTIFY_SHOW_ID --repo $Repo
        Assert-LastExitCode "gh secret set SAVE_TO_SPOTIFY_SHOW_ID"
        Write-Host "Set SAVE_TO_SPOTIFY_SHOW_ID to $showId"
      } else {
        Write-Warning "Found the show but could not identify its URI/ID. The workflow will use the CLI default show."
      }
    } else {
      Write-Warning "Could not find '$ShowTitle'. The workflow will use the CLI default show unless you set SAVE_TO_SPOTIFY_SHOW_ID manually."
    }
  } catch {
    Write-Warning "Could not list Save to Spotify shows: $($_.Exception.Message)"
    Write-Warning "The workflow will use the CLI default show unless you set SAVE_TO_SPOTIFY_SHOW_ID manually."
  }
}

Write-Host ""
Write-Host "Done. GitHub Actions now has the required secrets."
