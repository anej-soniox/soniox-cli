import os
import unicodedata


def _display_width(text: str) -> int:
    width = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ("W", "F") else 1
    return width


def truncate(text: str, max_width: int | None = None) -> str:
    if max_width is None:
        max_width = os.get_terminal_size().columns - 4
    if _display_width(text) <= max_width:
        return text
    result = []
    width = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        cw = 2 if eaw in ("W", "F") else 1
        if width + cw > max_width - 1:
            break
        result.append(ch)
        width += cw
    result.append("…")
    return "".join(result)
