from __future__ import annotations

from typing import Any

import httpx


class LidarrClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = self._client.get(f"/api/v1{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        r = self._client.post(f"/api/v1{path}", json=payload)
        r.raise_for_status()
        return r.json() if r.content else None

    def ping(self) -> dict[str, Any]:
        r = self._client.get("/api/v1/system/status")
        r.raise_for_status()
        return r.json()

    def wanted_missing(self, page_size: int = 50) -> list[dict[str, Any]]:
        albums: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._get(
                "/wanted/missing",
                params={
                    "page": page,
                    "pageSize": page_size,
                    "monitored": True,
                    "includeArtist": True,
                    "sortKey": "releaseDate",
                    "sortDirection": "descending",
                },
            )
            records = data.get("records") or []
            albums.extend(records)
            total_pages = int(data.get("totalPages") or 1)
            if page >= total_pages:
                break
            page += 1
        return albums

    def tracks_for_album(self, album_id: int) -> list[dict[str, Any]]:
        return self._get("/track", params={"albumId": album_id}) or []

    def scan_downloaded(self, path: str) -> Any:
        return self._post(
            "/command",
            {"name": "DownloadedAlbumsScan", "path": path, "importMode": "Move"},
        )
