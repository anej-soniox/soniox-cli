import click
from simple_term_menu import TerminalMenu

from soniox_cli.client import get_client
from soniox_cli.spinner import Spinner
from soniox_cli.util import truncate

PAGE_SIZE = 50


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _build_entry(f: object) -> str:
    return f"{f.created_at:%Y-%m-%d %H:%M}  {f.id}  {f.filename:30s}  {_format_size(f.size):>10s}"


def _file_actions(file_id: str, filename: str) -> bool:
    """Show actions for a selected file. Returns True if file was deleted."""
    menu = TerminalMenu(
        ["Retranscribe (coming soon)", "Delete", "Back"],
        title=f"\n{filename}\n",
    )
    choice = menu.show()

    if choice == 0:
        click.echo("  Retranscribe is not yet implemented.")
        return False

    if choice == 1:
        confirm = TerminalMenu(["Yes", "No"], title=f"\nDelete {filename}?\n")
        if confirm.show() == 0:
            client = get_client()
            with Spinner(f"Deleting {filename}..."):
                client.files.delete(file_id)
            click.echo(f"  Deleted {filename}")
            return True

    return False


def list_files() -> None:
    client = get_client()

    with Spinner("Loading files..."):
        result = client.files.list(limit=PAGE_SIZE)

    if not result.files:
        click.echo("No files found.")
        return

    file_list = list(result.files)
    next_cursor = result.next_page_cursor

    cursor = 0
    while True:
        entries = [truncate(_build_entry(f)) for f in file_list]
        if next_cursor:
            entries.append("Load more...")
        entries.append("Back")

        menu = TerminalMenu(entries, title="\nFiles\n", cursor_index=cursor)
        choice = menu.show()

        if choice is None or choice == len(entries) - 1:
            break

        cursor = choice

        if next_cursor and choice == len(entries) - 2:
            with Spinner("Loading more..."):
                result = client.files.list(limit=PAGE_SIZE, cursor=next_cursor)
            file_list.extend(result.files)
            next_cursor = result.next_page_cursor
            continue

        f = file_list[choice]
        deleted = _file_actions(f.id, f.filename)
        if deleted:
            file_list.pop(choice)
            if not file_list:
                click.echo("No files remaining.")
                break
