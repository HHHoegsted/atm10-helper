from __future__ import annotations

import typer

from atm10_helper.db import check_database

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