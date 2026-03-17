import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, useTransition } from "react";

import { createRun, fetchEvents, fetchRun, fetchRuns, runAction, subscribeRun } from "./api";
import { RunSidebar } from "./components/RunSidebar";
import { WorkflowGraph } from "./components/WorkflowGraph";
import { InspectorRail } from "./components/InspectorRail";
import { TimelineStrip } from "./components/TimelineStrip";

function App() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [outboundMessage, setOutboundMessage] = useState("OpenTask control-plane ping.");
  const [cronPatch, setCronPatch] = useState('{\n  "enabled": true\n}');
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
    mutationFn: (vars: { title: string; taskText: string }) =>
      createRun({
        title: vars.title,
        taskText: vars.taskText,
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
    <div className="app-layout">
      {/* Sidebar: Registry Ledger */}
      <RunSidebar
        runs={runsQuery.data ?? []}
        isFetching={runsQuery.isFetching}
        isSelecting={isSelecting}
        activeRunId={activeRunId}
        onSelectRun={(id) => {
          startSelection(() => {
            setSelectedRunId(id);
            setSelectedNodeId(null);
          });
        }}
        onCreateRun={(title, taskText) => createMutation.mutate({ title, taskText })}
        isCreating={createMutation.isPending}
        createError={createMutation.error instanceof Error ? createMutation.error.message : null}
      />

      {/* Main Stage: Node Graph Canvas & Timeline */}
      <main className="flex-col gap-4" style={{ overflow: "hidden" }}>
        <div className="glass-panel" style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {/* Subtle Stage Head */}
          <div className="flex-row items-center justify-between" style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-card)" }}>
            <div>
              <span className="kicker">Orchestration Stage</span>
              <h1 style={{ fontSize: "1.25rem", fontWeight: "600", marginTop: "2px" }}>
                {activeRun?.title ?? "Awaiting Control Signal"}
              </h1>
            </div>
            {activeRun && (
              <div className="mono text-xs text-muted flex-row gap-4">
                <span>{activeRun.workflowId}</span>
                <span>source: {activeRun.sourceAgentId ?? "main"}</span>
              </div>
            )}
          </div>
          
          <div style={{ flex: 1, position: "relative" }}>
            <WorkflowGraph
              run={activeRun}
              selectedNodeId={effectiveSelectedNodeId}
              onNodeSelect={(id) => setSelectedNodeId(id)}
            />
          </div>
        </div>

        {/* Timeline Event Sequence Strip */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <TimelineStrip events={latestEvents} onSelectNode={(id) => setSelectedNodeId(id)} />
        </div>
      </main>

      {/* Right Rail: Session Inspector & Overrides */}
      <InspectorRail
        activeRun={activeRun}
        selectedNode={selectedNode}
        actionMutation={actionMutation}
        outboundMessage={outboundMessage}
        setOutboundMessage={setOutboundMessage}
        cronPatch={cronPatch}
        setCronPatch={setCronPatch}
        submitCronPatch={submitCronPatch}
        actionError={actionError}
      />
    </div>
  );
}

export default App;
