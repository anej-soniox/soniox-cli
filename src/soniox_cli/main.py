import click
from simple_term_menu import TerminalMenu

from soniox_cli.config import get_api_key

MENU_ITEMS = [
    "Transcribe a file",
    "List transcriptions",
    "List files",
    "Exit",
]


def show_menu() -> None:
    menu = TerminalMenu(MENU_ITEMS, title="\nSoniox CLI\n")
    while True:
        choice = menu.show()
        if choice is None or choice == len(MENU_ITEMS) - 1:
            break
        click.echo(f"\n[TODO] {MENU_ITEMS[choice]}\n")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Soniox speech-to-text CLI."""
    if ctx.invoked_subcommand is not None:
        return
    get_api_key()
    show_menu()
