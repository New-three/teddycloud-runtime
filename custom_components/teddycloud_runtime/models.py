"""Data models for TeddyCloud Runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TonieMetadata:
    """Metadata from toniesCustomJson."""

    model: str
    audio_ids: tuple[str, ...]
    hashes: tuple[str, ...]
    series: str
    episode: str
    picture: str
    tracks: tuple[str, ...]


@dataclass(slots=True)
class LibraryItem:
    """One TeddyCloud tag-index item."""

    ruid: str
    uid: str
    audio_url: str
    exists: bool
    nocloud: bool
    source: str
    track_count: int
    model: str
    metadata: TonieMetadata | None = None


@dataclass(slots=True)
class AudioFile:
    """One physical TAF file in the TeddyCloud audio library."""

    path: str
    audio_id: str
    sha1_hash: str
    size: int
    valid: bool
    track_count: int
    metadata: TonieMetadata | None = None
    runtime_seconds: float | None = None

    @property
    def cache_key(self) -> str:
        """Return a stable identity that changes when content changes."""
        return f"{self.audio_id}|{self.sha1_hash}|{self.size}"


@dataclass(slots=True)
class RuntimeData:
    """Coordinator data exposed to entities."""

    items: dict[str, LibraryItem] = field(default_factory=dict)
    audio_files: dict[str, AudioFile] = field(default_factory=dict)
    metadata_by_audio_id: dict[str, TonieMetadata] = field(default_factory=dict)
    metadata_by_model: dict[str, TonieMetadata] = field(default_factory=dict)
    cache_entries: int = 0
    cache_state: str = "empty"
    last_error: str | None = None
    raw_custom_count: int = 0

    @property
    def custom_runtime_count(self) -> int:
        """Number of custom metadata entries with a measured library file."""
        return sum(
            audio.metadata is not None and audio.runtime_seconds is not None
            for audio in self.audio_files.values()
        )

    def current_metadata(self, audio_id: str | None) -> TonieMetadata | None:
        """Return metadata for a current audio ID."""
        if not audio_id:
            return None
        return self.metadata_by_audio_id.get(str(audio_id))
