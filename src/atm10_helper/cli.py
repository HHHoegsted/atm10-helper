from __future__ import annotations

from pathlib import Path

import typer

from atm10_helper.db import check_database
from atm10_helper.importer import import_quest_chapters, import_quests

app = typer.Typer(
    help="ATM10 Helper command-line tools.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """ATM10 Helper command-line tools."""


@app.command("db-check")
def db_check() -> None:
    """Verify that ATM10 Helper can connect to the configured PostgreSQL database."""
    result = check_database()

    typer.echo("ATM10 Helper database check")
    typer.echo("---------------------------")
    typer.echo(f"Database: {result.database_name}")
    typer.echo(f"User:     {result.database_user}")
    typer.echo(f"Tables:   {result.table_count}")
    typer.echo(f"Views:    {result.view_count}")
    typer.echo(f"Version:  {result.postgres_version.splitlines()[0]}")


@app.command("import-chapters")
def import_chapters(
    atm10_path: Path = typer.Argument(
        ...,
        help="Path to an extracted ATM10 instance folder.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
) -> None:
    """Import FTB Quests chapter files into PostgreSQL."""
    result = import_quest_chapters(atm10_path)

    typer.echo("ATM10 Helper chapter import")
    typer.echo("---------------------------")
    typer.echo(f"Source:     {result.source_path}")
    typer.echo(f"Chapters:   {result.chapter_count}")
    typer.echo(f"Import run: {result.import_run_id}")


@app.command("import-quests")
def import_quests_command(
    atm10_path: Path = typer.Argument(
        ...,
        help="Path to an extracted ATM10 instance folder.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
) -> None:
    """Import FTB Quests quest blocks into PostgreSQL."""
    result = import_quests(atm10_path)

    typer.echo("ATM10 Helper quest import")
    typer.echo("-------------------------")
    typer.echo(f"Source:     {result.source_path}")
    typer.echo(f"Chapters:   {result.chapter_count}")
    typer.echo(f"Quests:     {result.quest_count}")
    typer.echo(f"Import run: {result.import_run_id}")