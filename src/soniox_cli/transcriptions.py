import click
from simple_term_menu import TerminalMenu

from soniox_cli.cache import get_cached_meta, get_cached_transcript, is_terminal, save
from soniox_cli.client import get_client
from soniox_cli.spinner import Spinner

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


def _show_transcription(tx_id: str) -> None:
    meta = get_cached_meta(tx_id)
    text = get_cached_transcript(tx_id)

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
    click.pause("Press any key to go back...")


def _build_entry(tx_id: str, status: str) -> str:
    cached_text = get_cached_transcript(tx_id)
    if cached_text:
        preview = cached_text[:50].replace("\n", " ")
        return f"{tx_id}  {preview}..."

    cached_meta = get_cached_meta(tx_id)
    if cached_meta and cached_meta.get("status") == "error":
        return f"{tx_id}  [FAILED]"

    if status == "error":
        return f"{tx_id}  [FAILED]"
    if status == "completed":
        return f"{tx_id}  [not fetched]"
    return f"{tx_id}  [{status}]"


def list_transcriptions() -> None:
    client = get_client()

    with Spinner("Loading transcriptions..."):
        result = client.stt.list(limit=PAGE_SIZE)

    if not result.transcriptions:
        click.echo("No transcriptions found.")
        return

    tx_list = [(t.id, t.status) for t in result.transcriptions]
    next_cursor = result.next_page_cursor

    while True:
        entries = [_build_entry(tx_id, status) for tx_id, status in tx_list]
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
            tx_list.extend((t.id, t.status) for t in result.transcriptions)
            next_cursor = result.next_page_cursor
            continue

        tx_id, status = tx_list[choice]

        if not is_terminal(tx_id):
            _fetch_and_cache(tx_id)

        if is_terminal(tx_id):
            _show_transcription(tx_id)
