"""Asynchronous TeddyCloud API client and Ogg/Opus duration parser."""

from __future__ import annotations

import asyncio
import json
import struct
from typing import Any
from urllib.parse import quote, urlencode, urljoin

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import MAX_TAIL_WINDOW, TAIL_WINDOW


class TeddyCloudError(Exception):
    """Base TeddyCloud client error."""


class TeddyCloudConnectionError(TeddyCloudError):
    """TeddyCloud could not be reached."""


class TeddyCloudDataError(TeddyCloudError):
    """TeddyCloud returned invalid or unsupported data."""


class TeddyCloudClient:
    """Small client for the endpoints needed by the integration."""

    def __init__(self, session: ClientSession, host: str) -> None:
        self._session = session
        self.host = host.rstrip("/") + "/"

    def _url(self, path: str) -> str:
        return urljoin(self.host, path.lstrip("/"))

    async def _json(self, path: str) -> Any:
        try:
            async with asyncio.timeout(20):
                response = await self._session.get(self._url(path))
                async with response:
                    response.raise_for_status()
                    # TeddyCloud uses text/json and application/octet-stream.
                    return json.loads(await response.text(encoding="utf-8"))
        except (TimeoutError, ClientError) as err:
            raise TeddyCloudConnectionError(str(err)) from err
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise TeddyCloudDataError(f"Invalid JSON from {path}: {err}") from err

    async def async_get_tag_index(self) -> list[dict[str, Any]]:
        """Fetch tag index."""
        payload = await self._json("/api/getTagIndex")
        if not isinstance(payload, dict) or not isinstance(payload.get("tags"), list):
            raise TeddyCloudDataError("getTagIndex has no tags list")
        return payload["tags"]

    async def async_get_custom_metadata(self) -> list[dict[str, Any]]:
        """Fetch the unchanged custom metadata JSON."""
        payload = await self._json("/api/toniesCustomJson")
        if not isinstance(payload, list):
            raise TeddyCloudDataError("toniesCustomJson is not a list")
        return payload

    async def async_get_library_files(self) -> list[dict[str, Any]]:
        """Recursively enumerate the complete TeddyCloud library."""
        queue = ["/"]
        seen: set[str] = set()
        files: list[dict[str, Any]] = []
        while queue:
            directory = queue.pop(0)
            if directory in seen:
                continue
            seen.add(directory)
            query = urlencode({"path": directory, "special": "library"})
            payload = await self._json(f"/api/fileIndexV2?{query}")
            if not isinstance(payload, dict) or not isinstance(
                payload.get("files"), list
            ):
                raise TeddyCloudDataError(
                    f"fileIndexV2 has no files list for {directory}"
                )
            for entry in payload["files"]:
                if not isinstance(entry, dict) or entry.get("name") in {".", ".."}:
                    continue
                name = str(entry.get("name", ""))
                child = f"/{name}" if directory == "/" else f"{directory}/{name}"
                if entry.get("isDir"):
                    queue.append(child)
                else:
                    record = dict(entry)
                    record["path"] = child
                    files.append(record)
        return files

    @staticmethod
    def library_audio_url(path: str) -> str:
        """Build the read-only raw Ogg URL for a library TAF."""
        return f"/content{quote(path, safe='/')}?ogg=true&special=library"

    async def _range(
        self, path: str, start: int, end: int
    ) -> tuple[bytes, ClientResponse]:
        """Fetch an explicit byte range.

        TeddyCloud must not be queried with a range beginning at byte zero.
        """
        if start < 1 or end < start:
            raise TeddyCloudDataError("Invalid byte range")
        headers = {"Range": f"bytes={start}-{end}"}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with asyncio.timeout(20):
                    response = await self._session.get(
                        self._url(path), headers=headers
                    )
                    async with response:
                        body = await response.read()
                        if response.status != 206:
                            raise TeddyCloudDataError(
                                f"Range request returned HTTP {response.status}"
                            )
                        return body, response
            except (TimeoutError, ClientError) as err:
                last_error = err
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise TeddyCloudConnectionError(str(last_error)) from last_error

    async def async_runtime(self, audio_url: str) -> float:
        """Determine an Ogg/Opus runtime without downloading the full stream."""
        path = (
            audio_url
            if "ogg=true" in audio_url
            else _with_skip_header(audio_url)
        )
        prefix, response = await self._range(path, 1, 255)
        total = _content_range_total(response.headers.get("Content-Range"))
        # Byte zero is known to be "O" from the validated Ogg capture pattern.
        # It is reconstructed because TeddyCloud mishandles ranges starting at 0.
        pre_skip, serial = _parse_opus_head(b"O" + prefix)

        window = min(TAIL_WINDOW, max(total - 1, 1))
        while window <= min(MAX_TAIL_WINDOW, total - 1):
            start = max(1, total - window)
            tail, _ = await self._range(path, start, total - 1)
            final_granule = _last_complete_granule(tail, serial)
            if final_granule is not None:
                duration = (final_granule - pre_skip) / 48_000
                if duration <= 0:
                    raise TeddyCloudDataError("Calculated duration is not positive")
                return duration
            if window == min(MAX_TAIL_WINDOW, total - 1):
                break
            window = min(window * 2, MAX_TAIL_WINDOW, total - 1)

        raise TeddyCloudDataError("No complete final Ogg page found")

    async def async_assign_audio(self, ruid: str, library_path: str) -> None:
        """Assign one library TAF to a physical Custom Tonie."""
        source = f"lib://{library_path.lstrip('/')}"
        try:
            async with asyncio.timeout(20):
                response = await self._session.post(
                    self._url(f"/content/json/set/{ruid.lower()}"),
                    data={"source": source, "nocloud": "true"},
                )
                async with response:
                    body = await response.text()
                    if response.status >= 400:
                        raise TeddyCloudDataError(
                            f"Assignment returned HTTP {response.status}: {body}"
                        )
                    if body.strip().casefold() in {"error", "failed"}:
                        raise TeddyCloudDataError(
                            f"Assignment was rejected: {body.strip()}"
                        )
        except (TimeoutError, ClientError) as err:
            raise TeddyCloudConnectionError(str(err)) from err


def _with_skip_header(audio_url: str) -> str:
    """Ensure the directly parseable audio representation is requested."""
    if "skip_header=true" in audio_url:
        return audio_url
    separator = "&" if "?" in audio_url else "?"
    return f"{audio_url}{separator}skip_header=true"


def _content_range_total(value: str | None) -> int:
    """Extract total length from a Content-Range response header."""
    if not value or "/" not in value:
        raise TeddyCloudDataError("Missing Content-Range total")
    try:
        total = int(value.rsplit("/", 1)[1])
    except ValueError as err:
        raise TeddyCloudDataError("Invalid Content-Range total") from err
    if total < 256:
        raise TeddyCloudDataError("Audio stream is too small")
    return total


def _parse_opus_head(data: bytes) -> tuple[int, int]:
    """Return Opus pre-skip and the containing Ogg stream serial."""
    marker = data.find(b"OpusHead")
    ogg = data.rfind(b"OggS", 0, marker)
    if marker < 0 or ogg < 0 or marker + 12 > len(data):
        raise TeddyCloudDataError("Ogg/Opus header not found")
    pre_skip = struct.unpack_from("<H", data, marker + 10)[0]
    serial = struct.unpack_from("<I", data, ogg + 14)[0]
    return pre_skip, serial


def _last_complete_granule(data: bytes, serial: int) -> int | None:
    """Find the last structurally complete Ogg page for a stream."""
    last: int | None = None
    position = 0
    while True:
        position = data.find(b"OggS", position)
        if position < 0:
            return last
        if position + 27 > len(data) or data[position + 4] != 0:
            position += 1
            continue
        segment_count = data[position + 26]
        table_end = position + 27 + segment_count
        if table_end > len(data):
            position += 1
            continue
        page_end = table_end + sum(data[position + 27 : table_end])
        if page_end > len(data):
            position += 1
            continue
        page_serial = struct.unpack_from("<I", data, position + 14)[0]
        if page_serial == serial:
            last = struct.unpack_from("<Q", data, position + 6)[0]
        position = page_end
