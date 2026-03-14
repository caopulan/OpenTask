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
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
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
        position: { x: depth * 320, y: index * 180 },
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
  const [title, setTitle] = useState("OpenTask demo");
  const [taskText, setTaskText] = useState(
    "Plan and execute a small workflow, capture artifacts, and summarize the result.",
  );

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
    mutationFn: async (payload: { action: string; nodeId?: string }) => {
      if (!activeRunId) {
        throw new Error("No run selected.");
      }
      return runAction(activeRunId, payload.action, payload.nodeId ? { nodeId: payload.nodeId } : undefined);
    },
    onSuccess: (run) => {
      queryClient.setQueryData(["run", run.runId], run);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["events", run.runId] });
    },
  });

  const activeRun = runQuery.data;
  const selectedNode = activeRun?.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const graph = useMemo(() => graphFromRun(activeRun), [activeRun]);

  return (
    <div className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />
      <header className="masthead">
        <div>
          <p className="eyebrow">workflow control room</p>
          <h1>OpenTask</h1>
          <p className="lead">
            用一份 markdown workflow 驱动 OpenClaw，把运行状态、节点产物和人工控制放回同一块界面。
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

      <div className="workspace-grid">
        <aside className="panel launch-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">launch</span>
              <h2>Start a run</h2>
            </div>
            <button
              className="primary-btn"
              disabled={createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending ? "Launching..." : "Launch run"}
            </button>
          </div>

          <label className="field">
            <span>Title</span>
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="field">
            <span>Task</span>
            <textarea value={taskText} onChange={(event) => setTaskText(event.target.value)} rows={7} />
          </label>

          <div className="panel-head compact">
            <div>
              <span className="eyebrow">runs</span>
              <h2>Recent runs</h2>
            </div>
            <span className="muted">{runsQuery.isFetching ? "syncing" : "live"}</span>
          </div>
          <div className="run-list">
            {runsQuery.data?.map((run) => (
              <button
                key={run.runId}
                className={`run-card ${selectedRunId === run.runId ? "selected" : ""}`}
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
                <span className="run-meta">
                  updated {formatTime(run.updatedAt)} · {run.nodes.length} nodes
                </span>
              </button>
            ))}
          </div>
        </aside>

        <main className="panel flow-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">graph</span>
              <h2>{activeRun?.title ?? "Pick a run"}</h2>
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
                <p>Launch a run from the left panel to populate the graph and live timeline.</p>
              </div>
            )}
          </div>

          <section className="timeline-panel">
            <div className="panel-head compact">
              <div>
                <span className="eyebrow">timeline</span>
                <h2>Recent events</h2>
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

        <aside className="panel detail-panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">inspector</span>
              <h2>{selectedNode?.title ?? "Select a node"}</h2>
            </div>
            {selectedNode ? <span className={`status-chip ${statusTone(selectedNode.status)}`}>{selectedNode.status}</span> : null}
          </div>

          {selectedNode ? (
            <div className="detail-stack">
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
                <span className="detail-label">Session</span>
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
                    Approve gate
                  </button>
                ) : null}
              </div>
              <div className="note-list">
                {(selectedNode.notes.length ? selectedNode.notes : ["No notes yet."]).map((note) => (
                  <p key={note}>{note}</p>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty-detail">
              <p>Select a node in the graph to inspect dependencies, session mapping and artifacts.</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

export default App;
