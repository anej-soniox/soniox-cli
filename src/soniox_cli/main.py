from pathlib import Path

import click
from simple_term_menu import TerminalMenu

from soniox_cli.commands import files_group, settings_group, transcribe_cmd, transcriptions_group
from soniox_cli.config import get_api_key, switch_api_key
from soniox_cli.files import list_files
from soniox_cli.transcribe import transcribe_file
from soniox_cli.transcriptions import list_transcriptions

MENU_ITEMS = [
    "List transcriptions",
    "List files",
    "Transcribe file",
    "Switch API key",
    "Exit",
]

MENU_ACTIONS = {
    0: list_transcriptions,
    1: list_files,
    2: transcribe_file,
    3: switch_api_key,
}

MAN_DIR = Path.home() / ".local" / "share" / "man" / "man1"
MAN_MARKER = Path.home() / ".soniox" / ".man_installed"


def install_man_pages() -> None:
    from click_man.core import write_man_pages

    MAN_DIR.mkdir(parents=True, exist_ok=True)
    write_man_pages("soniox", cli, target_dir=str(MAN_DIR))
    MAN_MARKER.parent.mkdir(parents=True, exist_ok=True)
    MAN_MARKER.write_text("1")


def _ensure_man_pages() -> None:
    if MAN_MARKER.exists():
        return
    try:
        install_man_pages()
    except Exception:
        pass  # non-critical, don't block CLI usage


def show_menu() -> None:
    menu = TerminalMenu(MENU_ITEMS, title="\nSoniox CLI\n")
    while True:
        choice = menu.show()
        if choice is None or choice == len(MENU_ITEMS) - 1:
            break
        action = MENU_ACTIONS.get(choice)
        if action:
            action()


@click.group(invoke_without_command=True)
@click.option("--install-man", is_flag=True, help="Install man pages to ~/.local/share/man/man1/.")
@click.pass_context
def cli(ctx: click.Context, install_man: bool) -> None:
    """Soniox speech-to-text CLI."""
    if install_man:
        install_man_pages()
        click.echo(f"Man pages installed to {MAN_DIR}")
        return
    _ensure_man_pages()
    if ctx.invoked_subcommand is not None:
        return
    get_api_key()
    show_menu()


cli.add_command(transcriptions_group)
cli.add_command(files_group)
cli.add_command(transcribe_cmd)
cli.add_command(settings_group)
