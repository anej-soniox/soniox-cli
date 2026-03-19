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
        ["Back", "Retranscribe (coming soon)", "Delete"],
        title=f"\nSoniox CLI › {filename}\n",
    )
    choice = menu.show()

    if choice is None or choice == 0:
        return False

    if choice == 1:
        click.echo("  Retranscribe is not yet implemented.")
        return False

    if choice == 2:
        confirm = TerminalMenu(["Yes", "No"], title=f"\nSoniox CLI › Delete {filename}?\n")
        if confirm.show() == 0:
            client = get_client()
            with Spinner(f"Deleting {filename}..."):
                client.files.delete(file_id)
            click.echo(f"  Deleted {filename}")
            return True

    return False


def list_files() -> None:
    client = get_client()

    with Spinner("Loading files...", title="Soniox CLI › Files"):
        result = client.files.list(limit=PAGE_SIZE)

    if not result.files:
        click.echo("No files found.")
        return

    file_list = list(result.files)
    next_cursor = result.next_page_cursor

    cursor = 0
    while True:
        entries = ["Back"]
        entries.extend(truncate(_build_entry(f)) for f in file_list)
        if next_cursor:
            entries.append("Load more...")

        menu = TerminalMenu(entries, title="\nSoniox CLI › Files\n", cursor_index=cursor)
        choice = menu.show()

        if choice is None or choice == 0:
            break

        cursor = choice

        if next_cursor and choice == len(entries) - 1:
            with Spinner("Loading more..."):
                result = client.files.list(limit=PAGE_SIZE, cursor=next_cursor)
            file_list.extend(result.files)
            next_cursor = result.next_page_cursor
            continue

        f = file_list[choice - 1]
        deleted = _file_actions(f.id, f.filename)
        if deleted:
            file_list.pop(choice - 1)
            if not file_list:
                click.echo("No files remaining.")
                break
