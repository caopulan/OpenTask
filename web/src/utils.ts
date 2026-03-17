import type { DeliveryContext, RunState, RunNode } from "./types";

export function formatTime(value?: string | null): string {
  if (!value) {
    return "n/a";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function statusTone(status: string): string {
  switch (status) {
    case "completed":
      return "status-completed";
    case "failed":
    case "cancelled":
      return "status-failed";
    case "running":
      return "status-running";
    case "waiting":
      return "status-waiting";
    case "ready":
      return "status-ready";
    default:
      return "status-idle";
  }
}

export function statusBgTone(status: string): string {
  switch (status) {
    case "completed":
      return "bg-completed";
    case "failed":
    case "cancelled":
      return "bg-failed";
    case "running":
      return "bg-running";
    case "waiting":
      return "bg-waiting";
    case "ready":
      return "bg-ready";
    default:
      return "bg-idle";
  }
}

export function eventTone(event: string): string {
  if (event.endsWith("failed")) {
    return "status-failed";
  }
  if (event.endsWith("completed")) {
    return "status-completed";
  }
  if (event.includes("paused") || event.includes("waiting") || event.includes("approve")) {
    return "status-waiting";
  }
  if (event.includes("ready") || event.includes("resumed")) {
    return "status-ready";
  }
  return "status-running";
}

export function nodeKindLabel(kind: RunNode["kind"]): string {
  return kind.replace("_", " ");
}

export function deliveryLabel(context?: DeliveryContext | null): string {
  if (!context?.channel) {
    return "not wired";
  }
  const parts = [context.channel, context.to, context.threadId].filter(Boolean);
  return parts.join(" / ");
}

export function summarizeRun(run: RunState | undefined): {
  total: number;
  terminal: number;
  running: number;
  actionable: number;
  progress: number;
} {
  if (!run) {
    return { total: 0, terminal: 0, running: 0, actionable: 0, progress: 0 };
  }
  const total = run.nodes.length;
  const terminal = run.nodes.filter((node) => ["completed", "failed", "skipped"].includes(node.status)).length;
  const running = run.nodes.filter((node) => node.status === "running").length;
  const actionable = run.nodes.filter((node) => ["ready", "waiting"].includes(node.status)).length;
  return {
    total,
    terminal,
    running,
    actionable,
    progress: total === 0 ? 0 : Math.round((terminal / total) * 100),
  };
}
