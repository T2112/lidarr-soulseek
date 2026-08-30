from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from pathlib import Path

from aioslsk.client import SoulSeekClient
from aioslsk.settings import (
    CredentialsSettings,
    NetworkSettings,
    Settings,
    SharesSettings,
    SharedDirectorySettingEntry,
    ListeningSettings,
    UpnpSettings,
    ServerSettings,
    ReconnectSettings,
)
from aioslsk.shares.model import DirectoryShareMode

from config_loader import Config
from lidarr_client import LidarrClient
from match import AUDIO_EXT, build_queries, build_track_queries, group_results, score_folder, score_track_item
from state import JobStore

log = logging.getLogger("lidarr_slsk")
LOSSLESS_EXT = {".flac", ".wav", ".aiff", ".aif", ".wv", ".ape"}


def safe_name(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:120] or "Unknown"


def album_year(album: dict) -> str | None:
    raw = album.get("releaseDate") or ""
    return raw[:4] if raw and raw[:4].isdigit() else None


def artist_name(album: dict) -> str:
    artist = album.get("artist") or {}
    return artist.get("artistName") or album.get("artistName") or "Unknown Artist"


def track_titles(tracks: list[dict]) -> list[str]:
    titles = []
    for t in tracks:
        title = t.get("title") or t.get("mediumNumber")
        if title:
            titles.append(str(title))
    return titles


def state_name(transfer) -> str:
    state = getattr(transfer, "state", None)
    if state is None:
        return ""
    for attr in ("NAME", "name"):
        val = getattr(state, attr, None)
        if isinstance(val, str):
            return val.upper()
    text = str(state).upper()
    for token in ("COMPLETE", "FAILED", "ABORTED", "INCOMPLETE", "DOWNLOADING", "QUEUED", "PAUSED"):
        if token in text:
            return token
    return text


def build_slsk_settings(cfg: Config) -> Settings:
    directories = []
    if cfg.share_dir:
        directories.append(
            SharedDirectorySettingEntry(path=cfg.share_dir, share_mode=DirectoryShareMode.EVERYONE)
        )
    return Settings(
        credentials=CredentialsSettings(username=cfg.slsk_username, password=cfg.slsk_password),
        network=NetworkSettings(
            server=ServerSettings(reconnect=ReconnectSettings(auto=True, timeout=15)),
            listening=ListeningSettings(port=cfg.listen_port, obfuscated_port=cfg.obfuscated_port),
            upnp=UpnpSettings(enabled=cfg.enable_upnp),
        ),
        shares=SharesSettings(download=str(cfg.download_dir), directories=directories, scan_on_start=False),
    )


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def convert_to_mp3(src: Path, dest_mp3: Path, bitrate: int) -> None:
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH. Install it (winget install Gyan.FFmpeg) and restart the worker.")
    dest_mp3.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-y", "-i", str(src), "-codec:a", "libmp3lame", "-b:a", f"{bitrate}k", "-map_metadata", "0", "-id3v2_version", "3", str(dest_mp3)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {src.name}: {proc.stderr[-500:]}")


def prune_empty_dirs(start: Path, stop_at: Path) -> None:
    current = start if start.is_dir() else start.parent
    stop_at = stop_at.resolve()
    while current.exists():
        try:
            resolved = current.resolve()
        except OSError:
            break
        if resolved == stop_at or stop_at not in resolved.parents:
            break
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def cleanup_sources(paths: list[Path], download_root: Path) -> None:
    for src in paths:
        try:
            if src.is_file():
                src.unlink()
                log.info("Deleted source file %s", src)
        except OSError:
            log.exception("Could not delete %s", src)
            continue
        prune_empty_dirs(src.parent, download_root)


def stage_album_folder(cfg: Config, artist: str, title: str, year: str | None, transfers) -> tuple[Path, list[Path]]:
    stamp = f"{safe_name(artist)} - {safe_name(title)}"
    if year:
        stamp = f"{stamp} ({year})"
    dest = cfg.complete_dir / stamp
    dest.mkdir(parents=True, exist_ok=True)
    removable: list[Path] = []
    for transfer in transfers:
        local = getattr(transfer, "local_path", None)
        if not local:
            continue
        src = Path(local)
        if not src.is_file():
            continue
        ext = src.suffix.lower()
        if ext not in AUDIO_EXT:
            continue
        if cfg.convert_to_mp3 and ext in LOSSLESS_EXT:
            target = dest / (src.stem + ".mp3")
            if not target.exists():
                log.info("Converting %s -> MP3 %sk", src.name, cfg.convert_bitrate)
                convert_to_mp3(src, target, cfg.convert_bitrate)
            removable.append(src)
            continue
        target = dest / src.name
        if not target.exists():
            shutil.copy2(src, target)
        removable.append(src)
    return dest, removable


class Worker:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.lidarr = LidarrClient(cfg.lidarr_url, cfg.lidarr_api_key)
        self.store = JobStore(cfg.state_db)
        self.client: SoulSeekClient | None = None

    def close(self) -> None:
        self.lidarr.close()
        self.store.close()

    def soulseek_logged_in(self) -> bool:
        return bool(self.client and getattr(self.client, "session", None))

    async def start_soulseek(self) -> None:
        self.client = SoulSeekClient(build_slsk_settings(self.cfg))
        await self.client.start()
        await self.client.login()
        await asyncio.sleep(2)
        if not self.soulseek_logged_in():
            raise RuntimeError("Soulseek login returned but session is not active")
        log.info("Logged in to Soulseek as %s", self.cfg.slsk_username)

    async def ensure_soulseek(self) -> None:
        if self.soulseek_logged_in():
            return
        log.warning("Soulseek session dropped; reconnecting")
        try:
            if self.client:
                await self.client.stop()
        except Exception:
            log.exception("Error while stopping dead Soulseek client")
        self.client = None
        await asyncio.sleep(5)
        await self.start_soulseek()

    async def stop_soulseek(self) -> None:
        if self.client:
            await self.client.stop()
            self.client = None

    async def run_forever(self) -> None:
        status = self.lidarr.ping()
        log.info("Lidarr OK: %s", status.get("version") or status.get("appName") or "connected")
        await self.start_soulseek()
        try:
            while True:
                try:
                    await self.cycle()
                except Exception:
                    log.exception("Cycle failed")
                await asyncio.sleep(self.cfg.cycle_seconds)
        finally:
            await self.stop_soulseek()

    async def cycle(self) -> None:
        missing = self.lidarr.wanted_missing()
        log.info("Lidarr missing albums: %s", len(missing))
        processed = 0
        for album in missing:
            if processed >= self.cfg.max_albums_per_cycle:
                break
            album_id = int(album["id"])
            artist = artist_name(album)
            title = album.get("title") or "Unknown Album"
            if self.store.should_skip(album_id, self.cfg.retry_hours):
                continue
            self.store.upsert(album_id, artist, title, "searching")
            ok = await self.process_album(album)
            processed += 1
            if not ok:
                log.info("No usable result yet for %s - %s", artist, title)
        if self.cfg.fill_missing_tracks:
            await self.cycle_tracks()

    async def cycle_tracks(self) -> None:
        try:
            holes = self.lidarr.missing_tracks_on_partial_albums()
        except Exception:
            log.exception("Could not list missing tracks")
            return
        log.info("Lidarr missing tracks on partial albums: %s", len(holes))
        processed = 0
        for hole in holes:
            if processed >= self.cfg.max_tracks_per_cycle:
                break
            track = hole["track"]
            track_id = int(track["id"])
            album = hole["album"]
            album_id = int(album["id"])
            artist = hole["artist_name"]
            album_title = hole["album_title"]
            title = track.get("title") or "Unknown Track"
            if self.store.should_skip_track(track_id, self.cfg.retry_hours):
                continue
            self.store.upsert_track(track_id, album_id, artist, title, "searching")
            ok = await self.process_track(hole)
            processed += 1
            if not ok:
                log.info("No usable track yet for %s - %s - %s", artist, album_title, title)

    async def process_track(self, hole: dict) -> bool:
        await self.ensure_soulseek()
        assert self.client is not None
        track = hole["track"]
        album = hole["album"]
        track_id = int(track["id"])
        album_id = int(album["id"])
        artist = hole["artist_name"]
        album_title = hole["album_title"]
        title = track.get("title") or "Unknown Track"
        year = album_year(album)
        queries = build_track_queries(artist, album_title, title)
        log.info("Track search: %s", " | ".join(queries))
        best_item = None
        best_user = ""
        best_score = 0.0
        for query in queries:
            request = await self.client.searches.search(query)
            await asyncio.sleep(self.cfg.search_wait_seconds)
            for result in request.results:
                username = getattr(result, "username", "") or ""
                if username.lower() in self.cfg.ignored_users:
                    continue
                for item in list(getattr(result, "shared_items", None) or []):
                    score, reason = score_track_item(
                        item, username, artist, album_title, title,
                        self.cfg.preferred_extensions, self.cfg.min_filename_ratio, self.cfg.min_mp3_bitrate,
                    )
                    if reason != "ok":
                        continue
                    if score > best_score:
                        best_score = score
                        best_item = item
                        best_user = username
            try:
                self.client.searches.remove_request(request)
            except Exception:
                pass
            if best_item and best_score >= 18:
                break
        if best_item is None:
            self.store.upsert_track(track_id, album_id, artist, title, "no_match", "no file passed filters")
            return False
        log.info("Picked track %s from %s :: %s (score %.1f)", title, best_user, getattr(best_item, "filename", ""), best_score)
        self.store.upsert_track(track_id, album_id, artist, title, "downloading", best_user)
        transfer = await self.client.transfers.download(best_user, best_item.filename)
        deadline = asyncio.get_event_loop().time() + min(self.cfg.download_timeout_minutes, 30) * 60
        while asyncio.get_event_loop().time() < deadline:
            name = state_name(transfer)
            if name in {"COMPLETE", "FAILED", "ABORTED"}:
                break
            log.info("Track download %s: %s", title, name or "waiting")
            await asyncio.sleep(10)
        if state_name(transfer) != "COMPLETE":
            self.store.upsert_track(track_id, album_id, artist, title, "failed", state_name(transfer) or "timeout")
            return False
        folder, sources = stage_album_folder(self.cfg, artist, album_title, year, [transfer])
        audio_count = sum(1 for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT)
        if audio_count == 0:
            self.store.upsert_track(track_id, album_id, artist, title, "failed", "no file staged")
            return False
        scan_path = str(Path(self.cfg.lidarr_scan_path) / folder.name)
        try:
            self.lidarr.scan_downloaded(scan_path)
        except Exception as exc:
            try:
                self.lidarr.scan_downloaded(str(folder))
            except Exception:
                self.store.upsert_track(track_id, album_id, artist, title, "failed", f"scan failed: {exc}")
                raise
        if self.cfg.delete_sources_after_import:
            cleanup_sources(sources, self.cfg.download_dir)
        self.store.upsert_track(track_id, album_id, artist, title, "imported", str(folder))
        log.info("Asked Lidarr to import missing track %s into %s", title, folder)
        return True

    async def process_album(self, album: dict) -> bool:
        await self.ensure_soulseek()
        assert self.client is not None
        album_id = int(album["id"])
        artist = artist_name(album)
        title = album.get("title") or "Unknown Album"
        year = album_year(album)
        tracks = self.lidarr.tracks_for_album(album_id)
        titles = track_titles(tracks)
        queries = build_queries(artist, title, year)
        log.info("Searching: %s", " | ".join(queries))
        best = None
        for query in queries:
            request = await self.client.searches.search(query)
            await asyncio.sleep(self.cfg.search_wait_seconds)
            folders = group_results(request.results, self.cfg.ignored_users)
            for folder in folders:
                scored = score_folder(
                    folder, artist, title, titles,
                    self.cfg.preferred_extensions, self.cfg.min_filename_ratio,
                    self.cfg.track_count_tolerance, self.cfg.min_mp3_bitrate,
                )
                if scored.reason != "ok":
                    continue
                if best is None or scored.score > best.score:
                    best = scored
            try:
                self.client.searches.remove_request(request)
            except Exception:
                pass
            if best and best.score >= 20:
                break
        if best is None:
            self.store.upsert(album_id, artist, title, "no_match", "no folder passed filters")
            return False
        log.info("Picked %s :: %s (%s files, score %.1f)", best.username, best.remote_dir, len(best.files), best.score)
        self.store.upsert(album_id, artist, title, "downloading", best.username)
        transfers = []
        for item in best.files:
            transfer = await self.client.transfers.download(best.username, item.filename)
            transfers.append(transfer)
        deadline = asyncio.get_event_loop().time() + self.cfg.download_timeout_minutes * 60
        while asyncio.get_event_loop().time() < deadline:
            names = [state_name(t) for t in transfers]
            if all(n in {"COMPLETE", "FAILED", "ABORTED"} for n in names):
                break
            complete = sum(1 for n in names if n == "COMPLETE")
            log.info("Download progress %s/%s complete", complete, len(transfers))
            await asyncio.sleep(15)
        complete_transfers = [t for t in transfers if state_name(t) == "COMPLETE"]
        needed = max(1, len(best.files) - self.cfg.track_count_tolerance)
        if len(complete_transfers) < needed:
            detail = f"finished {len(complete_transfers)}/{len(transfers)}"
            self.store.upsert(album_id, artist, title, "failed", detail)
            log.warning("Incomplete download for %s - %s (%s)", artist, title, detail)
            return False
        folder, sources = stage_album_folder(self.cfg, artist, title, year, complete_transfers)
        audio_count = sum(1 for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT)
        if audio_count == 0:
            self.store.upsert(album_id, artist, title, "failed", "no files staged")
            return False
        scan_path = str(Path(self.cfg.lidarr_scan_path) / folder.name)
        try:
            self.lidarr.scan_downloaded(scan_path)
        except Exception as exc:
            try:
                self.lidarr.scan_downloaded(str(folder))
            except Exception:
                self.store.upsert(album_id, artist, title, "failed", f"scan failed: {exc}")
                raise
        if self.cfg.delete_sources_after_import:
            cleanup_sources(sources, self.cfg.download_dir)
        self.store.upsert(album_id, artist, title, "imported", str(folder))
        log.info("Asked Lidarr to import %s", folder)
        return True
