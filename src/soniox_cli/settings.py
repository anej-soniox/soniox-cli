import json
from pathlib import Path
from typing import Literal

import click
from pydantic import BaseModel
from simple_term_menu import TerminalMenu
from soniox.types import CreateTranscriptionConfig, StructuredContext, TranslationConfig

from soniox_cli.client import get_client
from soniox_cli.spinner import Spinner

# Patch simple-term-menu bugs when search_key=None:
# 1. wcswidth returns -1 for non-printable chars, making __len__ negative → crash
# 2. Arrow left/right fall through into search text and corrupt rendering
_OrigSearch = TerminalMenu.Search
_orig_len = _OrigSearch.__len__
_OrigSearch.__len__ = lambda self: max(0, _orig_len(self))

_orig_show = TerminalMenu.show

# Keys that simple-term-menu already handles in its action loop:
_KNOWN_KEYS = {
    "up", "down", "left", "right", "page_up", "page_down", "home", "end",
    "enter", "escape", "backspace", "tab", "insert", "delete",
    "ctrl-a", "ctrl-b", "ctrl-e", "ctrl-f", "ctrl-g",
    "ctrl-j", "ctrl-k", "ctrl-n", "ctrl-p",
}


def _patched_show(self: TerminalMenu) -> int | tuple[int, ...] | None:
    if self._search_key is None:
        orig_read = self._read_next_key

        def _filtered_read(ignore_case: bool = False) -> str:
            while True:
                key = orig_read(ignore_case=ignore_case)
                # Allow single printable characters (for search) and known
                # action keys. Drop everything else (e.g. arrow left/right
                # escape sequences that would corrupt search text).
                if len(key) == 1 or key in _KNOWN_KEYS:
                    return key

        self._read_next_key = _filtered_read  # type: ignore[assignment]
    return _orig_show(self)


TerminalMenu.show = _patched_show  # type: ignore[assignment]

SETTINGS_FILE = Path.home() / ".soniox" / "settings.json"


class TranslationSettings(BaseModel):
    type: Literal["one_way", "two_way"] | None = None
    target_language: str | None = None
    language_a: str | None = None
    language_b: str | None = None


class ContextPreset(BaseModel):
    name: str
    context: dict  # raw dict matching StructuredContext shape


class TranscriptionSettings(BaseModel):
    model: str = "stt-async-v4"
    language_hints: list[str] = []
    language_hints_strict: bool = False
    enable_speaker_diarization: bool = False
    enable_language_identification: bool = False
    translation: TranslationSettings | None = None
    active_context: str | None = None
    context_presets: list[ContextPreset] = []


def load_settings() -> TranscriptionSettings:
    if SETTINGS_FILE.exists():
        data = json.loads(SETTINGS_FILE.read_text())
        return TranscriptionSettings.model_validate(data)
    return TranscriptionSettings()


def save_settings(settings: TranscriptionSettings) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(settings.model_dump(exclude_none=True), indent=2) + "\n"
    )


def settings_to_config(settings: TranscriptionSettings) -> CreateTranscriptionConfig | None:
    data: dict = {}

    if settings.language_hints:
        data["language_hints"] = settings.language_hints
    if settings.language_hints_strict:
        data["language_hints_strict"] = True
    if settings.enable_speaker_diarization:
        data["enable_speaker_diarization"] = True
    if settings.enable_language_identification:
        data["enable_language_identification"] = True

    if settings.translation and settings.translation.type:
        t = settings.translation
        if t.type == "one_way" and t.target_language:
            data["translation"] = TranslationConfig(
                type="one_way", target_language=t.target_language
            )
        elif t.type == "two_way" and t.language_a and t.language_b:
            data["translation"] = TranslationConfig(
                type="two_way", language_a=t.language_a, language_b=t.language_b
            )

    if settings.active_context:
        preset = next(
            (p for p in settings.context_presets if p.name == settings.active_context),
            None,
        )
        if preset:
            data["context"] = StructuredContext.model_validate(preset.context)

    if not data:
        return None

    return CreateTranscriptionConfig(**data)


# --- Model cache ---

_models_cache: list | None = None


def get_available_models() -> list:
    global _models_cache
    if _models_cache is None:
        client = get_client()
        with Spinner("Fetching models..."):
            result = client.models.list()
        _models_cache = [m for m in result.models if m.transcription_mode == "async"]
    return _models_cache


def reset_models_cache() -> None:
    global _models_cache
    _models_cache = None


# --- Interactive form ---

def _format_translation(settings: TranscriptionSettings) -> str:
    t = settings.translation
    if not t or not t.type:
        return "Disabled"
    if t.type == "one_way":
        return f"One-way → {t.target_language or '?'}"
    return f"Two-way: {t.language_a or '?'} ↔ {t.language_b or '?'}"


def _format_hints(hints: list[str]) -> str:
    if not hints:
        return "None"
    return ", ".join(hints)


def _on_off(val: bool) -> str:
    return "ON" if val else "OFF"


def _edit_model(settings: TranscriptionSettings) -> None:
    models = get_available_models()
    if not models:
        click.echo("No async models available.")
        return

    entries = [f"{m.id}  ({m.name})" for m in models]
    entries.append("Back")

    current_idx = next((i for i, m in enumerate(models) if m.id == settings.model), None)
    menu = TerminalMenu(
        entries,
        title="\nSelect model\n",
        cursor_index=current_idx if current_idx is not None else 0,
    )
    choice = menu.show()
    if choice is not None and choice < len(models):
        settings.model = models[choice].id


def _get_languages_for_model(model_id: str) -> list[tuple[str, str]]:
    """Return [(code, name), ...] for the currently selected model."""
    models = get_available_models()
    for m in models:
        if m.id == model_id:
            return [(lang.code, lang.name) for lang in m.languages]
    return []


def _edit_language_hints(settings: TranscriptionSettings) -> None:
    languages = _get_languages_for_model(settings.model)
    if not languages:
        click.echo("No languages available for the selected model.")
        return

    selected = set(settings.language_hints)
    entries = [f"{code:>4s}  {name}" for code, name in languages]
    preselected = [i for i, (code, _) in enumerate(languages) if code in selected]

    menu = TerminalMenu(
        entries,
        title="\nLanguage hints (type to filter, tab to toggle, enter to confirm)\n",
        multi_select=True,
        show_multi_select_hint=True,
        multi_select_select_on_accept=False,
        multi_select_empty_ok=True,
        preselected_entries=preselected if preselected else None,
        search_key=None,
        multi_select_keys=("tab",),
    )
    menu.show()

    # chosen_accept_key is None when user pressed escape (cancel)
    if menu.chosen_accept_key is None:
        return

    chosen = menu.chosen_menu_indices
    settings.language_hints = [languages[i][0] for i in chosen] if chosen else []


def _pick_language(settings: TranscriptionSettings, title: str, current: str | None = None) -> str | None:
    """Show a searchable language picker. Returns selected code or None on cancel."""
    languages = _get_languages_for_model(settings.model)
    if not languages:
        click.echo("No languages available for the selected model.")
        return None

    entries = [f"{code:>4s}  {name}" for code, name in languages]
    entries.append("Back")

    cursor_idx = 0
    if current:
        cursor_idx = next((i for i, (c, _) in enumerate(languages) if c == current), 0)

    menu = TerminalMenu(
        entries,
        title=f"\n{title}\n",
        cursor_index=cursor_idx,
        search_key=None,
    )
    choice = menu.show()

    if choice is None or choice == len(entries) - 1:
        return None
    return languages[choice][0]


def _edit_translation(settings: TranscriptionSettings) -> None:
    entries = ["Disabled", "One-way translation", "Two-way translation", "Back"]
    menu = TerminalMenu(entries, title="\nTranslation type\n")
    choice = menu.show()

    if choice is None or choice == 3:
        return

    if choice == 0:
        settings.translation = None
        return

    if choice == 1:
        target = _pick_language(settings, "Target language")
        if target:
            settings.translation = TranslationSettings(
                type="one_way", target_language=target
            )

    if choice == 2:
        lang_a = _pick_language(settings, "Language A")
        if not lang_a:
            return
        lang_b = _pick_language(settings, "Language B")
        if lang_b:
            settings.translation = TranslationSettings(
                type="two_way", language_a=lang_a, language_b=lang_b
            )


_CONTEXT_TEMPLATE = json.dumps(
    {"text": "", "terms": [], "general": [], "translation_terms": []},
    indent=2,
)


def _validate_context(raw: dict) -> StructuredContext:
    """Validate a raw dict against StructuredContext. Raises on invalid data."""
    return StructuredContext.model_validate(raw)


def _edit_context_json(prefill: str | None = None) -> dict | None:
    """Open click.edit() with context JSON. Returns parsed dict or None on cancel."""
    result = click.edit(text=prefill or _CONTEXT_TEMPLATE, extension=".json")
    if result is None:
        return None
    result = result.strip()
    if not result:
        return None
    try:
        data = json.loads(result)
    except json.JSONDecodeError as e:
        click.echo(f"Invalid JSON: {e}")
        click.pause()
        return None
    try:
        _validate_context(data)
    except Exception as e:
        click.echo(f"Invalid context: {e}")
        click.pause()
        return None
    return data


def _edit_preset_actions(settings: TranscriptionSettings, idx: int) -> None:
    """Sub-menu for editing/renaming/deleting an existing preset."""
    preset = settings.context_presets[idx]
    entries = ["Edit", "Rename", "Delete", "Back"]
    menu = TerminalMenu(entries, title=f"\n{preset.name}\n")
    choice = menu.show()

    if choice is None or choice == 3:
        return

    if choice == 0:  # Edit
        data = _edit_context_json(json.dumps(preset.context, indent=2))
        if data is not None:
            preset.context = data

    elif choice == 1:  # Rename
        new_name = click.prompt("New name", default=preset.name).strip()
        if new_name and new_name != preset.name:
            if settings.active_context == preset.name:
                settings.active_context = new_name
            preset.name = new_name

    elif choice == 2:  # Delete
        if click.confirm(f"Delete preset '{preset.name}'?", default=False):
            if settings.active_context == preset.name:
                settings.active_context = None
            settings.context_presets.pop(idx)


def _edit_context(settings: TranscriptionSettings) -> None:
    cursor = 0
    while True:
        entries: list[str] = ["None (disable)", "New context..."]
        preset_offset = 0
        if settings.context_presets:
            entries.append("──────────────")
            preset_offset = len(entries)
            for p in settings.context_presets:
                marker = "  ✓" if p.name == settings.active_context else ""
                entries.append(f"{p.name}{marker}")
        entries.append("──────────────")
        entries.append("Back")

        menu = TerminalMenu(entries, title="\nContext\n", cursor_index=cursor)
        choice = menu.show()

        if choice is None or entries[choice] == "Back":
            return

        cursor = choice

        if choice == 0:  # None (disable)
            settings.active_context = None
            return

        if choice == 1:  # New context...
            data = _edit_context_json()
            if data is not None:
                name = click.prompt("Preset name").strip()
                if name:
                    settings.context_presets.append(ContextPreset(name=name, context=data))
                    settings.active_context = name
            continue

        if entries[choice] == "──────────────":
            continue

        # Clicked a preset
        preset_idx = choice - preset_offset
        if 0 <= preset_idx < len(settings.context_presets):
            preset = settings.context_presets[preset_idx]
            if settings.active_context == preset.name:
                # Already active — open actions sub-menu
                _edit_preset_actions(settings, preset_idx)
            else:
                # Set as active
                settings.active_context = preset.name


def show_settings_form() -> None:
    settings = load_settings()
    cursor = 0

    while True:
        W = 26  # label column width
        context_label = settings.active_context or "OFF"
        items = [
            f"{'Model:':{W}}{settings.model}",
            f"{'Speaker diarization:':{W}}{_on_off(settings.enable_speaker_diarization)}",
            f"{'Language identification:':{W}}{_on_off(settings.enable_language_identification)}",
            f"{'Language hints:':{W}}{_format_hints(settings.language_hints)}",
            f"{'Language hints strict:':{W}}{_on_off(settings.language_hints_strict)}",
            f"{'Translation:':{W}}{_format_translation(settings)}",
            f"{'Context:':{W}}{context_label}",
            "──────────────",
            "Save and back",
            "Reset to defaults",
        ]

        menu = TerminalMenu(items, title="\nTranscription settings\n", cursor_index=cursor)
        choice = menu.show()

        if choice is None:
            return

        cursor = choice

        match choice:
            case 0:
                _edit_model(settings)
            case 1:
                settings.enable_speaker_diarization = not settings.enable_speaker_diarization
            case 2:
                settings.enable_language_identification = not settings.enable_language_identification
            case 3:
                _edit_language_hints(settings)
            case 4:
                settings.language_hints_strict = not settings.language_hints_strict
            case 5:
                _edit_translation(settings)
            case 6:
                _edit_context(settings)
            case 7:
                pass  # separator
            case 8:
                save_settings(settings)
                click.echo("Settings saved.")
                return
            case 9:
                settings = TranscriptionSettings()
