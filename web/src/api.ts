import type { CreateRunInput, RunEvent, RunState } from "./types";

const apiBase = import.meta.env.VITE_API_BASE?.replace(/\/$/, "") ?? "";

function toHttpUrl(path: string): string {
  return `${apiBase}${path}`;
}

function toWebSocketUrl(path: string): string {
  if (apiBase) {
    const url = new URL(apiBase + path);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url.toString();
  }
  const url = new URL(path, window.location.href);
  url.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(toHttpUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchRuns(): Promise<RunState[]> {
  return request<RunState[]>("/api/runs");
}

export function fetchRun(runId: string): Promise<RunState> {
  return request<RunState>(`/api/runs/${runId}`);
}

export function fetchEvents(runId: string): Promise<RunEvent[]> {
  return request<RunEvent[]>(`/api/runs/${runId}/events`);
}

export function createRun(input: CreateRunInput): Promise<RunState> {
  return request<RunState>("/api/runs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function runAction(
  runId: string,
  action: string,
  payload?: { nodeId?: string },
): Promise<RunState> {
  return request<RunState>(`/api/runs/${runId}/actions/${action}`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export function subscribeRun(runId: string, onMessage: (run: RunState) => void): () => void {
  const ws = new WebSocket(toWebSocketUrl(`/api/runs/${runId}/stream`));
  ws.onmessage = (event) => {
    onMessage(JSON.parse(event.data) as RunState);
  };
  return () => {
    ws.close();
  };
}
