from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChapterImportResult:
    source_path: Path
    chapter_count: int
    import_run_id: str


@dataclass(frozen=True)
class QuestImportResult:
    source_path: Path
    chapter_count: int
    quest_count: int
    import_run_id: str


@dataclass(frozen=True)
class TaskImportResult:
    source_path: Path
    chapter_count: int
    quest_count: int
    task_count: int
    import_run_id: str


@dataclass(frozen=True)
class LanguageImportResult:
    source_path: Path
    locale: str
    language_file_count: int
    chapter_update_count: int
    quest_update_count: int
    import_run_id: str


@dataclass(frozen=True)
class ParsedChapter:
    id: str
    filename: str
    group_id: str | None
    icon_item_id: str | None
    default_quest_shape: str | None
    raw_snbt: str


@dataclass(frozen=True)
class ParsedQuest:
    id: str
    chapter_id: str
    title: str | None
    subtitle: str | None
    description: str | None
    icon_item_id: str | None
    shape: str | None
    size: float | None
    x: float | None
    y: float | None
    raw_snbt: str


@dataclass(frozen=True)
class ParsedQuestTask:
    id: str
    quest_id: str
    task_type: str
    item_id: str | None
    item_count: int | None
    title: str | None
    raw_snbt: str