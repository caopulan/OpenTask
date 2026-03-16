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

export type DeliveryContext = {
  channel?: string | null;
  to?: string | null;
  accountId?: string | null;
  threadId?: string | null;
};

export type NodeWorkingMemory = {
  plan?: string | null;
  findings?: string | null;
  progress?: string | null;
  handoff?: string | null;
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
  workingMemory?: NodeWorkingMemory | null;
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
  sourceSessionKey?: string | null;
  sourceAgentId?: string | null;
  deliveryContext?: DeliveryContext | null;
  rootSessionKey?: string | null;
  plannerSessionKey?: string | null;
  driverSessionKey?: string | null;
  cronJobId?: string | null;
  updatedAt: string;
  createdAt: string;
  lastEvent?: string | null;
  lastProgressMessage?: string | null;
  lastProgressMessageAt?: string | null;
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
  sourceSessionKey?: string;
  sourceAgentId?: string;
  deliveryContext?: DeliveryContext;
  rootSessionKey?: string;
};
