import click
from simple_term_menu import TerminalMenu

from soniox_cli.config import get_api_key, switch_api_key
from soniox_cli.files import list_files
from soniox_cli.settings import show_settings_form
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
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Soniox speech-to-text CLI."""
    if ctx.invoked_subcommand is not None:
        return
    get_api_key()
    show_menu()
