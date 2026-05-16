import type { NextSteps, Player, ProgressSummary } from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8020";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export function getPlayers(): Promise<Player[]> {
  return fetchJson<Player[]>("/api/players");
}

export function getProgressSummary(player: string): Promise<ProgressSummary> {
  const searchParams = new URLSearchParams({ player });

  return fetchJson<ProgressSummary>(`/api/progress-summary?${searchParams.toString()}`);
}

export function getNextSteps(player: string, limit = 20): Promise<NextSteps> {
  const searchParams = new URLSearchParams({
    player,
    limit: String(limit),
  });

  return fetchJson<NextSteps>(`/api/next-steps?${searchParams.toString()}`);
}