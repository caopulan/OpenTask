import type { DeliveryContext, RunState, RunNode, RunNodeDocument } from "./types";

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
  completed: number;
  running: number;
  actionable: number;
  blocked: number;
  progress: number;
} {
  if (!run) {
    return { total: 0, completed: 0, running: 0, actionable: 0, blocked: 0, progress: 0 };
  }
  const total = run.nodes.length;
  const completed = run.nodes.filter((node) => ["completed", "failed", "skipped"].includes(node.status)).length;
  const running = run.nodes.filter((node) => node.status === "running").length;
  const actionable = run.nodes.filter((node) => ["running", "ready"].includes(node.status)).length;
  const blocked = run.nodes.filter((node) => ["pending", "waiting"].includes(node.status)).length;
  return {
    total,
    completed,
    running,
    actionable,
    blocked,
    progress: total === 0 ? 0 : Math.round((completed / total) * 100),
  };
}

export function pickDefaultNodeId(run: RunState | undefined): string | null {
  if (!run || run.nodes.length === 0) {
    return null;
  }
  const current = run.nodes.find((node) => ["running", "ready", "waiting"].includes(node.status));
  if (current) {
    return current.id;
  }
  const latestCompleted = [...run.nodes]
    .filter((node) => node.completedAt)
    .sort((left, right) => Date.parse(right.completedAt ?? "") - Date.parse(left.completedAt ?? ""))[0];
  return latestCompleted?.id ?? run.nodes[0]?.id ?? null;
}

export function currentFocusNode(run: RunState | undefined): RunNode | null {
  if (!run) {
    return null;
  }
  const nodeId = pickDefaultNodeId(run);
  return run.nodes.find((node) => node.id === nodeId) ?? null;
}

export function currentFocusLabel(run: RunState | undefined): string {
  const focus = currentFocusNode(run);
  if (!focus) {
    return "No active stages";
  }
  if (["completed", "failed", "skipped"].includes(focus.status)) {
    return `Recently finished: ${focus.title}`;
  }
  return `${focus.title} is ${focus.status}`;
}

export function nodeDependencyLabel(node: RunNode): string {
  if (node.needs.length === 0) {
    return "Entry stage";
  }
  if (node.needs.length === 1) {
    return `Depends on ${node.needs[0]}`;
  }
  return `${node.needs.length} dependencies`;
}

export function countDeclaredDocuments(node: RunNode): number {
  const memoryDocs = Object.values(node.workingMemory ?? {}).filter(Boolean).length;
  return new Set([...node.artifactPaths, ...Object.values(node.workingMemory ?? {}).filter(Boolean)]).size || memoryDocs;
}

export function formatEventLabel(event: string): string {
  return event.replaceAll(".", " ");
}

export function documentPreviewLabel(document: RunNodeDocument): string {
  return document.truncated ? `${document.label} preview` : document.label;
}
