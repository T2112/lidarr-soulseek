from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from aioslsk.protocol.primitives import AttributeKey

AUDIO_EXT = {".flac", ".mp3", ".wav", ".aiff", ".aif", ".ogg", ".opus", ".m4a", ".ape", ".wv"}


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[\[\(\{].*?[\]\)\}]", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def basename(remote_path: str) -> str:
    return remote_path.replace("/", "\\").split("\\")[-1]


def parent_dir(remote_path: str) -> str:
    parts = remote_path.replace("/", "\\").split("\\")
    return "\\".join(parts[:-1]) if len(parts) > 1 else ""


def extension(remote_path: str) -> str:
    return Path(basename(remote_path)).suffix.lower().lstrip(".")


def bitrate_of(item) -> int:
    try:
        attrs = item.get_attribute_map()
        return int(attrs.get(AttributeKey.BITRATE) or 0)
    except Exception:
        return 0


@dataclass
class FolderCandidate:
    username: str
    remote_dir: str
    files: list = field(default_factory=list)
    score: float = 0.0
    reason: str = ""


def build_queries(artist: str, album: str, year: str | None) -> list[str]:
    artist_q = normalize(artist)
    album_q = normalize(album)
    queries = []
    if year and year.isdigit() and not year.startswith("2026"):
        queries.append(f"{artist_q} {album_q} {year}")
    queries.append(f"{artist_q} {album_q}")
    seen: set[str] = set()
    out = []
    for q in queries:
        key = normalize(q)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def score_folder(
    candidate: FolderCandidate,
    artist: str,
    album: str,
    track_titles: list[str],
    preferred_extensions: list[str],
    min_filename_ratio: float,
    track_count_tolerance: int,
    min_mp3_bitrate: int,
) -> FolderCandidate:
    audio = [f for f in candidate.files if extension(f.filename) in AUDIO_EXT or extension(f.filename) in preferred_extensions]
    if not audio:
        candidate.reason = "no audio"
        return candidate

    exts = {extension(f.filename) for f in audio}
    ext_rank = 0
    for i, pref in enumerate(preferred_extensions):
        if pref in exts:
            ext_rank = len(preferred_extensions) - i
            break
    if ext_rank == 0:
        candidate.reason = f"unwanted types {sorted(exts)}"
        return candidate

    if "mp3" in exts and "flac" not in exts:
        rates = [bitrate_of(f) for f in audio if extension(f.filename) == "mp3"]
        rates = [r for r in rates if r > 0]
        if rates and max(rates) < min_mp3_bitrate:
            candidate.reason = f"mp3 bitrate {max(rates)} < {min_mp3_bitrate}"
            return candidate

    expected = len(track_titles) or 0
    if expected and abs(len(audio) - expected) > track_count_tolerance:
        candidate.reason = f"track count {len(audio)} vs {expected}"
        return candidate

    names = [Path(basename(f.filename)).stem for f in audio]
    if track_titles:
        hits = 0
        for title in track_titles:
            if any(similarity(title, name) >= min_filename_ratio for name in names):
                hits += 1
        title_score = hits / max(len(track_titles), 1)
        if title_score < 0.4:
            candidate.reason = f"title match {title_score:.2f}"
            return candidate
    else:
        title_score = 0.5

    folder_blob = normalize(f"{candidate.remote_dir} {names[0] if names else ''}")
    album_hit = similarity(album, folder_blob)
    artist_hit = similarity(artist, folder_blob)
    if album_hit < 0.25 and artist_hit < 0.2:
        if title_score < 0.7:
            candidate.reason = "folder does not look like the album"
            return candidate

    candidate.files = audio
    candidate.score = (
        ext_rank * 10
        + title_score * 8
        + album_hit * 3
        + artist_hit * 2
        + min(len(audio), expected or len(audio)) * 0.1
    )
    candidate.reason = "ok"
    return candidate


def group_results(results, ignored_users: set[str]) -> list[FolderCandidate]:
    buckets: dict[tuple[str, str], FolderCandidate] = {}
    for result in results:
        username = getattr(result, "username", "") or ""
        if username.lower() in ignored_users:
            continue
        items = list(getattr(result, "shared_items", None) or [])
        by_dir: dict[str, list] = defaultdict(list)
        for item in items:
            filename = getattr(item, "filename", "")
            if not filename:
                continue
            by_dir[parent_dir(filename)].append(item)
        for remote_dir, files in by_dir.items():
            key = (username, remote_dir)
            if key not in buckets:
                buckets[key] = FolderCandidate(username=username, remote_dir=remote_dir, files=[])
            buckets[key].files.extend(files)
    return list(buckets.values())
