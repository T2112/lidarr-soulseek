from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class JobStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                album_id INTEGER PRIMARY KEY,
                artist TEXT,
                title TEXT,
                status TEXT NOT NULL,
                detail TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._db.commit()
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS track_jobs (
                track_id INTEGER PRIMARY KEY,
                album_id INTEGER,
                artist TEXT,
                title TEXT,
                status TEXT NOT NULL,
                detail TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def get(self, album_id: int) -> dict | None:
        row = self._db.execute(
            "SELECT album_id, artist, title, status, detail, updated_at FROM jobs WHERE album_id = ?",
            (album_id,),
        ).fetchone()
        if not row:
            return None
        keys = ("album_id", "artist", "title", "status", "detail", "updated_at")
        return dict(zip(keys, row))

    def upsert(self, album_id: int, artist: str, title: str, status: str, detail: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """
            INSERT INTO jobs(album_id, artist, title, status, detail, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(album_id) DO UPDATE SET
                artist=excluded.artist,
                title=excluded.title,
                status=excluded.status,
                detail=excluded.detail,
                updated_at=excluded.updated_at
            """,
            (album_id, artist, title, status, detail, now),
        )
        self._db.commit()

    def should_skip(self, album_id: int, retry_hours: int) -> bool:
        job = self.get(album_id)
        if not job:
            return False
        if job["status"] in {"imported", "downloading"}:
            return True
        if job["status"] in {"failed", "no_match"}:
            try:
                updated = datetime.fromisoformat(job["updated_at"])
            except ValueError:
                return False
            return datetime.now(timezone.utc) - updated < timedelta(hours=retry_hours)
        return False

    def get_track(self, track_id: int) -> dict | None:
        row = self._db.execute(
            "SELECT track_id, album_id, artist, title, status, detail, updated_at FROM track_jobs WHERE track_id = ?",
            (track_id,),
        ).fetchone()
        if not row:
            return None
        keys = ("track_id", "album_id", "artist", "title", "status", "detail", "updated_at")
        return dict(zip(keys, row))

    def upsert_track(
        self, track_id: int, album_id: int, artist: str, title: str, status: str, detail: str = ""
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """
            INSERT INTO track_jobs(track_id, album_id, artist, title, status, detail, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id) DO UPDATE SET
                album_id=excluded.album_id,
                artist=excluded.artist,
                title=excluded.title,
                status=excluded.status,
                detail=excluded.detail,
                updated_at=excluded.updated_at
            """,
            (track_id, album_id, artist, title, status, detail, now),
        )
        self._db.commit()

    def should_skip_track(self, track_id: int, retry_hours: int) -> bool:
        job = self.get_track(track_id)
        if not job:
            return False
        if job["status"] in {"imported", "downloading"}:
            return True
        if job["status"] in {"failed", "no_match"}:
            try:
                updated = datetime.fromisoformat(job["updated_at"])
            except ValueError:
                return False
            return datetime.now(timezone.utc) - updated < timedelta(hours=retry_hours)
        return False
