from __future__ import annotations

from pathlib import Path

import psycopg

from atm10_helper.config import DatabaseSettings, get_database_settings
from atm10_helper.importers.chapters import (
    CHAPTERS_RELATIVE_PATH,
    parse_chapter_file,
    raise_for_duplicate_chapter_ids,
)
from atm10_helper.importers.models import (
    ParsedQuest,
    ParsedQuestReward,
    RewardImportResult,
)
from atm10_helper.importers.quests import (
    parse_quests_for_chapter,
    raise_for_duplicate_quest_ids,
)
from atm10_helper.importers.snbt import (
    extract_item_count_from_item_block,
    extract_item_id_from_item_block,
    extract_top_level_list,
    extract_top_level_object,
    optional_top_level_integer_value,
    required_top_level_string_value,
    split_top_level_objects,
)


def import_rewards(
    atm10_path: Path,
    settings: DatabaseSettings | None = None,
) -> RewardImportResult:
    resolved_atm10_path = atm10_path.expanduser().resolve()
    chapters_path = resolved_atm10_path / CHAPTERS_RELATIVE_PATH

    if not resolved_atm10_path.exists():
        raise FileNotFoundError(f"ATM10 path does not exist: {resolved_atm10_path}")

    if not chapters_path.exists():
        raise FileNotFoundError(
            "Could not find FTB Quests chapter directory at "
            f"{chapters_path}. Expected an extracted ATM10 instance folder."
        )

    chapter_files = sorted(chapters_path.glob("*.snbt"))

    if not chapter_files:
        raise FileNotFoundError(f"No .snbt chapter files found in {chapters_path}")

    parsed_chapters = [parse_chapter_file(chapter_file) for chapter_file in chapter_files]
    raise_for_duplicate_chapter_ids(parsed_chapters)

    parsed_quests: list[ParsedQuest] = []

    for chapter_file, chapter in zip(chapter_files, parsed_chapters, strict=True):
        parsed_quests.extend(parse_quests_for_chapter(chapter_file, chapter.id))

    raise_for_duplicate_quest_ids(parsed_quests)

    parsed_rewards: list[ParsedQuestReward] = []

    for quest in parsed_quests:
        parsed_rewards.extend(parse_rewards_for_quest(quest))

    raise_for_duplicate_reward_ids(parsed_rewards)

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
                    "ftbquests_rewards",
                    str(resolved_atm10_path),
                    "atm10",
                    "Imported FTB Quests reward SNBT blocks.",
                ),
            )
            import_run_id = cursor.fetchone()[0]

            for reward in parsed_rewards:
                cursor.execute(
                    """
                    INSERT INTO quest_rewards (
                        id,
                        quest_id,
                        reward_type,
                        item_id,
                        item_count,
                        xp_levels,
                        raw_snbt,
                        import_run_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        quest_id = EXCLUDED.quest_id,
                        reward_type = EXCLUDED.reward_type,
                        item_id = EXCLUDED.item_id,
                        item_count = EXCLUDED.item_count,
                        xp_levels = EXCLUDED.xp_levels,
                        raw_snbt = EXCLUDED.raw_snbt,
                        imported_at = now(),
                        import_run_id = EXCLUDED.import_run_id;
                    """,
                    (
                        reward.id,
                        reward.quest_id,
                        reward.reward_type,
                        reward.item_id,
                        reward.item_count,
                        reward.xp_levels,
                        reward.raw_snbt,
                        import_run_id,
                    ),
                )

            cursor.execute(
                """
                UPDATE import_runs
                SET finished_at = now()
                WHERE id = %s;
                """,
                (import_run_id,),
            )

        connection.commit()

    return RewardImportResult(
        source_path=resolved_atm10_path,
        chapter_count=len(parsed_chapters),
        quest_count=len(parsed_quests),
        reward_count=len(parsed_rewards),
        import_run_id=str(import_run_id),
    )


def parse_rewards_for_quest(quest: ParsedQuest) -> list[ParsedQuestReward]:
    rewards_list = extract_top_level_list(quest.raw_snbt, "rewards")

    if rewards_list is None:
        return []

    reward_blocks = split_top_level_objects(rewards_list)

    return [
        parse_reward_block(
            reward_block=reward_block,
            quest_id=quest.id,
        )
        for reward_block in reward_blocks
    ]


def parse_reward_block(reward_block: str, quest_id: str) -> ParsedQuestReward:
    reward_id = required_top_level_string_value(
        reward_block,
        "id",
        Path(f"quest {quest_id}"),
    )
    reward_type = required_top_level_string_value(
        reward_block,
        "type",
        Path(f"quest {quest_id}"),
    )
    item_block = extract_top_level_object(reward_block, "item")

    return ParsedQuestReward(
        id=reward_id,
        quest_id=quest_id,
        reward_type=reward_type,
        item_id=extract_item_id_from_item_block(item_block),
        item_count=extract_item_count_from_item_block(item_block),
        xp_levels=optional_top_level_integer_value(reward_block, "xp_levels"),
        raw_snbt=reward_block,
    )


def raise_for_duplicate_reward_ids(parsed_rewards: list[ParsedQuestReward]) -> None:
    seen: dict[str, str] = {}

    for reward in parsed_rewards:
        if reward.id in seen:
            raise ValueError(
                "Duplicate reward ID found while importing reward blocks: "
                f"{reward.id} appears in both quest {seen[reward.id]} and quest "
                f"{reward.quest_id}. Refusing to import because one reward would overwrite another."
            )

        seen[reward.id] = reward.quest_id