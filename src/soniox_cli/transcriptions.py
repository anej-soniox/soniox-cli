import click
from simple_term_menu import TerminalMenu

from soniox_cli.cache import (
    delete_cache,
    get_cached_meta,
    get_cached_tokens,
    get_cached_transcript,
    get_cached_translation,
    is_terminal,
    save,
)
from soniox_cli.client import get_client
from soniox_cli.render import ViewMode, render_transcript, render_translation, render_unified
from soniox_cli.spinner import Spinner
from soniox_cli.util import truncate

PAGE_SIZE = 50


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


def _format_duration(ms: int | None) -> str:
    if ms is None:
        return "—"
    s = ms // 1000
    return f"{s // 60}m {s % 60}s"


def _format_meta(meta: dict) -> str:
    lines = [
        f"ID:        {meta['id']}",
        f"Status:    {meta['status']}",
        f"Model:     {meta['model']}",
        f"File:      {meta['filename']}",
        f"Duration:  {_format_duration(meta.get('audio_duration_ms'))}",
        f"Created:   {meta['created_at']}",
    ]
    if meta.get("error_message"):
        lines.append(f"Error:     {meta['error_message']}")
    return "\n".join(lines)


def _fetch_and_cache(transcription_id: str) -> str | None:
    client = get_client()
    with Spinner(f"Fetching {transcription_id}...", title="Soniox CLI › Transcriptions"):
        tx = client.stt.get(transcription_id)
        meta = _tx_to_meta(tx)

    if tx.status == "error":
        save(transcription_id, meta)
        return None

    if tx.status != "completed":
        click.echo(f"  Status: {tx.status} (not ready yet)")
        return None

    with Spinner("Downloading transcript...", title="Soniox CLI › Transcriptions"):
        result = client.stt.get_transcript(transcription_id)

    tokens = [t.model_dump() for t in result.tokens]
    text = render_transcript(tokens)
    translation = render_translation(tokens)

    save(transcription_id, meta, text, tokens=tokens, translation=translation)
    return text


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    import subprocess

    import pyperclip

    # pyperclip's wl-copy backend hangs because it calls communicate()
    # which waits for wl-copy's daemon process. Patch it to write + close
    # stdin without waiting.
    if pyperclip._executable_exists("wl-copy"):
        try:
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, close_fds=True)
            p.stdin.write(text.encode("utf-8"))
            p.stdin.close()
            return True
        except (OSError, FileNotFoundError) as e:
            click.echo(f"\nClipboard error: {e}")
            click.pause()
            return False

    try:
        pyperclip.copy(text)
        return True
    except pyperclip.PyperclipException as e:
        click.echo(f"\n{e}")
        click.pause()
        return False


def _get_display_text(
    view_mode: ViewMode,
    text: str | None,
    translation: str | None,
    tokens: list[dict] | None,
) -> str | None:
    """Return the text to display for the current view mode."""
    match view_mode:
        case ViewMode.TRANSCRIPT:
            return text
        case ViewMode.TRANSLATION:
            return translation
        case ViewMode.UNIFIED:
            if tokens:
                return render_unified(tokens)
            return text


def _view_label(mode: ViewMode, current: ViewMode) -> str:
    marker = "●" if mode == current else "○"
    return f"{marker} {mode.value}"


def _show_transcription(tx_id: str) -> bool:
    """Show transcription detail view. Returns True if deleted."""
    meta = get_cached_meta(tx_id)
    text = get_cached_transcript(tx_id)
    translation = get_cached_translation(tx_id)
    tokens = get_cached_tokens(tx_id) if translation else None
    has_translation = translation is not None

    view_mode = ViewMode.UNIFIED if has_translation else ViewMode.TRANSCRIPT
    copied_text = False
    copied_json = False
    copied_translation = False

    while True:
        click.clear()
        if meta:
            click.echo(_format_meta(meta))
        click.echo("─" * 60)

        if meta and meta.get("status") == "error":
            click.echo("[FAILED]")
        else:
            display = _get_display_text(view_mode, text, translation, tokens)
            if display:
                click.echo(display)
            else:
                click.echo("No transcript available.")

        click.echo()
        items = ["Back"]
        if has_translation:
            for mode in ViewMode:
                items.append(_view_label(mode, view_mode))
        items.append("Copy transcript ✓" if copied_text else "Copy transcript")
        items.append("Copy JSON ✓" if copied_json else "Copy JSON")
        if has_translation:
            items.append("Copy translation ✓" if copied_translation else "Copy translation")
        items.append("Delete")

        menu = TerminalMenu(items)
        choice = menu.show()

        if choice is None:
            return False

        selected = items[choice]

        if selected == "Back":
            return False

        if selected.startswith("●") or selected.startswith("○"):
            for mode in ViewMode:
                if selected.endswith(mode.value):
                    view_mode = mode
                    break

        elif selected.startswith("Copy transcript"):
            if text and _copy_to_clipboard(text):
                copied_text = True
                copied_json = False
                copied_translation = False

        elif selected.startswith("Copy JSON"):
            cached_tokens = get_cached_tokens(tx_id)
            if cached_tokens:
                import json

                if _copy_to_clipboard(json.dumps(cached_tokens, indent=2, default=str)):
                    copied_json = True
                    copied_text = False
                    copied_translation = False

        elif selected.startswith("Copy translation"):
            if translation and _copy_to_clipboard(translation):
                copied_translation = True
                copied_text = False
                copied_json = False

        elif selected == "Delete":
            confirm = TerminalMenu(
                ["Yes", "No"], title=f"\nSoniox CLI › Delete transcription {tx_id}?\n"
            )
            if confirm.show() == 0:
                client = get_client()
                with Spinner(f"Deleting {tx_id}..."):
                    client.stt.delete(tx_id)
                delete_cache(tx_id)
                click.echo(f"Deleted {tx_id}")
                return True


def _format_date(dt: object) -> str:
    return f"{dt:%Y-%m-%d %H:%M}"


def _build_entry(tx_id: str, status: str, created_at: object) -> str:
    date = _format_date(created_at)
    cached_text = get_cached_transcript(tx_id)
    if cached_text:
        preview = cached_text[:50].replace("\n", " ")
        return f"{date}  {tx_id}  {preview}..."

    cached_meta = get_cached_meta(tx_id)
    if cached_meta and cached_meta.get("status") == "error":
        return f"{date}  {tx_id}  [FAILED]"

    if status == "error":
        return f"{date}  {tx_id}  [FAILED]"
    if status == "completed":
        return f"{date}  {tx_id}  [not fetched]"
    return f"{date}  {tx_id}  [{status}]"


def list_transcriptions() -> None:
    client = get_client()

    with Spinner("Loading transcriptions...", title="Soniox CLI › Transcriptions"):
        result = client.stt.list(limit=PAGE_SIZE)

    if not result.transcriptions:
        click.echo("No transcriptions found.")
        return

    tx_list = [(t.id, t.status, t.created_at) for t in result.transcriptions]
    next_cursor = result.next_page_cursor

    cursor = 0
    while True:
        entries = ["Back"]
        entries.extend(
            truncate(_build_entry(tx_id, status, created_at))
            for tx_id, status, created_at in tx_list
        )
        if next_cursor:
            entries.append("Load more...")

        menu = TerminalMenu(entries, title="\nSoniox CLI › Transcriptions\n", cursor_index=cursor)
        choice = menu.show()

        if choice is None or choice == 0:
            break

        cursor = choice

        if next_cursor and choice == len(entries) - 1:
            with Spinner("Loading more..."):
                result = client.stt.list(limit=PAGE_SIZE, cursor=next_cursor)
            tx_list.extend(
                (t.id, t.status, t.created_at) for t in result.transcriptions
            )
            next_cursor = result.next_page_cursor
            continue

        tx_idx = choice - 1
        tx_id, status, _created_at = tx_list[tx_idx]

        if not is_terminal(tx_id):
            _fetch_and_cache(tx_id)

        if is_terminal(tx_id):
            deleted = _show_transcription(tx_id)
            if deleted:
                tx_list.pop(tx_idx)
                if not tx_list:
                    click.echo("No transcriptions remaining.")
                    break
