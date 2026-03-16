import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  type Edge,
  MarkerType,
  type Node,
  Position,
  ReactFlow,
} from "@xyflow/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, useTransition } from "react";

import { createRun, fetchEvents, fetchRun, fetchRuns, runAction, subscribeRun } from "./api";
import type { DeliveryContext, RunEvent, RunNode, RunState } from "./types";

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
      return "is-completed";
    case "failed":
      return "is-failed";
    case "running":
      return "is-running";
    case "waiting":
      return "is-waiting";
    case "ready":
      return "is-ready";
    case "paused":
      return "is-paused";
    case "cancelled":
      return "is-failed";
    default:
      return "is-idle";
  }
}

function eventTone(event: string): string {
  if (event.endsWith("failed")) {
    return "is-failed";
  }
  if (event.endsWith("completed")) {
    return "is-completed";
  }
  if (event.includes("paused") || event.includes("waiting") || event.includes("approve")) {
    return "is-waiting";
  }
  if (event.includes("ready") || event.includes("resumed")) {
    return "is-ready";
  }
  return "is-running";
}

function nodeKindLabel(kind: RunNode["kind"]): string {
  return kind.replace("_", " ");
}

function deliveryLabel(context?: DeliveryContext | null): string {
  if (!context?.channel) {
    return "not wired";
  }
  const parts = [context.channel, context.to, context.threadId].filter(Boolean);
  return parts.join(" / ");
}

function summarizeRun(run: RunState | undefined): {
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

function FlowNodeLabel({ node, index }: { node: RunNode; index: number }) {
  return (
    <div className={`flow-node ${statusTone(node.status)}`}>
      <div className="flow-node-stripe" />
      <div className="flow-node-index">{String(index + 1).padStart(2, "0")}</div>
      <div className="flow-node-body">
        <div className="flow-node-head">
          <span className="flow-node-kind">{nodeKindLabel(node.kind)}</span>
          <span className={`status-pill ${statusTone(node.status)}`}>{node.status}</span>
        </div>
        <strong>{node.title}</strong>
        <p>{node.needs.length === 0 ? "entry signal" : `${node.needs.length} prerequisite ${node.needs.length === 1 ? "edge" : "edges"}`}</p>
        <div className="flow-node-meta">
          <span>{node.outputsMode}</span>
          <span>{node.artifactPaths.length} artifact paths</span>
        </div>
      </div>
    </div>
  );
}

function SignalTile({
  label,
  value,
  detail,
  tone,
  dense = false,
}: {
  label: string;
  value: string | number;
  detail: string;
  tone: string;
  dense?: boolean;
}) {
  return (
    <article className={`signal-tile ${tone} ${dense ? "is-dense" : ""}`}>
      <span className="signal-label">{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function LedgerRow({ label, value, subtle }: { label: string; value: string; subtle?: string }) {
  return (
    <div className="ledger-row">
      <span>{label}</span>
      <strong>{value}</strong>
      {subtle ? <em>{subtle}</em> : null}
    </div>
  );
}

function graphFromRun(run: RunState | undefined): { nodes: Node[]; edges: Edge[] } {
  if (!run) {
    return { nodes: [], edges: [] };
  }

  const nodeMap = new Map(run.nodes.map((node) => [node.id, node]));
  const depthCache = new Map<string, number>();

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
  run.nodes.forEach((node) => {
    const depth = getDepth(node);
    const bucket = columns.get(depth) ?? [];
    bucket.push(node);
    columns.set(depth, bucket);
  });

  const flowNodes: Node[] = [];
  const flowEdges: Edge[] = [];
  let visualIndex = 0;

  Array.from(columns.entries())
    .sort(([left], [right]) => left - right)
    .forEach(([depth, columnNodes]) => {
      columnNodes
        .slice()
        .sort((left, right) => left.needs.length - right.needs.length || left.title.localeCompare(right.title))
        .forEach((node, index) => {
          flowNodes.push({
            id: node.id,
            position: { x: 90 + depth * 360, y: 72 + index * 208 + (depth % 2 === 0 ? 0 : 34) },
            sourcePosition: Position.Right,
            targetPosition: Position.Left,
            draggable: false,
            selectable: true,
            data: {
              label: <FlowNodeLabel node={node} index={visualIndex} />,
            },
          });
          visualIndex += 1;
        });
    });

  run.nodes.forEach((node) => {
    node.needs.forEach((dependency) => {
      flowEdges.push({
        id: `${dependency}-${node.id}`,
        source: dependency,
        target: node.id,
        animated: node.status === "running",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: {
          strokeWidth: 1.6,
        },
      });
    });
  });

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
  const [isSelecting, startSelection] = useTransition();

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
      startSelection(() => {
        setSelectedRunId(run.runId);
        setSelectedNodeId(null);
      });
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
  const effectiveSelectedNodeId = useMemo(() => {
    if (!activeRun) {
      return null;
    }
    if (selectedNodeId && activeRun.nodes.some((node) => node.id === selectedNodeId)) {
      return selectedNodeId;
    }
    return (
      activeRun.nodes.find((node) => ["running", "ready", "waiting"].includes(node.status))?.id ??
      activeRun.nodes[0]?.id ??
      null
    );
  }, [activeRun, selectedNodeId]);
  const selectedNode = activeRun?.nodes.find((node) => node.id === effectiveSelectedNodeId) ?? null;
  const graph = useMemo(() => graphFromRun(activeRun), [activeRun]);
  const activeStats = useMemo(() => summarizeRun(activeRun), [activeRun]);
  const latestEvents = useMemo(() => (eventsQuery.data ? [...eventsQuery.data].reverse() : []), [eventsQuery.data]);

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
      <div className="glow glow-left" />
      <div className="glow glow-right" />

      <header className="hero">
        <section className="hero-copy">
          <p className="kicker">OpenTask / editorial control room</p>
          <h1>Registry visible. Runtime sovereign.</h1>
          <p className="hero-text">
            OpenClaw remains the execution engine. This surface reads the registry like a signal desk, tracks session
            bindings, and emits precise human overrides without pretending to be the runtime.
          </p>
        </section>

        <section className="hero-signals">
          <SignalTile
            label="indexed runs"
            value={runsQuery.data?.length ?? 0}
            detail={runsQuery.isFetching ? "registry sync in flight" : "registry watcher steady"}
            tone="is-accent"
          />
          <SignalTile
            label="active progress"
            value={`${activeStats.progress}%`}
            detail={
              activeRun
                ? `${activeStats.terminal}/${activeStats.total} terminal · ${activeStats.running} running`
                : "no run selected"
            }
            tone="is-cool"
          />
          <SignalTile
            label="actionable nodes"
            value={activeStats.actionable}
            detail={activeRun ? `${activeRun.status} · updated ${formatTime(activeRun.updatedAt)}` : "awaiting selection"}
            tone="is-warning"
            dense
          />
          <SignalTile
            label="delivery line"
            value={activeRun?.deliveryContext?.channel ?? "none"}
            detail={activeRun ? deliveryLabel(activeRun.deliveryContext) : "no outbound route bound"}
            tone="is-ink"
            dense
          />
        </section>
      </header>

      <div className="control-grid">
        <aside className="panel-surface run-rail">
          <div className="section-head">
            <div>
              <p className="kicker">registry ledger</p>
              <h2>Runs</h2>
            </div>
            <span className="section-meta">{isSelecting ? "switching" : runsQuery.isFetching ? "syncing" : "live"}</span>
          </div>

          <div className="run-list">
            {runsQuery.data?.length ? (
              runsQuery.data.map((run) => {
                const summary = summarizeRun(run);
                return (
                  <button
                    key={run.runId}
                    className={`run-entry ${activeRunId === run.runId ? "is-selected" : ""}`}
                    onClick={() =>
                      startSelection(() => {
                        setSelectedRunId(run.runId);
                        setSelectedNodeId(null);
                      })
                    }
                    type="button"
                  >
                    <div className={`run-entry-stripe ${statusTone(run.status)}`} />
                    <div className="run-entry-top">
                      <strong>{run.title}</strong>
                      <span className={`status-pill ${statusTone(run.status)}`}>{run.status}</span>
                    </div>
                    <p className="run-entry-id">{run.runId}</p>
                    <div className="run-entry-body">
                      <span>{run.workflowId}</span>
                      <span>{run.sourceSessionKey ?? run.rootSessionKey ?? "session unbound"}</span>
                    </div>
                    <div className="run-entry-footer">
                      <span>{summary.total} nodes</span>
                      <span>{summary.progress}% resolved</span>
                      <span>updated {formatTime(run.updatedAt)}</span>
                    </div>
                  </button>
                );
              })
            ) : (
              <div className="empty-block">
                <h3>No indexed runs</h3>
                <p>Point the API at a populated registry root or use the operator hatch to create a debug run.</p>
              </div>
            )}
          </div>

          <details className="operator-hatch">
            <summary>
              <div>
                <p className="kicker">operator hatch</p>
                <h3>Debug create surface</h3>
              </div>
              <span className="section-meta">API-only</span>
            </summary>
            <div className="hatch-body">
              <label className="field">
                <span>Title</span>
                <input value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label className="field">
                <span>Task</span>
                <textarea rows={5} value={taskText} onChange={(event) => setTaskText(event.target.value)} />
              </label>
              <button className="primary-btn" disabled={createMutation.isPending} onClick={() => createMutation.mutate()} type="button">
                {createMutation.isPending ? "creating..." : "create debug run"}
              </button>
              {createMutation.error ? (
                <div className="error-banner">{createMutation.error instanceof Error ? createMutation.error.message : "Create failed."}</div>
              ) : null}
            </div>
          </details>
        </aside>

        <main className="panel-surface stage">
          <div className="section-head stage-head">
            <div>
              <p className="kicker">orchestration stage</p>
              <h2>{activeRun?.title ?? "Select a run"}</h2>
              <p className="stage-copy">
                {activeRun
                  ? `${activeRun.workflowId} · source ${activeRun.sourceAgentId ?? "main"} · last event ${activeRun.lastEvent ?? "not recorded"}`
                  : "Choose a registry-backed run to inspect its graph, edges, and control envelope."}
              </p>
            </div>

            <div className="header-actions">
              <button
                className="secondary-btn"
                disabled={!activeRun || actionMutation.isPending}
                onClick={() => actionMutation.mutate({ action: activeRun?.status === "paused" ? "resume" : "pause" })}
                type="button"
              >
                {activeRun?.status === "paused" ? "resume" : "pause"}
              </button>
              <button
                className="secondary-btn"
                disabled={!activeRun || actionMutation.isPending}
                onClick={() => actionMutation.mutate({ action: "tick" })}
                type="button"
              >
                force tick
              </button>
            </div>
          </div>

          {activeRun ? (
            <div className="status-ribbon">
              <div className="ribbon-cell">
                <span>root session</span>
                <strong>{activeRun.rootSessionKey ?? activeRun.driverSessionKey ?? "n/a"}</strong>
              </div>
              <div className="ribbon-cell">
                <span>delivery</span>
                <strong>{deliveryLabel(activeRun.deliveryContext)}</strong>
              </div>
              <div className="ribbon-cell">
                <span>node balance</span>
                <strong>
                  {activeStats.running} running · {activeStats.actionable} actionable
                </strong>
              </div>
              <div className="ribbon-cell">
                <span>last progress note</span>
                <strong>{activeRun.lastProgressMessage ?? "none sent"}</strong>
              </div>
            </div>
          ) : null}

          <div className="stage-canvas">
            {activeRun ? (
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                fitView
                fitViewOptions={{ padding: 0.18 }}
                onNodeClick={(_, node) => setSelectedNodeId(node.id)}
                onPaneClick={() => setSelectedNodeId(null)}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable
                proOptions={{ hideAttribution: true }}
              >
                <Background variant={BackgroundVariant.Lines} gap={48} size={0.8} />
                <Controls showInteractive={false} />
                <MiniMap pannable zoomable />
              </ReactFlow>
            ) : (
              <div className="empty-block stage-empty">
                <h3>No graph mounted</h3>
                <p>The control plane stays read-mostly: pick a run on the left and the workflow will render here.</p>
              </div>
            )}
          </div>

          <section className="timeline-strip">
            <div className="section-head compact">
              <div>
                <p className="kicker">audit trail</p>
                <h3>Event sequence</h3>
              </div>
              <span className="section-meta">{latestEvents.length} events</span>
            </div>

            <div className="timeline-list">
              {latestEvents.length ? (
                latestEvents.map((event: RunEvent) => (
                  <button
                    key={`${event.timestamp}-${event.event}-${event.nodeId ?? "run"}`}
                    className={`timeline-entry ${event.nodeId ? "is-clickable" : ""}`}
                    onClick={() => {
                      if (event.nodeId) {
                        setSelectedNodeId(event.nodeId);
                      }
                    }}
                    type="button"
                  >
                    <div className={`timeline-pulse ${eventTone(event.event)}`} />
                    <div className="timeline-copy">
                      <div className="timeline-top">
                        <strong>{event.event}</strong>
                        <span>{formatTime(event.timestamp)}</span>
                      </div>
                      <p>{event.message ?? "No message recorded."}</p>
                      <div className="timeline-meta">
                        <span>{event.nodeId ?? "run-wide"}</span>
                        <span>{Object.keys(event.payload ?? {}).length} payload keys</span>
                      </div>
                    </div>
                  </button>
                ))
              ) : (
                <div className="empty-block compact-empty">
                  <p>No events indexed for the selected run yet.</p>
                </div>
              )}
            </div>
          </section>
        </main>

        <aside className="panel-surface ops-rail">
          <section className="ops-section">
            <div className="section-head compact">
              <div>
                <p className="kicker">session ledger</p>
                <h2>{selectedNode?.title ?? activeRun?.runId ?? "No run"}</h2>
              </div>
              {activeRun ? <span className={`status-pill ${statusTone(activeRun.status)}`}>{activeRun.status}</span> : null}
            </div>

            {activeRun ? (
              <div className="ledger-grid">
                <LedgerRow label="source session" value={activeRun.sourceSessionKey ?? "not bound"} />
                <LedgerRow label="root session" value={activeRun.rootSessionKey ?? activeRun.driverSessionKey ?? "n/a"} />
                <LedgerRow label="planner / driver" value={activeRun.plannerSessionKey ?? activeRun.driverSessionKey ?? "not persisted"} />
                <LedgerRow label="delivery context" value={deliveryLabel(activeRun.deliveryContext)} />
                <LedgerRow label="cron job" value={activeRun.cronJobId ?? "not scheduled"} />
                <LedgerRow label="last progress update" value={activeRun.lastProgressMessage ?? "none sent"} subtle={formatTime(activeRun.lastProgressMessageAt)} />
              </div>
            ) : (
              <div className="empty-block compact-empty">
                <p>Session routing, delivery, and cron bindings appear here once a run is selected.</p>
              </div>
            )}
          </section>

          <section className="ops-section composer-stack">
            <article className="composer-card">
              <div className="section-head compact">
                <div>
                  <p className="kicker">human override</p>
                  <h3>Send explicit update</h3>
                </div>
              </div>
              <textarea rows={4} value={outboundMessage} onChange={(event) => setOutboundMessage(event.target.value)} />
              <button
                className="primary-btn"
                disabled={actionMutation.isPending || !activeRun?.deliveryContext?.to}
                onClick={() => actionMutation.mutate({ action: "send_message", message: outboundMessage })}
                type="button"
              >
                send message
              </button>
            </article>

            <article className="composer-card">
              <div className="section-head compact">
                <div>
                  <p className="kicker">scheduler override</p>
                  <h3>Patch cron</h3>
                </div>
              </div>
              <textarea rows={6} value={cronPatch} onChange={(event) => setCronPatch(event.target.value)} />
              <button className="secondary-btn" disabled={actionMutation.isPending} onClick={submitCronPatch} type="button">
                apply patch
              </button>
            </article>
          </section>

          <section className="ops-section">
            <div className="section-head compact">
              <div>
                <p className="kicker">node inspector</p>
                <h3>{selectedNode?.id ?? "No node selected"}</h3>
              </div>
              {selectedNode ? <span className={`status-pill ${statusTone(selectedNode.status)}`}>{selectedNode.status}</span> : null}
            </div>

            {selectedNode ? (
              <div className="inspector-stack">
                <div className="badge-row">
                  <span className="inspector-badge">{nodeKindLabel(selectedNode.kind)}</span>
                  <span className="inspector-badge">{selectedNode.outputsMode}</span>
                  <span className="inspector-badge">{selectedNode.needs.length ? `${selectedNode.needs.length} deps` : "entry"}</span>
                </div>

                <div className="inspector-grid">
                  <LedgerRow label="dependencies" value={selectedNode.needs.length ? selectedNode.needs.join(", ") : "entry"} />
                  <LedgerRow label="session binding" value={selectedNode.childSessionKey ?? selectedNode.sessionKey ?? "pending"} />
                  <LedgerRow label="started" value={formatTime(selectedNode.startedAt)} />
                  <LedgerRow label="completed" value={formatTime(selectedNode.completedAt)} />
                </div>

                <div className="inspector-card">
                  <span>artifact paths</span>
                  <ul className="path-list">
                    {selectedNode.artifactPaths.length ? (
                      selectedNode.artifactPaths.map((artifact) => <li key={artifact}>{artifact}</li>)
                    ) : (
                      <li>none declared</li>
                    )}
                  </ul>
                </div>

                <div className="inspector-card">
                  <span>working memory</span>
                  <ul className="path-list">
                    {selectedNode.workingMemory ? (
                      Object.entries(selectedNode.workingMemory)
                        .filter(([, value]) => Boolean(value))
                        .map(([label, value]) => <li key={label}>{`${label}: ${value}`}</li>)
                    ) : (
                      <li>not configured</li>
                    )}
                  </ul>
                </div>

                <div className="header-actions">
                  <button
                    className="secondary-btn"
                    disabled={actionMutation.isPending}
                    onClick={() => actionMutation.mutate({ action: "retry", nodeId: selectedNode.id })}
                    type="button"
                  >
                    retry node
                  </button>
                  <button
                    className="secondary-btn"
                    disabled={actionMutation.isPending}
                    onClick={() => actionMutation.mutate({ action: "skip", nodeId: selectedNode.id })}
                    type="button"
                  >
                    skip node
                  </button>
                  {selectedNode.kind === "approval" ? (
                    <button
                      className="primary-btn"
                      disabled={actionMutation.isPending}
                      onClick={() => actionMutation.mutate({ action: "approve", nodeId: selectedNode.id })}
                      type="button"
                    >
                      approve gate
                    </button>
                  ) : null}
                </div>

                <div className="inspector-card">
                  <span>operator notes</span>
                  <div className="note-list">
                    {(selectedNode.notes.length ? selectedNode.notes : ["No node notes recorded."]).map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="empty-block compact-empty">
                <p>Pick a node from the graph or the timeline to inspect bindings, artifacts, and direct actions.</p>
              </div>
            )}
          </section>

          {actionError ? <div className="error-banner">{actionError}</div> : null}
        </aside>
      </div>
    </div>
  );
}

export default App;
