import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, useTransition } from "react";

import {
  createRun,
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
import { WorkflowGraph } from "./components/WorkflowGraph";
import { currentFocusNode, pickDefaultNodeId, summarizeRun } from "./utils";

type ViewTab = "stages" | "flow";

const tabs: Array<{ id: ViewTab; label: string; description: string }> = [
  { id: "stages", label: "Stages", description: "Follow the workflow in execution order." },
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
  const [isRunsPinned, setIsRunsPinned] = useState(false);
  const [isRunsPeekOpen, setIsRunsPeekOpen] = useState(false);

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

  useEffect(() => {
    if (!activeRunId) {
      return;
    }
    return subscribeRun(activeRunId, (run) => {
      queryClient.setQueryData(["run", activeRunId], run);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
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
  const documentsQuery = useQuery({
    queryKey: ["documents", activeRunId, effectiveSelectedNodeId],
    queryFn: () => fetchNodeDocuments(activeRunId!, effectiveSelectedNodeId!),
    enabled: Boolean(activeRunId && effectiveSelectedNodeId),
  });

  const overview = useMemo(() => summarizeRun(activeRun), [activeRun]);
  const focusNode = useMemo(() => currentFocusNode(activeRun), [activeRun]);
  const isRunsDrawerOpen = isRunsPinned || isRunsPeekOpen;

  function submitCronPatch() {
    try {
      const patch = JSON.parse(cronPatch) as Record<string, unknown>;
      actionMutation.mutate({ action: "patch_cron", patch });
    } catch {
      setActionError("Schedule patch must be valid JSON.");
    }
  }

  return (
    <div className={`dashboard-shell ${isRunsDrawerOpen ? "runs-drawer-visible" : ""}`}>
      <div
        className="runs-edge-zone"
        aria-hidden="true"
        onMouseEnter={() => setIsRunsPeekOpen(true)}
      />
      <button
        type="button"
        className="runs-mobile-toggle"
        onClick={() => setIsRunsPeekOpen((current) => !current)}
      >
        Runs
      </button>
      <button
        type="button"
        aria-label="Close runs drawer"
        className={`runs-overlay-backdrop ${isRunsDrawerOpen ? "visible" : ""}`}
        onClick={() => {
          if (!isRunsPinned) {
            setIsRunsPeekOpen(false);
          }
        }}
      />
      <RunSidebar
        runs={runsQuery.data ?? []}
        isFetching={runsQuery.isFetching}
        isSelecting={isSelecting}
        activeRunId={activeRunId}
        isOpen={isRunsDrawerOpen}
        isPinned={isRunsPinned}
        onPinToggle={() => {
          setIsRunsPinned((current) => {
            const next = !current;
            if (!next) {
              setIsRunsPeekOpen(false);
            } else {
              setIsRunsPeekOpen(true);
            }
            return next;
          });
        }}
        onRequestOpen={() => setIsRunsPeekOpen(true)}
        onRequestClose={() => {
          if (!isRunsPinned) {
            setIsRunsPeekOpen(false);
          }
        }}
        onSelectRun={(id) => {
          startSelection(() => {
            setSelectedRunId(id);
            setSelectedNodeId(null);
            setActiveTab("stages");
          });
          if (!isRunsPinned) {
            setIsRunsPeekOpen(false);
          }
        }}
        onCreateRun={(title, taskText) => createMutation.mutate({ title, taskText })}
        isCreating={createMutation.isPending}
        createError={createMutation.error instanceof Error ? createMutation.error.message : null}
      />

      <main className="workspace-grid">
        <RunOverviewHero activeRun={activeRun} summary={overview} focusNode={focusNode} />

        <section className="surface-panel view-pane">
          <div className="pane-header">
            <div>
              <span className="eyebrow">View</span>
              <h2>{activeTab === "stages" ? "Stages" : "Flow"}</h2>
            </div>
            <div className="tab-strip" role="tablist" aria-label="Run views">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
                  title={tab.description}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="pane-scroll">
            {activeTab === "stages" ? (
              <StageBoard
                run={activeRun}
                selectedNodeId={effectiveSelectedNodeId}
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
      </main>
    </div>
  );
}

export default App;
