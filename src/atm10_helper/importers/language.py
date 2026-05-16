from __future__ import annotations

import re
from pathlib import Path

import psycopg

from atm10_helper.config import DatabaseSettings, get_database_settings
from atm10_helper.importers.models import LanguageImportResult
from atm10_helper.importers.snbt import (
    clean_minecraft_text,
    parse_snbt_string,
    parse_snbt_string_list,
    updated_depth,
    value_depth,
)


LANGUAGE_RELATIVE_PATH = Path("config/ftbquests/quests/lang")


def import_language(
    atm10_path: Path,
    locale: str = "en_us",
    settings: DatabaseSettings | None = None,
) -> LanguageImportResult:
    resolved_atm10_path = atm10_path.expanduser().resolve()
    language_path = resolved_atm10_path / LANGUAGE_RELATIVE_PATH / f"{locale}.snbt"
    chapter_language_path = resolved_atm10_path / LANGUAGE_RELATIVE_PATH / locale / "chapters"

    if not resolved_atm10_path.exists():
        raise FileNotFoundError(f"ATM10 path does not exist: {resolved_atm10_path}")

    if not language_path.exists():
        raise FileNotFoundError(f"Could not find language file: {language_path}")

    language_files = [language_path]

    if chapter_language_path.exists():
        language_files.extend(sorted(chapter_language_path.glob("*.snbt")))

    language_entries: dict[str, str | list[str]] = {}

    for language_file in language_files:
        language_entries.update(parse_language_entries(language_file))

    chapter_updates = build_chapter_language_updates(language_entries)
    quest_updates = build_quest_language_updates(language_entries)

    resolved_settings = settings or get_database_settings()

    with psycopg.connect(resolved_settings.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO import_runs (source_label, source_path, modpack_slug, notes)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    "ftbquests_language",
                    str(resolved_atm10_path),
                    "atm10",
                    f"Imported FTB Quests language strings for locale {locale}.",
                ),
            )
            import_run_id = cursor.fetchone()[0]

            chapter_update_count = 0

            for chapter_id, update in chapter_updates.items():
                cursor.execute(
                    """
                    UPDATE quest_chapters
                    SET
                        title = COALESCE(%s, title),
                        subtitle = COALESCE(%s, subtitle),
                        imported_at = now(),
                        import_run_id = %s
                    WHERE id = %s;
                    """,
                    (
                        update.get("title"),
                        update.get("subtitle"),
                        import_run_id,
                        chapter_id,
                    ),
                )

                chapter_update_count += cursor.rowcount

            quest_update_count = 0

            for quest_id, update in quest_updates.items():
                cursor.execute(
                    """
                    UPDATE quests
                    SET
                        title = COALESCE(%s, title),
                        subtitle = COALESCE(%s, subtitle),
                        description = COALESCE(%s, description),
                        imported_at = now(),
                        import_run_id = %s
                    WHERE id = %s;
                    """,
                    (
                        update.get("title"),
                        update.get("subtitle"),
                        update.get("description"),
                        import_run_id,
                        quest_id,
                    ),
                )

                quest_update_count += cursor.rowcount

            cursor.execute(
                """
                UPDATE import_runs
                SET finished_at = now()
                WHERE id = %s;
                """,
                (import_run_id,),
            )

        connection.commit()

    return LanguageImportResult(
        source_path=resolved_atm10_path,
        locale=locale,
        language_file_count=len(language_files),
        chapter_update_count=chapter_update_count,
        quest_update_count=quest_update_count,
        import_run_id=str(import_run_id),
    )


def parse_language_entries(language_file: Path) -> dict[str, str | list[str]]:
    raw_snbt = language_file.read_text(encoding="utf-8")
    entries: dict[str, str | list[str]] = {}
    lines = raw_snbt.splitlines()
    depth = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped_line = line.strip()

        if depth == 1:
            match = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", stripped_line)

            if match is not None:
                key = match.group(1)
                raw_value = match.group(2)

                if raw_value.startswith('"'):
                    entries[key] = clean_minecraft_text(parse_snbt_string(raw_value))
                    depth = updated_depth(depth, line)
                    index += 1
                    continue

                if raw_value.startswith("["):
                    collected_lines = [raw_value]
                    collected_value_depth = value_depth(raw_value)

                    while collected_value_depth > 0:
                        index += 1

                        if index >= len(lines):
                            raise ValueError(
                                f"Unterminated language list for key {key} in {language_file}"
                            )

                        collected_lines.append(lines[index])
                        collected_value_depth += value_depth(lines[index])

                    entries[key] = [
                        clean_minecraft_text(value)
                        for value in parse_snbt_string_list("\n".join(collected_lines))
                    ]
                    depth = updated_depth(depth, line)
                    index += 1
                    continue

        depth = updated_depth(depth, line)
        index += 1

    return entries


def build_chapter_language_updates(
    language_entries: dict[str, str | list[str]],
) -> dict[str, dict[str, str | None]]:
    updates: dict[str, dict[str, str | None]] = {}

    for key, value in language_entries.items():
        match = re.fullmatch(r"chapter\.([A-Fa-f0-9]+)\.(title|chapter_subtitle)", key)

        if match is None:
            continue

        chapter_id = match.group(1)
        field = match.group(2)
        update = updates.setdefault(chapter_id, {})

        if field == "title":
            update["title"] = language_value_to_text(value)

        if field == "chapter_subtitle":
            update["subtitle"] = language_value_to_text(value)

    return updates


def build_quest_language_updates(
    language_entries: dict[str, str | list[str]],
) -> dict[str, dict[str, str | None]]:
    updates: dict[str, dict[str, str | None]] = {}

    for key, value in language_entries.items():
        match = re.fullmatch(r"quest\.([A-Fa-f0-9]+)\.(title|subtitle|quest_desc)", key)

        if match is None:
            continue

        quest_id = match.group(1)
        field = match.group(2)
        update = updates.setdefault(quest_id, {})

        if field == "title":
            update["title"] = language_value_to_text(value)

        if field == "subtitle":
            update["subtitle"] = language_value_to_text(value)

        if field == "quest_desc":
            update["description"] = language_value_to_text(value)

    return updates


def language_value_to_text(value: str | list[str]) -> str | None:
    if isinstance(value, str):
        return value or None

    text = "\n\n".join(part for part in value if part)

    return text or None