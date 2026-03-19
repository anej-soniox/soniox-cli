from pathlib import Path

import click
from simple_term_menu import TerminalMenu

from soniox_cli.cache import save
from soniox_cli.client import get_client
from soniox_cli.render import render_transcript, render_translation
from soniox_cli.settings import load_settings, settings_to_config, show_settings_form
from soniox_cli.spinner import Spinner
from soniox_cli.util import truncate

AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".m4a",
    ".aac",
    ".wma",
    ".webm",
    ".mp4",
}
_LAST_DIR_FILE = Path.home() / ".soniox" / "last_browse_dir"

PAGE_SIZE = 50


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
    cursor = 1  # start on ".."

    while True:
        entries: list[str] = ["Back", ".."]
        paths: list[Path] = []

        dirs = sorted(
            p for p in cwd.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        files = sorted(
            p
            for p in cwd.iterdir()
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        )

        for d in dirs:
            entries.append(f"📁 {d.name}/")
            paths.append(d)
        for f in files:
            size_kb = f.stat().st_size / 1024
            entries.append(f"   {f.name}  ({size_kb:.0f} KB)")
            paths.append(f)

        if not dirs and not files:
            entries.append("   (no audio files)")

        menu = TerminalMenu(entries, title=f"\nSoniox CLI › Browse › {cwd}\n", cursor_index=cursor)
        choice = menu.show()

        if choice is None or choice == 0:
            return None
        if choice == 1:
            cursor = 1  # keep cursor on ".." when navigating up
            cwd = cwd.parent
            continue

        # "(no audio files)" placeholder
        if not paths:
            continue

        selected = paths[choice - 2]
        if selected.is_dir():
            cursor = 1
            cwd = selected
        else:
            _save_last_dir(selected.parent)
            return selected


def _tx_to_meta(tx: object) -> dict:
    return {
        "id": tx.id,
        "status": tx.status,
        "model": tx.model,
        "created_at": str(tx.created_at),
        "filename": tx.filename,
        "audio_duration_ms": tx.audio_duration_ms,
        "error_type": tx.error_type,
        "error_message": tx.error_message,
    }


def _transcribe_file_id(file_id: str) -> None:
    client = get_client()
    settings = load_settings()
    config = settings_to_config(settings)

    with Spinner("Transcribing...", title="Soniox CLI › Transcribe") as sp:
        result = client.stt.transcribe(
            file_id=file_id, model=settings.model, config=config
        )
        tx = client.stt.wait(result.id)

    if tx.status != "completed":
        click.echo(f"Transcription failed: {tx.status}")
        return

    transcript_result = client.stt.get_transcript(tx.id)
    tokens = [t.model_dump() for t in transcript_result.tokens]
    text = render_transcript(tokens)
    translation = render_translation(tokens)

    meta = _tx_to_meta(tx)
    save(tx.id, meta, text, tokens=tokens, translation=translation)

    click.echo(f"\n{text}")
    if translation:
        click.echo(f"\n─── Translation ───\n{translation}")


def _upload_and_transcribe() -> None:
    path = _browse_for_file()
    if path is None:
        return

    client = get_client()
    settings = load_settings()
    config = settings_to_config(settings)

    with Spinner(f"Uploading {path.name}...", title="Soniox CLI › Transcribe") as sp:
        uploaded = client.files.upload(file=path)
        sp.update("Transcribing...")
        result = client.stt.transcribe(
            file_id=uploaded.id, model=settings.model, config=config
        )
        tx = client.stt.wait(result.id)

    if tx.status != "completed":
        click.echo(f"Transcription failed: {tx.status}")
        return

    transcript_result = client.stt.get_transcript(tx.id)
    tokens = [t.model_dump() for t in transcript_result.tokens]
    text = render_transcript(tokens)
    translation = render_translation(tokens)

    meta = _tx_to_meta(tx)
    save(tx.id, meta, text, tokens=tokens, translation=translation)

    click.echo(f"\n{text}")
    if translation:
        click.echo(f"\n─── Translation ───\n{translation}")


def _transcribe_uploaded_file() -> None:
    client = get_client()

    with Spinner("Loading files...", title="Soniox CLI › Transcribe › Select file"):
        result = client.files.list(limit=PAGE_SIZE)

    if not result.files:
        click.echo("No uploaded files found.")
        return

    file_list = list(result.files)
    next_cursor = result.next_page_cursor
    cursor = 0

    while True:
        entries = ["Back"]
        entries.extend(
            truncate(f"{f.created_at:%Y-%m-%d %H:%M}  {f.filename}") for f in file_list
        )
        if next_cursor:
            entries.append("Load more...")

        menu = TerminalMenu(
            entries, title="\nSoniox CLI › Transcribe › Select file\n", cursor_index=cursor
        )
        choice = menu.show()

        if choice is None or choice == 0:
            return

        cursor = choice

        if next_cursor and choice == len(entries) - 1:
            with Spinner("Loading more..."):
                result = client.files.list(limit=PAGE_SIZE, cursor=next_cursor)
            file_list.extend(result.files)
            next_cursor = result.next_page_cursor
            continue

        selected = file_list[choice - 1]
        _transcribe_file_id(selected.id)
        return


def transcribe_file() -> None:
    menu_items = [
        "Back",
        "Transcribe uploaded file",
        "Upload and transcribe",
        "Config",
    ]

    cursor = 0
    while True:
        menu = TerminalMenu(menu_items, title="\nSoniox CLI › Transcribe\n", cursor_index=cursor)
        choice = menu.show()

        if choice is None or choice == 0:
            return

        cursor = choice

        match choice:
            case 1:
                _transcribe_uploaded_file()
            case 2:
                _upload_and_transcribe()
            case 3:
                show_settings_form()
