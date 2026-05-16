from __future__ import annotations

import re
from pathlib import Path

import typer

from atm10_helper.db import check_database, get_progress_summary
from atm10_helper.importer import (
    import_language,
    import_progress,
    import_quest_chapters,
    import_quests,
    import_rewards,
    import_tasks,
)

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


@app.command("progress-summary")
def progress_summary(
    player_filter: str | None = typer.Option(
        None,
        "--player",
        "-p",
        help="Only show players whose display name contains this text, case-insensitive.",
    ),
    top_chapters: int = typer.Option(
        10,
        "--top-chapters",
        "-n",
        min=1,
        help="Number of chapter rows to show per player unless --all-chapters is used.",
    ),
    all_chapters: bool = typer.Option(
        False,
        "--all-chapters",
        help="Show every chapter with progress instead of only the top chapter rows.",
    ),
) -> None:
    """Show imported FTB Quests progress summaries."""
    result = get_progress_summary()

    selected_players = [
        player
        for player in result.players
        if player_filter is None
        or player_filter.casefold() in player.display_name.casefold()
    ]

    typer.echo("ATM10 Helper progress summary")
    typer.echo("-----------------------------")

    if not result.players:
        typer.echo("No players found.")
        return

    if not selected_players:
        typer.echo(f"No players matched filter: {player_filter}")
        return

    typer.echo("Players")
    typer.echo("-------")

    for player in selected_players:
        typer.echo(
            f"{clean_cli_text(player.display_name)}: "
            f"{player.completed_task_count} completed tasks, "
            f"{player.complete_quest_count} complete quests, "
            f"{player.partial_quest_count} partial quests, "
            f"{player.known_quest_count} quests with progress"
        )

    selected_player_uuids = {
        player.player_uuid
        for player in selected_players
    }

    selected_chapters = [
        chapter
        for chapter in result.chapters
        if chapter.player_uuid in selected_player_uuids
    ]

    if not selected_chapters:
        return

    typer.echo("")
    typer.echo("Top chapters with progress")
    typer.echo("--------------------------")

    for player in selected_players:
        player_chapters = [
            chapter
            for chapter in selected_chapters
            if chapter.player_uuid == player.player_uuid
        ]

        if not player_chapters:
            continue

        displayed_chapters = player_chapters if all_chapters else player_chapters[:top_chapters]
        hidden_chapter_count = len(player_chapters) - len(displayed_chapters)

        typer.echo("")
        typer.echo(clean_cli_text(player.display_name))

        chapter_lines = [
            (
                f"  {clean_cli_text(chapter.chapter_title)}: "
                f"{chapter.complete_quest_count} complete, "
                f"{chapter.partial_quest_count} partial, "
                f"{chapter.total_quest_count} total with progress"
            )
            for chapter in displayed_chapters
        ]

        if hidden_chapter_count > 0:
            chapter_lines.append(
                f"  ... {hidden_chapter_count} more chapters hidden "
                f"(use --all-chapters to show all)"
            )

        typer.echo("\n".join(chapter_lines))


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


@app.command("import-tasks")
def import_tasks_command(
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
    """Import FTB Quests task blocks into PostgreSQL."""
    result = import_tasks(atm10_path)

    typer.echo("ATM10 Helper task import")
    typer.echo("------------------------")
    typer.echo(f"Source:     {result.source_path}")
    typer.echo(f"Chapters:   {result.chapter_count}")
    typer.echo(f"Quests:     {result.quest_count}")
    typer.echo(f"Tasks:      {result.task_count}")
    typer.echo(f"Import run: {result.import_run_id}")


@app.command("import-rewards")
def import_rewards_command(
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
    """Import FTB Quests reward blocks into PostgreSQL."""
    result = import_rewards(atm10_path)

    typer.echo("ATM10 Helper reward import")
    typer.echo("--------------------------")
    typer.echo(f"Source:     {result.source_path}")
    typer.echo(f"Chapters:   {result.chapter_count}")
    typer.echo(f"Quests:     {result.quest_count}")
    typer.echo(f"Rewards:    {result.reward_count}")
    typer.echo(f"Import run: {result.import_run_id}")


@app.command("import-progress")
def import_progress_command(
    atm10_path: Path = typer.Argument(
        ...,
        help="Path to an ATM10 instance folder with FTB Quests player progress.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
) -> None:
    """Import FTB Quests player task progress into PostgreSQL."""
    result = import_progress(atm10_path)

    typer.echo("ATM10 Helper progress import")
    typer.echo("----------------------------")
    typer.echo(f"Source:        {result.source_path}")
    typer.echo(f"Players:       {result.player_count}")
    typer.echo(f"Task progress: {result.task_progress_count}")
    typer.echo(f"Import run:    {result.import_run_id}")


@app.command("import-language")
def import_language_command(
    atm10_path: Path = typer.Argument(
        ...,
        help="Path to an extracted ATM10 instance folder.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
    locale: str = typer.Option(
        "en_us",
        "--locale",
        "-l",
        help="FTB Quests language locale to import.",
    ),
) -> None:
    """Import FTB Quests language strings into PostgreSQL."""
    result = import_language(atm10_path, locale=locale)

    typer.echo("ATM10 Helper language import")
    typer.echo("----------------------------")
    typer.echo(f"Source:          {result.source_path}")
    typer.echo(f"Locale:          {result.locale}")
    typer.echo(f"Language files:  {result.language_file_count}")
    typer.echo(f"Chapter updates: {result.chapter_update_count}")
    typer.echo(f"Quest updates:   {result.quest_update_count}")
    typer.echo(f"Import run:      {result.import_run_id}")


def clean_cli_text(value: str | None) -> str:
    if value is None:
        return ""

    without_control_characters = "".join(
        character
        for character in value
        if character.isprintable() or character.isspace()
    )

    return re.sub(r"\s+", " ", without_control_characters).strip()