import { useEffect, useMemo, useState } from "react";

import { getNextSteps, getPlayers, getProgressSummary } from "./api";
import type { NextSteps, Player, ProgressSummary } from "./types";

type LoadState = "idle" | "loading" | "ready" | "error";

const preferredDefaultHandle = "Tureni_DK";

export default function App() {
  const [players, setPlayers] = useState<Player[]>([]);
  const [selectedHandle, setSelectedHandle] = useState<string>("");
  const [progressSummary, setProgressSummary] = useState<ProgressSummary | null>(null);
  const [nextSteps, setNextSteps] = useState<NextSteps | null>(null);
  const [playersState, setPlayersState] = useState<LoadState>("idle");
  const [detailsState, setDetailsState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const selectedPlayer = useMemo(
    () => players.find((player) => player.handle === selectedHandle) ?? null,
    [players, selectedHandle],
  );

  const selectedProgress = progressSummary?.players[0] ?? null;
  const selectedChapters = progressSummary?.chapters ?? [];
  const selectedPartialQuests = nextSteps?.partial_quests ?? [];

  useEffect(() => {
    let isMounted = true;

    async function loadPlayers() {
      setPlayersState("loading");
      setErrorMessage(null);

      try {
        const loadedPlayers = await getPlayers();

        if (!isMounted) {
          return;
        }

        setPlayers(loadedPlayers);

        const preferredPlayer =
          loadedPlayers.find((player) => player.handle === preferredDefaultHandle) ??
          loadedPlayers[0] ??
          null;

        setSelectedHandle(preferredPlayer?.handle ?? "");
        setPlayersState("ready");
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setPlayersState("error");
        setErrorMessage(error instanceof Error ? error.message : "Failed to load players.");
      }
    }

    loadPlayers();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedHandle) {
      return;
    }

    let isMounted = true;

    async function loadPlayerDetails() {
      setDetailsState("loading");
      setErrorMessage(null);

      try {
        const [loadedProgressSummary, loadedNextSteps] = await Promise.all([
          getProgressSummary(selectedHandle),
          getNextSteps(selectedHandle, 20),
        ]);

        if (!isMounted) {
          return;
        }

        setProgressSummary(loadedProgressSummary);
        setNextSteps(loadedNextSteps);
        setDetailsState("ready");
      } catch (error) {
        if (!isMounted) {
          return;
        }

        setDetailsState("error");
        setErrorMessage(error instanceof Error ? error.message : "Failed to load player details.");
      }
    }

    loadPlayerDetails();

    return () => {
      isMounted = false;
    };
  }, [selectedHandle]);

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">ATM10 Helper</p>
          <h1>Quest recovery dashboard</h1>
          <p className="hero-copy">
            Pick one player and see current quest progress plus unfinished quests with concrete
            missing tasks.
          </p>
        </div>

        <label className="player-picker">
          <span>Player</span>
          <select
            value={selectedHandle}
            onChange={(event) => setSelectedHandle(event.target.value)}
            disabled={playersState !== "ready" || players.length === 0}
          >
            {players.map((player) => (
              <option key={player.player_uuid} value={player.handle}>
                {player.handle}
              </option>
            ))}
          </select>
        </label>
      </header>

      {errorMessage ? <section className="error-card">{errorMessage}</section> : null}

      {playersState === "loading" ? (
        <section className="card">Loading players…</section>
      ) : null}

      {selectedPlayer ? (
        <section className="section-heading">
          <p className="eyebrow">Selected player</p>
          <h2>{selectedPlayer.handle}</h2>
        </section>
      ) : null}

      {detailsState === "loading" ? (
        <section className="card">Loading player details…</section>
      ) : null}

      {detailsState === "ready" && selectedProgress ? (
        <>
          <section className="stats-grid">
            <StatCard label="Completed tasks" value={selectedProgress.completed_task_count} />
            <StatCard label="Complete quests" value={selectedProgress.complete_quest_count} />
            <StatCard label="Partial quests" value={selectedProgress.partial_quest_count} />
            <StatCard label="Quests with progress" value={selectedProgress.known_quest_count} />
          </section>

          <section className="content-grid">
            <section className="card">
              <div className="card-header">
                <div>
                  <p className="eyebrow">Progress</p>
                  <h2>Top chapters</h2>
                </div>
              </div>

              <div className="chapter-list">
                {selectedChapters.slice(0, 12).map((chapter) => (
                  <article className="chapter-row" key={chapter.chapter_id}>
                    <div>
                      <h3>{chapter.chapter_title}</h3>
                      <p>
                        {chapter.total_quest_count} quests with progress ·{" "}
                        {chapter.partial_quest_count} partial
                      </p>
                    </div>
                    <strong>{chapter.complete_quest_count}</strong>
                  </article>
                ))}
              </div>
            </section>

            <section className="card">
              <div className="card-header">
                <div>
                  <p className="eyebrow">Next steps</p>
                  <h2>Partial quests</h2>
                </div>
              </div>

              <div className="quest-list">
                {selectedPartialQuests.map((quest) => (
                  <article className="quest-card" key={quest.quest_id}>
                    <div className="quest-title-row">
                      <div>
                        <p className="quest-chapter">{quest.chapter_title}</p>
                        <h3>{quest.quest_title || "Unnamed quest"}</h3>
                      </div>
                      <span>
                        {quest.completed_tasks}/{quest.total_tasks}
                      </span>
                    </div>

                    {quest.missing_task_details.length > 0 ? (
                      <ul className="missing-list">
                        {quest.missing_task_details.slice(0, 6).map((task) => (
                          <li key={task.task_id}>
                            {task.item_count && task.item_count > 1 ? (
                              <strong>x{task.item_count}</strong>
                            ) : (
                              <strong>item</strong>
                            )}
                            <span>{task.item_id ?? task.title ?? `${task.task_type} task`}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="muted">No missing task details imported.</p>
                    )}
                  </article>
                ))}
              </div>
            </section>
          </section>
        </>
      ) : null}
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <article className="stat-card">
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}