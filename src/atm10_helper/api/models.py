from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class PlayerResponse(BaseModel):
    player_uuid: str
    display_name: str
    handle: str


class PlayerProgressSummaryResponse(BaseModel):
    player_uuid: str
    display_name: str
    handle: str
    completed_task_count: int
    complete_quest_count: int
    partial_quest_count: int
    known_quest_count: int


class ChapterProgressSummaryResponse(BaseModel):
    player_uuid: str
    display_name: str
    handle: str
    chapter_id: str
    chapter_title: str
    complete_quest_count: int
    partial_quest_count: int
    total_quest_count: int


class ProgressSummaryResponse(BaseModel):
    players: list[PlayerProgressSummaryResponse]
    chapters: list[ChapterProgressSummaryResponse]


class MissingTaskResponse(BaseModel):
    task_id: str
    task_type: str
    title: str | None
    item_id: str | None
    item_count: int | None


class PartialQuestResponse(BaseModel):
    player_uuid: str
    display_name: str
    handle: str
    chapter_id: str
    chapter_title: str
    quest_id: str
    quest_title: str | None
    completed_tasks: int
    total_tasks: int
    missing_tasks: int
    missing_task_details: list[MissingTaskResponse]


class NextStepsResponse(BaseModel):
    player_filter: str | None
    partial_quests: list[PartialQuestResponse]