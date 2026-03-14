export type NodeStatus =
  | "pending"
  | "ready"
  | "running"
  | "waiting"
  | "completed"
  | "failed"
  | "skipped";

export type RunStatus = "draft" | "running" | "paused" | "completed" | "failed" | "cancelled";

export type WaitFor = {
  type: "next_tick" | "manual" | "file_exists";
  path?: string | null;
};

export type RunNode = {
  id: string;
  title: string;
  kind: "session_turn" | "subagent" | "wait" | "approval" | "summary";
  status: NodeStatus;
  needs: string[];
  outputsMode: "notify" | "report";
  sessionKey?: string | null;
  childSessionKey?: string | null;
  runId?: string | null;
  artifactPaths: string[];
  notes: string[];
  startedAt?: string | null;
  completedAt?: string | null;
  waitFor?: WaitFor | null;
};

export type RunState = {
  runId: string;
  workflowId: string;
  title: string;
  status: RunStatus;
  plannerSessionKey: string;
  driverSessionKey: string;
  cronJobId?: string | null;
  updatedAt: string;
  createdAt: string;
  lastEvent?: string | null;
  nodes: RunNode[];
};

export type RunEvent = {
  event: string;
  runId: string;
  timestamp: string;
  nodeId?: string | null;
  message?: string | null;
  payload: Record<string, unknown>;
};

export type CreateRunInput = {
  title?: string;
  taskText?: string;
  workflowPath?: string;
  workflowMarkdown?: string;
};
