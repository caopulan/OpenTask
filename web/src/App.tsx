import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, useTransition } from "react";

import {
  createRun,
  fetchEvents,
  fetchNodeDocuments,
  fetchRun,
  fetchRuns,
  runAction,
  subscribeRun,
} from "./api";
import { InspectorRail } from "./components/InspectorRail";
import { RunOverviewHero } from "./components/RunOverviewHero";
import { RunSidebar } from "./components/RunSidebar";
import { StageBoard } from "./components/StageBoard";
import { TimelineStrip } from "./components/TimelineStrip";
import { WorkflowGraph } from "./components/WorkflowGraph";
import { currentFocusNode, pickDefaultNodeId, summarizeRun } from "./utils";

type ViewTab = "stages" | "activity" | "flow";

const tabs: Array<{ id: ViewTab; label: string; description: string }> = [
  { id: "stages", label: "Stages", description: "Follow the workflow in execution order." },
  { id: "activity", label: "Activity", description: "Inspect the latest events and operator-visible history." },
  { id: "flow", label: "Flow", description: "Open the dependency graph when you need the full map." },
];

function App() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ViewTab>("stages");
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
    if (selectedRunId) {
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
      queryClient.invalidateQueries({ queryKey: ["documents", activeRunId] });
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
        setActiveTab("stages");
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
      queryClient.invalidateQueries({ queryKey: ["documents", run.runId] });
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
    return pickDefaultNodeId(activeRun);
  }, [activeRun, selectedNodeId]);

  const selectedNode = activeRun?.nodes.find((node) => node.id === effectiveSelectedNodeId) ?? null;
  const latestEvents = useMemo(
    () => (eventsQuery.data ? [...eventsQuery.data].sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp)) : []),
    [eventsQuery.data],
  );
  const documentsQuery = useQuery({
    queryKey: ["documents", activeRunId, effectiveSelectedNodeId],
    queryFn: () => fetchNodeDocuments(activeRunId!, effectiveSelectedNodeId!),
    enabled: Boolean(activeRunId && effectiveSelectedNodeId),
  });

  const overview = useMemo(() => summarizeRun(activeRun), [activeRun]);
  const focusNode = useMemo(() => currentFocusNode(activeRun), [activeRun]);

  function submitCronPatch() {
    try {
      const patch = JSON.parse(cronPatch) as Record<string, unknown>;
      actionMutation.mutate({ action: "patch_cron", patch });
    } catch {
      setActionError("Schedule patch must be valid JSON.");
    }
  }

  return (
    <div className="dashboard-shell">
      <RunSidebar
        runs={runsQuery.data ?? []}
        isFetching={runsQuery.isFetching}
        isSelecting={isSelecting}
        activeRunId={activeRunId}
        onSelectRun={(id) => {
          startSelection(() => {
            setSelectedRunId(id);
            setSelectedNodeId(null);
            setActiveTab("stages");
          });
        }}
        onCreateRun={(title, taskText) => createMutation.mutate({ title, taskText })}
        isCreating={createMutation.isPending}
        createError={createMutation.error instanceof Error ? createMutation.error.message : null}
      />

      <main className="dashboard-main">
        <RunOverviewHero activeRun={activeRun} summary={overview} focusNode={focusNode} />

        <section className="surface-panel workspace-panel">
          <div className="workspace-header">
            <div>
              <span className="eyebrow">Views</span>
              <h2>Read the run before you operate it</h2>
            </div>
            <div className="tab-strip" role="tablist" aria-label="Run views">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <span>{tab.label}</span>
                  <small>{tab.description}</small>
                </button>
              ))}
            </div>
          </div>

          <div className="workspace-content">
            {activeTab === "stages" ? (
              <StageBoard
                run={activeRun}
                selectedNodeId={effectiveSelectedNodeId}
                onSelectNode={(id) => setSelectedNodeId(id)}
              />
            ) : null}
            {activeTab === "activity" ? (
              <TimelineStrip
                events={latestEvents}
                onSelectNode={(id) => setSelectedNodeId(id)}
              />
            ) : null}
            {activeTab === "flow" ? (
              <WorkflowGraph
                run={activeRun}
                selectedNodeId={effectiveSelectedNodeId}
                onNodeSelect={(id) => setSelectedNodeId(id)}
              />
            ) : null}
          </div>
        </section>
      </main>

      <InspectorRail
        activeRun={activeRun}
        selectedNode={selectedNode}
        focusNode={focusNode}
        actionMutation={actionMutation}
        outboundMessage={outboundMessage}
        setOutboundMessage={setOutboundMessage}
        cronPatch={cronPatch}
        setCronPatch={setCronPatch}
        submitCronPatch={submitCronPatch}
        actionError={actionError}
        documents={documentsQuery.data ?? []}
        documentsLoading={documentsQuery.isFetching}
      />
    </div>
  );
}

export default App;
