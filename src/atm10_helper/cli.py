from __future__ import annotations

import re
from pathlib import Path

import typer

from atm10_helper.db import check_database, get_partial_quests, get_progress_summary
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


@app.command("next-steps")
def next_steps(
    player_filter: str | None = typer.Option(
        None,
        "--player",
        "-p",
        help="Only show players whose display name contains this text, case-insensitive.",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        min=1,
        help="Maximum number of partial quests to show.",
    ),
    missing_limit: int = typer.Option(
        10,
        "--missing-limit",
        min=1,
        help="Maximum number of missing task details to show per quest.",
    ),
) -> None:
    """Show incomplete quests that already have progress."""
    partial_quests = get_partial_quests(player_filter=player_filter)

    typer.echo("ATM10 Helper next steps")
    typer.echo("-----------------------")

    if player_filter is not None:
        typer.echo(f"Player filter: {clean_cli_text(player_filter)}")

    if not partial_quests:
        if player_filter is None:
            typer.echo("No partial quests found.")
        else:
            typer.echo(f"No partial quests found for player filter: {player_filter}")
        return

    displayed_quests = partial_quests[:limit]
    hidden_quest_count = len(partial_quests) - len(displayed_quests)

    current_player_uuid: str | None = None

    for quest in displayed_quests:
        if quest.player_uuid != current_player_uuid:
            current_player_uuid = quest.player_uuid
            typer.echo("")
            typer.echo(clean_cli_text(quest.display_name))

        quest_lines = [
            f"  {format_quest_heading(quest.chapter_title, quest.quest_title, quest.quest_id)}",
            (
                f"    Progress: {quest.completed_tasks}/{quest.total_tasks} tasks "
                f"({quest.missing_tasks} missing)"
            ),
        ]

        if quest.missing_task_details:
            displayed_missing_tasks = quest.missing_task_details[:missing_limit]
            hidden_missing_task_count = (
                len(quest.missing_task_details) - len(displayed_missing_tasks)
            )

            item_tasks = [
                task
                for task in displayed_missing_tasks
                if task.task_type == "item" and task.item_id
            ]
            other_tasks = [
                task
                for task in displayed_missing_tasks
                if task.task_type != "item" or not task.item_id
            ]

            if item_tasks:
                quest_lines.append("    Missing item tasks:")
                for task in item_tasks:
                    quest_lines.extend(
                        format_item_task_lines(task.item_id, task.item_count)
                    )

            if other_tasks:
                quest_lines.append("    Missing other tasks:")
                quest_lines.extend(
                    f"      - {format_other_task(task.task_type, task.title, task.task_id)}"
                    for task in other_tasks
                )

            if hidden_missing_task_count > 0:
                quest_lines.append(
                    f"    ... {hidden_missing_task_count} more missing tasks hidden "
                    f"(use --missing-limit {len(quest.missing_task_details)} to show all)"
                )

        typer.echo("\n".join(quest_lines))

    if hidden_quest_count > 0:
        typer.echo("")
        typer.echo(
            f"... {hidden_quest_count} more partial quests hidden "
            f"(use --limit {len(partial_quests)} to show all)"
        )


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


def format_quest_heading(chapter_title: str, quest_title: str, quest_id: str) -> str:
    clean_chapter_title = clean_cli_text(chapter_title)
    clean_quest_title = clean_cli_text(quest_title)

    if clean_quest_title:
        return f"{clean_chapter_title} — {clean_quest_title}"

    return f"{clean_chapter_title} — quest {quest_id}"


def format_item_task_lines(item_id: str, item_count: int | None) -> list[str]:
    clean_item_id = clean_identifier(item_id)

    if item_count is None or item_count <= 1:
        return [
            "      - item",
            f"        {clean_item_id}",
        ]

    return [
        f"      - x{item_count}",
        f"        {clean_item_id}",
    ]


def format_other_task(task_type: str, title: str, task_id: str) -> str:
    clean_title = clean_cli_text(title)

    if clean_title:
        return f"{clean_identifier(task_type)}: {clean_title}"

    return f"{clean_identifier(task_type)} task {clean_identifier(task_id)}"


def clean_identifier(value: str | None) -> str:
    if value is None:
        return ""

    return "".join(
        character
        for character in value
        if character.isprintable() and not character.isspace()
    ).strip()


def clean_cli_text(value: str | None) -> str:
    if value is None:
        return ""

    without_control_characters = "".join(
        character
        for character in value
        if character.isprintable() or character.isspace()
    )

    return re.sub(r"\s+", " ", without_control_characters).strip()