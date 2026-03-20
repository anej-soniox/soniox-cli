import json
from pathlib import Path

import click

from soniox_cli.cache import (
    delete_cache,
    get_cached_tokens,
    get_cached_transcript,
    get_cached_translation,
    is_terminal,
    save,
)
from soniox_cli.client import get_client
from soniox_cli.render import render_transcript, render_translation
from soniox_cli.settings import (
    TranscriptionSettings,
    load_settings,
    save_settings,
    settings_to_config,
)


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


# ── Transcriptions ──────────────────────────────────────────────


@click.group("transcriptions")
def transcriptions_group() -> None:
    """Manage transcriptions."""


@transcriptions_group.command("list")
@click.option("--limit", default=50, show_default=True, help="Max items to return.")
@click.option("--cursor", default=None, help="Pagination cursor.")
@click.option("--json-output", "--json", "json_output", is_flag=True, help="Output JSON.")
def transcriptions_list(limit: int, cursor: str | None, json_output: bool) -> None:
    """List transcriptions."""
    client = get_client()
    kwargs: dict = {"limit": limit}
    if cursor:
        kwargs["cursor"] = cursor
    result = client.stt.list(**kwargs)

    if json_output:
        data = {
            "transcriptions": [
                {
                    "id": t.id,
                    "status": t.status,
                    "model": t.model,
                    "created_at": str(t.created_at),
                    "filename": t.filename,
                    "audio_duration_ms": t.audio_duration_ms,
                }
                for t in result.transcriptions
            ],
            "next_page_cursor": result.next_page_cursor,
        }
        click.echo(json.dumps(data, indent=2))
    else:
        if not result.transcriptions:
            click.echo("No transcriptions found.")
            return
        for t in result.transcriptions:
            click.echo(f"{t.created_at:%Y-%m-%d %H:%M}  {t.id}  {t.status:10s}  {t.filename}")
        if result.next_page_cursor:
            click.echo(f"\nNext cursor: {result.next_page_cursor}", err=True)


@transcriptions_group.command("get")
@click.argument("transcription_id")
@click.option("--json-output", "--json", "json_output", is_flag=True, help="Output full token JSON.")
@click.option("--translation", is_flag=True, help="Print translation instead of transcript.")
def transcriptions_get(transcription_id: str, json_output: bool, translation: bool) -> None:
    """Get transcript text for a transcription."""
    client = get_client()

    if json_output:
        tokens = get_cached_tokens(transcription_id)
        if tokens is None:
            click.echo("Fetching transcript...", err=True)
            result = client.stt.get_transcript(transcription_id)
            tokens = [t.model_dump() for t in result.tokens]
            # Cache while we're at it
            tx = client.stt.get(transcription_id)
            meta = _tx_to_meta(tx)
            text = render_transcript(tokens)
            trans = render_translation(tokens)
            save(transcription_id, meta, text, tokens=tokens, translation=trans)
        click.echo(json.dumps(tokens, indent=2, default=str))
        return

    if translation:
        trans = get_cached_translation(transcription_id)
        if trans is None:
            click.echo("Fetching transcript...", err=True)
            result = client.stt.get_transcript(transcription_id)
            tokens = [t.model_dump() for t in result.tokens]
            tx = client.stt.get(transcription_id)
            meta = _tx_to_meta(tx)
            text = render_transcript(tokens)
            trans = render_translation(tokens)
            save(transcription_id, meta, text, tokens=tokens, translation=trans)
        if trans:
            click.echo(trans)
        else:
            click.echo("No translation available.")
        return

    text = get_cached_transcript(transcription_id)
    if text is None:
        if not is_terminal(transcription_id):
            click.echo("Fetching transcript...", err=True)
            tx = client.stt.get(transcription_id)
            meta = _tx_to_meta(tx)
            if tx.status != "completed":
                raise click.ClickException(f"Transcription status: {tx.status}")
            result = client.stt.get_transcript(transcription_id)
            tokens = [t.model_dump() for t in result.tokens]
            text = render_transcript(tokens)
            trans = render_translation(tokens)
            save(transcription_id, meta, text, tokens=tokens, translation=trans)
        else:
            raise click.ClickException("Transcript not available (transcription may have failed).")
    click.echo(text)


@transcriptions_group.command("delete")
@click.argument("transcription_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
def transcriptions_delete(transcription_id: str, yes: bool) -> None:
    """Delete a transcription."""
    if not yes:
        click.confirm(f"Delete transcription {transcription_id}?", abort=True)
    client = get_client()
    client.stt.delete(transcription_id)
    delete_cache(transcription_id)
    click.echo(f"Deleted {transcription_id}")


# ── Files ────────────────────────────────────────────────────────


@click.group("files")
def files_group() -> None:
    """Manage uploaded files."""


@files_group.command("list")
@click.option("--limit", default=50, show_default=True, help="Max items to return.")
@click.option("--cursor", default=None, help="Pagination cursor.")
@click.option("--json-output", "--json", "json_output", is_flag=True, help="Output JSON.")
def files_list(limit: int, cursor: str | None, json_output: bool) -> None:
    """List uploaded files."""
    client = get_client()
    kwargs: dict = {"limit": limit}
    if cursor:
        kwargs["cursor"] = cursor
    result = client.files.list(**kwargs)

    if json_output:
        data = {
            "files": [
                {
                    "id": f.id,
                    "filename": f.filename,
                    "size": f.size,
                    "created_at": str(f.created_at),
                }
                for f in result.files
            ],
            "next_page_cursor": result.next_page_cursor,
        }
        click.echo(json.dumps(data, indent=2))
    else:
        if not result.files:
            click.echo("No files found.")
            return
        for f in result.files:
            click.echo(f"{f.created_at:%Y-%m-%d %H:%M}  {f.id}  {f.filename}  {f.size}")
        if result.next_page_cursor:
            click.echo(f"\nNext cursor: {result.next_page_cursor}", err=True)


@files_group.command("upload")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json-output", "--json", "json_output", is_flag=True, help="Output JSON.")
def files_upload(path: Path, json_output: bool) -> None:
    """Upload an audio file."""
    client = get_client()
    click.echo(f"Uploading {path.name}...", err=True)
    uploaded = client.files.upload(file=path)
    if json_output:
        click.echo(json.dumps({"id": uploaded.id, "filename": uploaded.filename}, indent=2))
    else:
        click.echo(uploaded.id)


@files_group.command("delete")
@click.argument("file_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
def files_delete(file_id: str, yes: bool) -> None:
    """Delete an uploaded file."""
    if not yes:
        click.confirm(f"Delete file {file_id}?", abort=True)
    client = get_client()
    client.files.delete(file_id)
    click.echo(f"Deleted {file_id}")


# ── Transcribe ───────────────────────────────────────────────────


@click.command("transcribe")
@click.argument("path", required=False, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--file-id", default=None, help="Transcribe an already-uploaded file (mutually exclusive with PATH).")
@click.option("--model", default=None, help="Override model.")
@click.option("--speaker-diarization/--no-speaker-diarization", default=None, help="Enable/disable speaker diarization.")
@click.option("--language-id/--no-language-id", default=None, help="Enable/disable language identification.")
@click.option("--language-hints", default=None, help="Comma-separated language hints.")
@click.option("--language-hints-strict/--no-language-hints-strict", default=None, help="Strict language hints.")
@click.option("--json-output", "--json", "json_output", is_flag=True, help="Output token JSON.")
@click.option("--no-wait", is_flag=True, help="Print transcription ID without waiting.")
def transcribe_cmd(
    path: Path | None,
    file_id: str | None,
    model: str | None,
    speaker_diarization: bool | None,
    language_id: bool | None,
    language_hints: str | None,
    language_hints_strict: bool | None,
    json_output: bool,
    no_wait: bool,
) -> None:
    """Upload and transcribe an audio file.

    Provide PATH to upload a local file, or --file-id to transcribe an
    already-uploaded file.
    """
    if path is None and file_id is None:
        raise click.UsageError("Provide PATH or --file-id.")
    if path is not None and file_id is not None:
        raise click.UsageError("PATH and --file-id are mutually exclusive.")

    client = get_client()
    settings = load_settings()

    # Apply inline overrides
    if model is not None:
        settings.model = model
    if speaker_diarization is not None:
        settings.enable_speaker_diarization = speaker_diarization
    if language_id is not None:
        settings.enable_language_identification = language_id
    if language_hints is not None:
        settings.language_hints = [h.strip() for h in language_hints.split(",") if h.strip()]
    if language_hints_strict is not None:
        settings.language_hints_strict = language_hints_strict

    config = settings_to_config(settings)

    # Upload if needed
    if path is not None:
        click.echo(f"Uploading {path.name}...", err=True)
        uploaded = client.files.upload(file=path)
        file_id = uploaded.id

    click.echo("Transcribing...", err=True)
    result = client.stt.transcribe(file_id=file_id, model=settings.model, config=config)

    if no_wait:
        click.echo(result.id)
        return

    tx = client.stt.wait(result.id)
    if tx.status != "completed":
        raise click.ClickException(f"Transcription failed: {tx.status}")

    transcript_result = client.stt.get_transcript(tx.id)
    tokens = [t.model_dump() for t in transcript_result.tokens]
    text = render_transcript(tokens)
    translation = render_translation(tokens)

    meta = _tx_to_meta(tx)
    save(tx.id, meta, text, tokens=tokens, translation=translation)

    if json_output:
        click.echo(json.dumps(tokens, indent=2, default=str))
    else:
        click.echo(text)
        if translation:
            click.echo(f"\n─── Translation ───\n{translation}")


# ── Settings ─────────────────────────────────────────────────────


@click.group("settings")
def settings_group() -> None:
    """Manage transcription settings."""


@settings_group.command("show")
@click.option("--json-output", "--json", "json_output", is_flag=True, help="Output JSON.")
def settings_show(json_output: bool) -> None:
    """Show current transcription settings."""
    settings = load_settings()
    if json_output:
        click.echo(json.dumps(settings.model_dump(exclude_none=True), indent=2))
    else:
        click.echo(f"Model:                    {settings.model}")
        click.echo(f"Speaker diarization:      {'ON' if settings.enable_speaker_diarization else 'OFF'}")
        click.echo(f"Language identification:   {'ON' if settings.enable_language_identification else 'OFF'}")
        click.echo(f"Language hints:            {', '.join(settings.language_hints) or 'None'}")
        click.echo(f"Language hints strict:     {'ON' if settings.language_hints_strict else 'OFF'}")


@settings_group.command("set")
@click.option("--model", default=None, help="Set model.")
@click.option("--speaker-diarization/--no-speaker-diarization", default=None, help="Enable/disable speaker diarization.")
@click.option("--language-id/--no-language-id", default=None, help="Enable/disable language identification.")
@click.option("--language-hints", default=None, help="Comma-separated language hints (empty string to clear).")
@click.option("--language-hints-strict/--no-language-hints-strict", default=None, help="Strict language hints.")
def settings_set(
    model: str | None,
    speaker_diarization: bool | None,
    language_id: bool | None,
    language_hints: str | None,
    language_hints_strict: bool | None,
) -> None:
    """Modify transcription settings."""
    settings = load_settings()
    changed = False

    if model is not None:
        settings.model = model
        changed = True
    if speaker_diarization is not None:
        settings.enable_speaker_diarization = speaker_diarization
        changed = True
    if language_id is not None:
        settings.enable_language_identification = language_id
        changed = True
    if language_hints is not None:
        settings.language_hints = [h.strip() for h in language_hints.split(",") if h.strip()]
        changed = True
    if language_hints_strict is not None:
        settings.language_hints_strict = language_hints_strict
        changed = True

    if not changed:
        raise click.UsageError("No settings specified. Use --help to see available options.")

    save_settings(settings)
    click.echo("Settings saved.")


@settings_group.command("reset")
def settings_reset() -> None:
    """Reset transcription settings to defaults."""
    save_settings(TranscriptionSettings())
    click.echo("Settings reset to defaults.")
