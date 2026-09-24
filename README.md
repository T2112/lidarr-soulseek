# Lidarr Soulseek Worker

**Version 1.1.0** — Windows package. No Docker. No slskd.

The worker reads Lidarr **Wanted → Missing**, searches Soulseek, downloads matching albums or individual missing tracks, converts FLAC/WAV to MP3 when needed, asks Lidarr to import and rename, then cleans leftover files.

Custom Lidarr import list (MusicBrainz IDs):  
https://raw.githubusercontent.com/T2112/lidarr-soulseek/main/lists/lidarr-custom-list.json

## What's new in 1.1.0

- Status page with live transfers, cancel, and recent completions
- Track fill for partial albums (does not re-download albums Lidarr already has)
- Convert each lossless file as soon as it finishes
- Concurrent album searches
- A–Z artist order and optional one-artist focus
- Incomplete folder cleanup on failure plus a 12-hour sweep
- Lidarr `RenameFiles` after a successful import
- Full changelog: [CHANGELOG.md](CHANGELOG.md)

## Requirements

- Windows 10 or 11
- Lidarr already running on this PC
- A Soulseek account
- Python 3.11+ from https://www.python.org/downloads/  
  Tick **Add python.exe to PATH**
- ffmpeg (`winget install Gyan.FFmpeg`) if you want FLAC converted to MP3

## Install

1. Unzip this folder somewhere permanent, for example `C:\Tools\lidarr-soulseek`.
2. Open PowerShell **in this folder**:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

3. Edit `config.toml`. Every text value stays in double quotes.

Lidarr API key: **Settings → General → Security**.

4. Confirm Lidarr: `.\.venv\Scripts\python.exe check.py`
5. Open ports with `open-firewall.ps1` as Administrator. Forward TCP 2234 and 2235.
6. Test: `.\.venv\Scripts\python.exe main.py` then open http://127.0.0.1:8787
7. Background at logon: `.\register-task.ps1`

## Lidarr so files land in the library

- Settings → Media Management → Rename Tracks = On
- Artist Root Folder must be the real library, not Complete
- Completed Download Handling = Enable

The worker calls `DownloadedAlbumsScan` with Move, then `RenameFiles`.

## Legal

Soulseek is a peer-to-peer network. Only download and share files you have the right to download and share.
