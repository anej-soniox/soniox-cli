import json
from pathlib import Path
from typing import Any

CACHE_DIR = Path.home() / ".soniox" / "transcripts"


def _tx_dir(transcription_id: str) -> Path:
    return CACHE_DIR / transcription_id


def get_cached_transcript(transcription_id: str) -> str | None:
    path = _tx_dir(transcription_id) / "transcript.txt"
    if path.exists():
        return path.read_text()
    return None


def get_cached_meta(transcription_id: str) -> dict[str, Any] | None:
    path = _tx_dir(transcription_id) / "meta.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def is_terminal(transcription_id: str) -> bool:
    meta = get_cached_meta(transcription_id)
    if meta is None:
        return False
    return meta.get("status") in ("completed", "error")


def save(transcription_id: str, meta: dict[str, Any], transcript: str | None = None) -> None:
    d = _tx_dir(transcription_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    if transcript is not None:
        (d / "transcript.txt").write_text(transcript)


def delete_cache(transcription_id: str) -> None:
    import shutil

    d = _tx_dir(transcription_id)
    if d.exists():
        shutil.rmtree(d)
