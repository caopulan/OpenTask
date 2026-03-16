import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { createRun, fetchEvents, fetchRun, fetchRuns, runAction, subscribeRun } from "./api";
import type { RunNode, RunState } from "./types";

function formatTime(value?: string | null): string {
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

function statusTone(status: string): string {
  switch (status) {
    case "completed":
      return "tone-emerald";
    case "failed":
      return "tone-rust";
    case "running":
      return "tone-sky";
    case "waiting":
      return "tone-amber";
    case "ready":
      return "tone-ink";
    case "paused":
      return "tone-amber";
    default:
      return "tone-stone";
  }
}

function graphFromRun(run: RunState | undefined): { nodes: Node[]; edges: Edge[] } {
  if (!run) {
    return { nodes: [], edges: [] };
  }

  const depthCache = new Map<string, number>();
  const nodeMap = new Map(run.nodes.map((node) => [node.id, node]));

  const getDepth = (node: RunNode): number => {
    const cached = depthCache.get(node.id);
    if (cached !== undefined) {
      return cached;
    }
    const depth =
      node.needs.length === 0
        ? 0
        : Math.max(...node.needs.map((dep) => (nodeMap.get(dep) ? getDepth(nodeMap.get(dep)!) : 0))) + 1;
    depthCache.set(node.id, depth);
    return depth;
  };

  const columns = new Map<number, RunNode[]>();
  for (const node of run.nodes) {
    const depth = getDepth(node);
    const bucket = columns.get(depth) ?? [];
    bucket.push(node);
    columns.set(depth, bucket);
  }

  const flowNodes: Node[] = [];
  const flowEdges: Edge[] = [];

  for (const [depth, columnNodes] of columns.entries()) {
    columnNodes.forEach((node, index) => {
      flowNodes.push({
        id: node.id,
        position: { x: depth * 330, y: index * 180 },
        data: {
          label: (
            <div className={`graph-card ${statusTone(node.status)}`}>
              <div className="graph-card-head">
                <span className="graph-kind">{node.kind.replace("_", " ")}</span>
                <span className={`status-chip ${statusTone(node.status)}`}>{node.status}</span>
              </div>
              <strong>{node.title}</strong>
              <span className="graph-meta">
                {node.outputsMode} · {node.needs.length === 0 ? "entry" : `${node.needs.length} deps`}
              </span>
            </div>
          ),
        },
        draggable: false,
        selectable: true,
      });
    });
  }

  for (const node of run.nodes) {
    node.needs.forEach((dependency) => {
      flowEdges.push({
        id: `${dependency}-${node.id}`,
        source: dependency,
        target: node.id,
        animated: node.status === "running",
      });
    });
  }

  return { nodes: flowNodes, edges: flowEdges };
}

function App() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [outboundMessage, setOutboundMessage] = useState("OpenTask control-plane ping.");
  const [cronPatch, setCronPatch] = useState('{\n  "enabled": true\n}');
  const [title, setTitle] = useState("Debug OpenTask run");
  const [taskText, setTaskText] = useState("Inspect the repo and write a short report.");
  const [actionError, setActionError] = useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: fetchRuns,
    refetchInterval: 5000,
  });

  const activeRunId = useMemo(() => {
    const runIds = runsQuery.data?.map((run) => run.runId) ?? [];
    if (selectedRunId && runIds.includes(selectedRunId)) {
      return selectedRunId;
    }
    return runIds[0] ?? null;
  }, [runsQuery.data, selectedRunId]);

  const runQuery = useQuery({
    queryKey: ["run", activeRunId],
    queryFn: () => fetchRun(activeRunId!),
    enabled: Boolean(activeRunId),
  });

  const eventsQuery = useQuery({
    queryKey: ["events", activeRunId],
    queryFn: () => fetchEvents(activeRunId!),
    enabled: Boolean(activeRunId),
    refetchInterval: 4000,
  });

  useEffect(() => {
    if (!activeRunId) {
      return;
    }
    return subscribeRun(activeRunId, (run) => {
      queryClient.setQueryData(["run", activeRunId], run);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["events", activeRunId] });
    });
  }, [activeRunId, queryClient]);

  const createMutation = useMutation({
    mutationFn: () =>
      createRun({
        title,
        taskText,
      }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.setQueryData(["run", run.runId], run);
      setSelectedRunId(run.runId);
      setSelectedNodeId(null);
    },
  });

  const actionMutation = useMutation({
    mutationFn: async (payload: { action: string; nodeId?: string; message?: string; patch?: Record<string, unknown> }) => {
      if (!activeRunId) {
        throw new Error("No run selected.");
      }
      return runAction(activeRunId, payload.action, payload);
    },
    onSuccess: (run) => {
      setActionError(null);
      queryClient.setQueryData(["run", run.runId], run);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["events", run.runId] });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : "Action failed.");
    },
  });

  const activeRun = runQuery.data;
  const selectedNode = activeRun?.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const graph = useMemo(() => graphFromRun(activeRun), [activeRun]);

  function submitCronPatch() {
    try {
      const patch = JSON.parse(cronPatch) as Record<string, unknown>;
      actionMutation.mutate({ action: "patch_cron", patch });
    } catch {
      setActionError("Cron patch must be valid JSON.");
    }
  }

  return (
    <div className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />
      <header className="masthead">
        <div>
          <p className="eyebrow">registry-driven control plane</p>
          <h1>OpenTask</h1>
          <p className="lead">
            OpenClaw executes the workflow. OpenTask indexes the registry, renders the DAG, and emits explicit control
            actions without becoming the only runtime.
          </p>
        </div>
        <div className="status-row">
          <div className="hero-card">
            <span>runs</span>
            <strong>{runsQuery.data?.length ?? 0}</strong>
          </div>
          <div className="hero-card">
            <span>selected</span>
            <strong>{activeRun?.status ?? "none"}</strong>
          </div>
        </div>
      </header>

      <div className="workspace-grid control-plane-grid">
        <aside className="panel launch-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">registry</span>
              <h2>Runs</h2>
            </div>
            <span className="muted">{runsQuery.isFetching ? "syncing" : "watching"}</span>
          </div>

          <div className="run-list">
            {runsQuery.data?.map((run) => (
              <button
                key={run.runId}
                className={`run-card ${activeRunId === run.runId ? "selected" : ""}`}
                onClick={() => {
                  setSelectedRunId(run.runId);
                  setSelectedNodeId(null);
                }}
              >
                <div className="run-card-head">
                  <strong>{run.title}</strong>
                  <span className={`status-chip ${statusTone(run.status)}`}>{run.status}</span>
                </div>
                <span className="run-meta">{run.workflowId}</span>
                <span className="run-meta">{run.sourceSessionKey ?? run.rootSessionKey ?? "unbound session"}</span>
                <span className="run-meta">
                  updated {formatTime(run.updatedAt)} · {run.nodes.length} nodes
                </span>
              </button>
            ))}
          </div>

          <section className="debug-section">
            <div className="panel-head compact">
              <div>
                <span className="eyebrow">debug only</span>
                <h2>Create via API</h2>
              </div>
              <button
                className="primary-btn"
                disabled={createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                {createMutation.isPending ? "Creating..." : "Create"}
              </button>
            </div>
            <label className="field">
              <span>Title</span>
              <input value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label className="field">
              <span>Task</span>
              <textarea value={taskText} onChange={(event) => setTaskText(event.target.value)} rows={5} />
            </label>
          </section>
        </aside>

        <main className="panel flow-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">workflow graph</span>
              <h2>{activeRun?.title ?? "Select a run"}</h2>
            </div>
            <div className="control-strip">
              <button
                className="ghost-btn"
                disabled={!activeRun || actionMutation.isPending}
                onClick={() => actionMutation.mutate({ action: activeRun?.status === "paused" ? "resume" : "pause" })}
              >
                {activeRun?.status === "paused" ? "Resume" : "Pause"}
              </button>
              <button
                className="ghost-btn"
                disabled={!activeRun || actionMutation.isPending}
                onClick={() => actionMutation.mutate({ action: "tick" })}
              >
                Force tick
              </button>
            </div>
          </div>

          <div className="graph-stage">
            {activeRun ? (
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                fitView
                onNodeClick={(_, node) => setSelectedNodeId(node.id)}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable
              >
                <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} />
                <Controls showInteractive={false} />
                <MiniMap pannable zoomable />
              </ReactFlow>
            ) : (
              <div className="empty-state">
                <h3>No run selected</h3>
                <p>Pick a run from the registry index. OpenTask now treats API creation as a debug surface only.</p>
              </div>
            )}
          </div>

          <section className="timeline-panel">
            <div className="panel-head compact">
              <div>
                <span className="eyebrow">timeline</span>
                <h2>Audit trail</h2>
              </div>
              <span className="muted">{eventsQuery.data?.length ?? 0} events</span>
            </div>
            <div className="timeline-list">
              {eventsQuery.data?.slice().reverse().map((event) => (
                <article className="timeline-item" key={`${event.timestamp}-${event.event}-${event.nodeId ?? "run"}`}>
                  <div className="timeline-marker" />
                  <div>
                    <div className="timeline-head">
                      <strong>{event.event}</strong>
                      <span>{formatTime(event.timestamp)}</span>
                    </div>
                    <p>{event.message ?? "No message."}</p>
                    {event.nodeId ? <span className="timeline-tag">{event.nodeId}</span> : null}
                  </div>
                </article>
              ))}
            </div>
          </section>
        </main>

        <aside className="panel detail-panel control-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">control</span>
              <h2>{selectedNode?.title ?? activeRun?.title ?? "No run"}</h2>
            </div>
            {activeRun ? <span className={`status-chip ${statusTone(activeRun.status)}`}>{activeRun.status}</span> : null}
          </div>

          {activeRun ? (
            <div className="detail-stack">
              <div className="detail-card">
                <span className="detail-label">Source session</span>
                <strong>{activeRun.sourceSessionKey ?? "not bound"}</strong>
              </div>
              <div className="detail-card">
                <span className="detail-label">Root session</span>
                <strong>{activeRun.rootSessionKey ?? activeRun.driverSessionKey ?? "n/a"}</strong>
              </div>
              <div className="detail-card">
                <span className="detail-label">Delivery</span>
                <strong>
                  {activeRun.deliveryContext?.channel && activeRun.deliveryContext?.to
                    ? `${activeRun.deliveryContext.channel} · ${activeRun.deliveryContext.to}`
                    : "none"}
                </strong>
              </div>
              <div className="detail-card">
                <span className="detail-label">Cron job</span>
                <strong>{activeRun.cronJobId ?? "n/a"}</strong>
              </div>
              <div className="detail-card">
                <span className="detail-label">Last outbound update</span>
                <strong>{activeRun.lastProgressMessage ?? "none sent"}</strong>
                <span className="detail-muted">{formatTime(activeRun.lastProgressMessageAt)}</span>
              </div>

              <div className="composer-card">
                <span className="detail-label">Send explicit update</span>
                <textarea
                  rows={4}
                  value={outboundMessage}
                  onChange={(event) => setOutboundMessage(event.target.value)}
                />
                <button
                  className="primary-btn"
                  disabled={actionMutation.isPending || !activeRun.deliveryContext?.to}
                  onClick={() => actionMutation.mutate({ action: "send_message", message: outboundMessage })}
                >
                  Send message
                </button>
              </div>

              <div className="composer-card">
                <span className="detail-label">Patch cron</span>
                <textarea rows={5} value={cronPatch} onChange={(event) => setCronPatch(event.target.value)} />
                <button className="ghost-btn" disabled={actionMutation.isPending} onClick={submitCronPatch}>
                  Apply cron patch
                </button>
              </div>

              {selectedNode ? (
                <>
                  <div className="detail-card">
                    <span className="detail-label">Kind</span>
                    <strong>{selectedNode.kind}</strong>
                  </div>
                  <div className="detail-card">
                    <span className="detail-label">Dependencies</span>
                    <strong>{selectedNode.needs.length ? selectedNode.needs.join(", ") : "entry"}</strong>
                  </div>
                  <div className="detail-card">
                    <span className="detail-label">Output mode</span>
                    <strong>{selectedNode.outputsMode}</strong>
                  </div>
                  <div className="detail-card">
                    <span className="detail-label">Node session</span>
                    <strong>{selectedNode.childSessionKey ?? selectedNode.sessionKey ?? "pending"}</strong>
                  </div>
                  <div className="detail-card">
                    <span className="detail-label">Artifacts</span>
                    <ul className="artifact-list">
                      {selectedNode.artifactPaths.length ? (
                        selectedNode.artifactPaths.map((artifact) => <li key={artifact}>{artifact}</li>)
                      ) : (
                        <li>none yet</li>
                      )}
                    </ul>
                  </div>
                  <div className="detail-card">
                    <span className="detail-label">Node memory</span>
                    <ul className="artifact-list">
                      {selectedNode.workingMemory ? (
                        Object.entries(selectedNode.workingMemory)
                          .filter(([, value]) => Boolean(value))
                          .map(([label, value]) => <li key={label}>{`${label}: ${value}`}</li>)
                      ) : (
                        <li>not configured</li>
                      )}
                    </ul>
                  </div>
                  <div className="detail-actions">
                    <button
                      className="ghost-btn"
                      disabled={actionMutation.isPending}
                      onClick={() => actionMutation.mutate({ action: "retry", nodeId: selectedNode.id })}
                    >
                      Retry
                    </button>
                    <button
                      className="ghost-btn"
                      disabled={actionMutation.isPending}
                      onClick={() => actionMutation.mutate({ action: "skip", nodeId: selectedNode.id })}
                    >
                      Skip
                    </button>
                    {selectedNode.kind === "approval" ? (
                      <button
                        className="primary-btn"
                        disabled={actionMutation.isPending}
                        onClick={() => actionMutation.mutate({ action: "approve", nodeId: selectedNode.id })}
                      >
                        Approve
                      </button>
                    ) : null}
                  </div>
                  <div className="note-list">
                    {(selectedNode.notes.length ? selectedNode.notes : ["No notes yet."]).map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                  </div>
                </>
              ) : (
                <div className="empty-detail">
                  <p>Select a node to inspect session ownership, outputs, and control actions.</p>
                </div>
              )}

              {actionError ? <div className="error-banner">{actionError}</div> : null}
            </div>
          ) : (
            <div className="empty-detail">
              <p>Choose a run from the left pane to inspect its session binding and control surface.</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

export default App;
