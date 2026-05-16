CREATE EXTENSION
IF NOT EXISTS pgcrypto;

CREATE TABLE import_runs
(
	id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
	source_label text NOT NULL,
	source_path text,
	modpack_slug text NOT NULL DEFAULT 'atm10',
	started_at timestamptz NOT NULL DEFAULT now(),
	finished_at timestamptz,
	notes text
);

CREATE TABLE quest_chapters
(
	id text PRIMARY KEY,
	filename text NOT NULL UNIQUE,
	group_id text,
	title text,
	subtitle text,
	icon_item_id text,
	order_index integer,
	progression_mode text,
	raw_snbt text NOT NULL,
	imported_at timestamptz NOT NULL DEFAULT now(),
	import_run_id uuid REFERENCES import_runs(id) ON DELETE SET NULL
);

CREATE TABLE quests
(
	id text PRIMARY KEY,
	chapter_id text NOT NULL REFERENCES quest_chapters(id) ON DELETE CASCADE,
	title text,
	subtitle text,
	description text,
	icon_item_id text,
	shape text,
	size numeric,
	x numeric,
	y numeric,
	raw_snbt text NOT NULL,
	imported_at timestamptz NOT NULL DEFAULT now(),
	import_run_id uuid REFERENCES import_runs(id) ON DELETE SET NULL
);

CREATE INDEX idx_quests_chapter_id ON quests(chapter_id);

CREATE TABLE quest_dependencies
(
	quest_id text NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
	depends_on_quest_id text NOT NULL,
	PRIMARY KEY (quest_id, depends_on_quest_id)
);

CREATE INDEX idx_quest_dependencies_depends_on
    ON quest_dependencies(depends_on_quest_id);

CREATE TABLE quest_tasks
(
	id text PRIMARY KEY,
	quest_id text NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
	task_type text NOT NULL,
	item_id text,
	item_count integer,
	title text,
	raw_snbt text NOT NULL,
	imported_at timestamptz NOT NULL DEFAULT now(),
	import_run_id uuid REFERENCES import_runs(id) ON DELETE SET NULL
);

CREATE INDEX idx_quest_tasks_quest_id ON quest_tasks(quest_id);
CREATE INDEX idx_quest_tasks_task_type ON quest_tasks(task_type);
CREATE INDEX idx_quest_tasks_item_id ON quest_tasks(item_id);

CREATE TABLE quest_rewards
(
	id text PRIMARY KEY,
	quest_id text NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
	reward_type text NOT NULL,
	item_id text,
	item_count integer,
	xp_levels integer,
	raw_snbt text NOT NULL,
	imported_at timestamptz NOT NULL DEFAULT now(),
	import_run_id uuid REFERENCES import_runs(id) ON DELETE SET NULL
);

CREATE INDEX idx_quest_rewards_quest_id ON quest_rewards(quest_id);
CREATE INDEX idx_quest_rewards_reward_type ON quest_rewards(reward_type);

CREATE TABLE players
(
	uuid text PRIMARY KEY,
	display_name text NOT NULL,
	raw_snbt text,
	imported_at timestamptz NOT NULL DEFAULT now(),
	import_run_id uuid REFERENCES import_runs(id) ON DELETE SET NULL
);

CREATE TABLE player_task_progress
(
	player_uuid text NOT NULL REFERENCES players(uuid) ON DELETE CASCADE,
	task_id text NOT NULL,
	progress_value bigint NOT NULL,
	imported_at timestamptz NOT NULL DEFAULT now(),
	import_run_id uuid REFERENCES import_runs(id) ON DELETE SET NULL,
	PRIMARY KEY (player_uuid, task_id)
);

CREATE INDEX idx_player_task_progress_task_id
    ON player_task_progress(task_id);

CREATE VIEW player_completed_tasks
AS
	SELECT
		ptp.player_uuid,
		p.display_name,
		ptp.task_id,
		qt.quest_id,
		q.chapter_id,
		ptp.progress_value
	FROM player_task_progress ptp
		JOIN players p
		ON p.uuid = ptp.player_uuid
		LEFT JOIN quest_tasks qt
		ON qt.id = ptp.task_id
		LEFT JOIN quests q
		ON q.id = qt.quest_id
	WHERE ptp.progress_value > 0;

CREATE VIEW quest_completion_by_player
AS
	SELECT
		p.uuid AS player_uuid,
		p.display_name,
		q.id AS quest_id,
		q.title AS quest_title,
		q.chapter_id,
		COUNT(qt.id) AS total_tasks,
		COUNT(pct.task_id) AS completed_tasks,
		CASE
        WHEN COUNT(qt.id) = 0 THEN false
        WHEN COUNT(qt.id) = COUNT(pct.task_id) THEN true
        ELSE false
    END AS is_complete
	FROM players p
CROSS JOIN quests q
		LEFT JOIN quest_tasks qt
		ON qt.quest_id = q.id
		LEFT JOIN player_completed_tasks pct
		ON pct.player_uuid = p.uuid
			AND pct.task_id = qt.id
	GROUP BY
    p.uuid,
    p.display_name,
    q.id,
    q.title,
    q.chapter_id;