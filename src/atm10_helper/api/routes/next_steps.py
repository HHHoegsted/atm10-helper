from __future__ import annotations

from fastapi import APIRouter

from atm10_helper.api.formatting import clean_player_handle
from atm10_helper.api.models import (
    MissingTaskResponse,
    NextStepsResponse,
    PartialQuestResponse,
)
from atm10_helper.db import get_partial_quests

router = APIRouter(prefix="/api")


@router.get("/next-steps", response_model=NextStepsResponse)
def next_steps(
    player: str | None = None,
    limit: int = 20,
    missing_limit: int = 10,
) -> NextStepsResponse:
    partial_quests = get_partial_quests(player_filter=player)
    displayed_quests = partial_quests[:limit]

    return NextStepsResponse(
        player_filter=player,
        partial_quests=[
            PartialQuestResponse(
                player_uuid=quest.player_uuid,
                display_name=quest.display_name,
                handle=clean_player_handle(quest.display_name),
                chapter_id=quest.chapter_id,
                chapter_title=quest.chapter_title,
                quest_id=quest.quest_id,
                quest_title=quest.quest_title,
                completed_tasks=quest.completed_tasks,
                total_tasks=quest.total_tasks,
                missing_tasks=quest.missing_tasks,
                missing_task_details=[
                    MissingTaskResponse(
                        task_id=task.task_id,
                        task_type=task.task_type,
                        title=task.title,
                        item_id=task.item_id,
                        item_count=task.item_count,
                    )
                    for task in quest.missing_task_details[:missing_limit]
                ],
            )
            for quest in displayed_quests
        ],
    )