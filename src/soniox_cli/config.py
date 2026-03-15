import os
import re
import sys
from pathlib import Path

ENV_VAR = "SONIOX_API_KEY"


def get_rc_file() -> Path:
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return Path.home() / ".zshrc"
    return Path.home() / ".bashrc"


def _read_key_from_rc() -> str | None:
    rc = get_rc_file()
    if not rc.exists():
        return None
    text = rc.read_text()
    match = re.search(rf'export\s+{ENV_VAR}=["\']?([^"\'\s]+)["\']?', text)
    if match:
        return match.group(1)
    return None


def get_api_key(prompt_if_missing: bool = True) -> str | None:
    key = os.environ.get(ENV_VAR)
    if key:
        return key

    key = _read_key_from_rc()
    if key:
        os.environ[ENV_VAR] = key
        return key

    if not prompt_if_missing or not sys.stdin.isatty():
        return None

    import click

    key = click.prompt("Enter your Soniox API key", hide_input=True)
    if not key:
        return None

    os.environ[ENV_VAR] = key

    if click.confirm("Save API key to shell rc file?", default=True):
        _save_key_to_rc(key)
        rc = get_rc_file()
        click.echo(f"Saved to {rc}.")

    return key


def _save_key_to_rc(key: str) -> None:
    rc = get_rc_file()
    if rc.exists():
        text = rc.read_text()
        # Replace existing export line if present
        new_text, count = re.subn(
            rf'export\s+{ENV_VAR}=["\']?[^"\'\s]*["\']?',
            f'export {ENV_VAR}="{key}"',
            text,
        )
        if count > 0:
            rc.write_text(new_text)
            return
    with open(rc, "a") as f:
        f.write(f'\nexport {ENV_VAR}="{key}"\n')


def require_api_key() -> str:
    key = get_api_key()
    if not key:
        import click

        raise click.ClickException(
            f"API key required. Set {ENV_VAR} or run `soniox` interactively."
        )
    return key
