# Changelog

All notable changes to this project are documented here.

## [1.1.0] — 2026-09-24

First feature release after the initial Windows package.

### Added

- Local status page at `http://127.0.0.1:8787` with live transfers, cancel buttons, and the last 10 completed downloads.
- Track-level Soulseek search for albums that already have some files in Lidarr (`fill_missing_tracks`).
- Artist focus mode so the worker finishes one artist before hopping (`focus_one_artist`).
- Alphabetical artist order when picking work.
- Concurrent album searches (`concurrent_albums`).
- Incremental FLAC/WAV → MP3 conversion as each file finishes, not after the whole album.
- Incomplete-folder cleanup on failed or cancelled downloads (`clean_incomplete_on_fail`).
- Age sweep of leftover Incomplete files (`incomplete_max_age_hours`, default 12).
- After a successful import, ask Lidarr to **RenameFiles** for that artist so tracks move into the library naming scheme.
- Quiet aioslsk peer-connect warnings so the log is readable.

### Changed

- Full-album Soulseek grabs only run when Lidarr has **zero** files for that album. Partial albums use track fill instead of re-downloading the folder.
- Lidarr wanted/missing is paged until empty instead of stopping at the first 250 records.
- SQLite state is safe across the status-page thread and the worker thread.
- Preferred extension order and conversion settings are documented in `config.example.toml`.

### Fixed

- Duplicate TOML keys no longer sneak into the example config.
- Status page no longer crashes with `SQLite objects created in a thread can only be used in that same thread`.
- Failed downloads no longer pile up in Incomplete for days.

### Upgrade

1. Stop the scheduled task.
2. Copy the new `.py` files over your install. Keep your existing `config.toml`.
3. Add any new keys you want from `config.example.toml` (they have safe defaults if omitted).
4. Start the task again.

## [1.0.0] — 2026-08-29

Initial public package: Windows-native Lidarr + aioslsk worker, no Docker, no slskd.
