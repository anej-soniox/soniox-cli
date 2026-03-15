from pathlib import Path

import click
from simple_term_menu import TerminalMenu

from soniox_cli.client import get_client
from soniox_cli.spinner import Spinner

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".webm", ".mp4"}
_LAST_DIR_FILE = Path.home() / ".soniox" / "last_browse_dir"


def _get_start_dir() -> Path:
    if _LAST_DIR_FILE.exists():
        saved = Path(_LAST_DIR_FILE.read_text().strip())
        if saved.is_dir():
            return saved
    return Path.cwd()


def _save_last_dir(directory: Path) -> None:
    _LAST_DIR_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_DIR_FILE.write_text(str(directory))


def _browse_for_file() -> Path | None:
    cwd = _get_start_dir()

    while True:
        entries: list[str] = [".."]
        paths: list[Path] = []

        dirs = sorted(p for p in cwd.iterdir() if p.is_dir() and not p.name.startswith("."))
        files = sorted(p for p in cwd.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS)

        for d in dirs:
            entries.append(f"📁 {d.name}/")
            paths.append(d)
        for f in files:
            size_kb = f.stat().st_size / 1024
            entries.append(f"   {f.name}  ({size_kb:.0f} KB)")
            paths.append(f)

        if not dirs and not files:
            entries.append("   (no audio files)")

        menu = TerminalMenu(entries, title=f"\n{cwd}\n")
        choice = menu.show()

        if choice is None:
            return None
        if choice == 0:
            cwd = cwd.parent
            continue

        # "(no audio files)" placeholder
        if not paths:
            continue

        selected = paths[choice - 1]
        if selected.is_dir():
            cwd = selected
        else:
            _save_last_dir(selected.parent)
            return selected


def transcribe_file() -> None:
    path = _browse_for_file()
    if path is None:
        return

    client = get_client()

    with Spinner(f"Uploading {path.name}...") as sp:
        uploaded = client.files.upload(file=path)
        sp.update("Transcribing...")
        result = client.stt.transcribe(file_id=uploaded.id)
        tx = client.stt.wait(result.id)

    if tx.status != "completed":
        click.echo(f"Transcription failed: {tx.status}")
        return

    text = client.stt.get_transcript(tx.id).text
    click.echo(f"\n{text}")
