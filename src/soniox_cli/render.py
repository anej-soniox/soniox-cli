from enum import Enum


class ViewMode(Enum):
    TRANSCRIPT = "Transcript"
    TRANSLATION = "Translation"
    UNIFIED = "Unified"


def render_transcript(tokens: list[dict]) -> str:
    """Render transcript from tokens, with speaker labels and language tags."""
    parts: list[str] = []
    current_speaker: int | None = None
    current_language: str | None = None

    for token in tokens:
        if token.get("translation_status") == "translation":
            continue

        speaker = token.get("speaker")
        if speaker is not None and speaker != current_speaker:
            current_speaker = speaker
            parts.append(f"\n─ Speaker {speaker} ─\n")

        language = token.get("language")
        if language is not None and language != current_language:
            current_language = language
            parts.append(f"[{language}] ")

        parts.append(token.get("text", ""))

    return "".join(parts).strip()


def render_translation(tokens: list[dict]) -> str | None:
    """Render translation from tokens. Returns None if no translation tokens exist."""
    translated = [t for t in tokens if t.get("translation_status") == "translation"]
    if not translated:
        return None

    parts: list[str] = []
    current_speaker: int | None = None

    for token in translated:
        speaker = token.get("speaker")
        if speaker is not None and speaker != current_speaker:
            current_speaker = speaker
            parts.append(f"\n─ Speaker {speaker} ─\n")

        parts.append(token.get("text", ""))

    return "".join(parts).strip()


def render_unified(tokens: list[dict]) -> str | None:
    """Render interleaved original/translation chunks for comparison.

    The token stream alternates between original and translation chunks.
    Speaker and language state is tracked across the entire stream so labels
    only appear on change.
    """
    # Split into chunks by translation_status transitions
    chunks: list[tuple[str, list[dict]]] = []
    current_status: str | None = None
    current_chunk: list[dict] = []

    for token in tokens:
        status = token.get("translation_status", "none")
        if status != current_status:
            if current_chunk:
                chunks.append((current_status or "none", current_chunk))
            current_status = status
            current_chunk = [token]
        else:
            current_chunk.append(token)

    if current_chunk:
        chunks.append((current_status or "none", current_chunk))

    has_translation = any(s == "translation" for s, _ in chunks)
    if not has_translation:
        return None

    parts: list[str] = []
    current_speaker: int | None = None
    current_orig_lang: str | None = None
    current_trans_lang: str | None = None

    for status, chunk_tokens in chunks:
        is_translation = status == "translation"
        prefix = "◇" if is_translation else "◆"
        line_parts: list[str] = []

        for token in chunk_tokens:
            speaker = token.get("speaker")
            if speaker is not None and speaker != current_speaker:
                current_speaker = speaker
                # Flush text before speaker separator
                text = "".join(line_parts).strip()
                if text:
                    for line in text.splitlines():
                        parts.append(f"{prefix} {line}" if line.strip() else "")
                    if is_translation:
                        parts.append("")
                line_parts = []
                parts.append(f"─ Speaker {speaker} ─")

            if is_translation:
                lang = token.get("source_language")
                if lang is not None and lang != current_trans_lang:
                    current_trans_lang = lang
                    line_parts.append(f"[{lang}] ")
            else:
                lang = token.get("language")
                if lang is not None and lang != current_orig_lang:
                    current_orig_lang = lang
                    line_parts.append(f"[{lang}] ")

            line_parts.append(token.get("text", ""))

        text = "".join(line_parts).strip()
        if text:
            for line in text.splitlines():
                parts.append(f"{prefix} {line}" if line.strip() else "")
            if is_translation:
                parts.append("")

    return "\n".join(parts).strip()
