# Chas's PPC Daily Brief Automation

This folder powers the weekday cloud automation for the private PPC brief.

## How It Runs

GitHub Actions runs `.github/workflows/ppc-daily-brief.yml` every weekday at
10:00 UTC, which is 6:00 AM New York time during daylight saving time and
5:00 AM during standard time. It can also be run manually from the Actions tab.

The workflow:

1. Restores your Feedly OPML export from a GitHub Secret.
2. Restores your Save to Spotify token from a GitHub Secret.
3. Fetches fresh items from the OPML's `SEM` folder.
4. Builds a short PPC script and source notes.
5. Renders audio with `en-US-AriaNeural`.
6. Uploads the MP3 to Save to Spotify.

Your laptop does not need to be on.

## Required GitHub Secrets

- `FEEDLY_OPML_B64`: base64-encoded Feedly OPML export.
- `SAVE_TO_SPOTIFY_TOKEN_JSON_B64`: base64-encoded Save to Spotify token JSON.
- `SAVE_TO_SPOTIFY_SHOW_ID`: optional but recommended. If set, uploads always
  target the existing `Chas's PPC Daily Brief` show.

Run this locally from PowerShell to set the secrets:

```powershell
C:\Users\chasd\Documents\ProgrammingProjects\claude-code-fun\automation\setup_github_secrets.ps1
```

That helper requires GitHub CLI (`gh`) to be installed and authenticated.

## Refreshing Feeds

The OPML export is static. If you add or remove Feedly feeds, export OPML again
and rerun `setup_github_secrets.ps1`.

## Spotify Auth

If Spotify auth is revoked or expires beyond refresh, run:

```powershell
C:\Users\chasd\.local\bin\save-to-spotify.exe auth login --no-browser
```

Then rerun `setup_github_secrets.ps1` so GitHub Actions receives the refreshed
token JSON.
