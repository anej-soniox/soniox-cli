import click
from simple_term_menu import TerminalMenu

import sys

from soniox_cli.cache import delete_cache, get_cached_meta, get_cached_transcript, is_terminal, save
from soniox_cli.client import get_client
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
    with Spinner(f"Fetching {transcription_id}..."):
        tx = client.stt.get(transcription_id)
        meta = _tx_to_meta(tx)

    if tx.status == "error":
        save(transcription_id, meta)
        return None

    if tx.status != "completed":
        click.echo(f"  Status: {tx.status} (not ready yet)")
        return None

    with Spinner("Downloading transcript..."):
        text = client.stt.get_transcript(transcription_id).text

    save(transcription_id, meta, text)
    return text


def _copy_to_clipboard(text: str) -> None:
    import base64

    encoded = base64.b64encode(text.encode()).decode()
    sys.stdout.write(f"\033]52;c;{encoded}\a")
    sys.stdout.flush()


def _show_transcription(tx_id: str) -> bool:
    """Show transcription detail view. Returns True if deleted."""
    meta = get_cached_meta(tx_id)
    text = get_cached_transcript(tx_id)

    copied_text = False
    copied_json = False

    while True:
        click.clear()
        if meta:
            click.echo(_format_meta(meta))
        click.echo("─" * 60)

        if meta and meta.get("status") == "error":
            click.echo("[FAILED]")
        elif text:
            click.echo(text)
        else:
            click.echo("No transcript available.")

        click.echo()
        items = [
            "Back",
            "Copy transcript ✓" if copied_text else "Copy transcript",
            "Copy JSON ✓" if copied_json else "Copy JSON",
            "Delete",
        ]
        menu = TerminalMenu(items)
        choice = menu.show()

        if choice is None or choice == 0:
            return False

        if choice == 1:
            if text:
                _copy_to_clipboard(text)
                copied_text = True
                copied_json = False

        if choice == 2:
            if meta:
                import json
                _copy_to_clipboard(json.dumps(meta, indent=2, default=str))
                copied_json = True
                copied_text = False

        if choice == 3:
            confirm = TerminalMenu(["Yes", "No"], title=f"\nDelete transcription {tx_id}?\n")
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

    with Spinner("Loading transcriptions..."):
        result = client.stt.list(limit=PAGE_SIZE)

    if not result.transcriptions:
        click.echo("No transcriptions found.")
        return

    tx_list = [(t.id, t.status, t.created_at) for t in result.transcriptions]
    next_cursor = result.next_page_cursor

    while True:
        entries = [truncate(_build_entry(tx_id, status, created_at)) for tx_id, status, created_at in tx_list]
        if next_cursor:
            entries.append("Load more...")
        entries.append("Back")

        menu = TerminalMenu(entries, title="\nTranscriptions\n")
        choice = menu.show()

        if choice is None or choice == len(entries) - 1:
            break

        if next_cursor and choice == len(entries) - 2:
            with Spinner("Loading more..."):
                result = client.stt.list(limit=PAGE_SIZE, cursor=next_cursor)
            tx_list.extend((t.id, t.status, t.created_at) for t in result.transcriptions)
            next_cursor = result.next_page_cursor
            continue

        tx_id, status, _created_at = tx_list[choice]

        if not is_terminal(tx_id):
            _fetch_and_cache(tx_id)

        if is_terminal(tx_id):
            deleted = _show_transcription(tx_id)
            if deleted:
                tx_list.pop(choice)
                if not tx_list:
                    click.echo("No transcriptions remaining.")
                    break
