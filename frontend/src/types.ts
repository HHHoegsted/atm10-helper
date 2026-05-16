export type Player = {
  player_uuid: string;
  display_name: string;
  handle: string;
};

export type PlayerProgressSummary = {
  player_uuid: string;
  display_name: string;
  handle: string;
  completed_task_count: number;
  complete_quest_count: number;
  partial_quest_count: number;
  known_quest_count: number;
};

export type ChapterProgressSummary = {
  player_uuid: string;
  display_name: string;
  handle: string;
  chapter_id: string;
  chapter_title: string;
  complete_quest_count: number;
  partial_quest_count: number;
  total_quest_count: number;
};

export type ProgressSummary = {
  players: PlayerProgressSummary[];
  chapters: ChapterProgressSummary[];
};

export type MissingTask = {
  task_id: string;
  task_type: string;
  title: string | null;
  item_id: string | null;
  item_count: number | null;
};

export type PartialQuest = {
  player_uuid: string;
  display_name: string;
  handle: string;
  chapter_id: string;
  chapter_title: string;
  quest_id: string;
  quest_title: string | null;
  completed_tasks: number;
  total_tasks: number;
  missing_tasks: number;
  missing_task_details: MissingTask[];
};

export type NextSteps = {
  player_filter: string | null;
  partial_quests: PartialQuest[];
};