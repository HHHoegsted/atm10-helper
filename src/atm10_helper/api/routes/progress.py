from __future__ import annotations

from fastapi import APIRouter

from atm10_helper.api.formatting import clean_player_handle
from atm10_helper.api.models import (
    ChapterProgressSummaryResponse,
    PlayerProgressSummaryResponse,
    PlayerResponse,
    ProgressSummaryResponse,
)
from atm10_helper.db import get_players, get_progress_summary

router = APIRouter(prefix="/api")


@router.get("/players", response_model=list[PlayerResponse])
def list_players() -> list[PlayerResponse]:
    players = get_players()

    return [
        PlayerResponse(
            player_uuid=player.player_uuid,
            display_name=player.display_name,
            handle=clean_player_handle(player.display_name),
        )
        for player in players
    ]


@router.get("/progress-summary", response_model=ProgressSummaryResponse)
def progress_summary(
    player: str | None = None,
) -> ProgressSummaryResponse:
    summary = get_progress_summary()

    selected_player_uuids = {
        summary_player.player_uuid
        for summary_player in summary.players
        if player is None or player.casefold() in summary_player.display_name.casefold()
    }

    return ProgressSummaryResponse(
        players=[
            PlayerProgressSummaryResponse(
                player_uuid=summary_player.player_uuid,
                display_name=summary_player.display_name,
                handle=clean_player_handle(summary_player.display_name),
                completed_task_count=summary_player.completed_task_count,
                complete_quest_count=summary_player.complete_quest_count,
                partial_quest_count=summary_player.partial_quest_count,
                known_quest_count=summary_player.known_quest_count,
            )
            for summary_player in summary.players
            if summary_player.player_uuid in selected_player_uuids
        ],
        chapters=[
            ChapterProgressSummaryResponse(
                player_uuid=chapter.player_uuid,
                display_name=chapter.display_name,
                handle=clean_player_handle(chapter.display_name),
                chapter_id=chapter.chapter_id,
                chapter_title=chapter.chapter_title,
                complete_quest_count=chapter.complete_quest_count,
                partial_quest_count=chapter.partial_quest_count,
                total_quest_count=chapter.total_quest_count,
            )
            for chapter in summary.chapters
            if chapter.player_uuid in selected_player_uuids
        ],
    )