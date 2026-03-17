import { Activity, Clock, Box, ShieldAlert, Cpu } from "lucide-react";
import type { RunState } from "../types";
import { formatTime, summarizeRun, statusTone, statusBgTone } from "../utils";

export function RunSidebar({
  runs,
  isFetching,
  isSelecting,
  activeRunId,
  onSelectRun,
  onCreateRun,
  isCreating,
  createError,
}: {
  runs: RunState[];
  isFetching: boolean;
  isSelecting: boolean;
  activeRunId: string | null;
  onSelectRun: (id: string) => void;
  onCreateRun: (title: string, taskText: string) => void;
  isCreating: boolean;
  createError: string | null;
}) {
  return (
    <aside className="glass-panel flex-col" style={{ overflow: "hidden" }}>
      <div style={{ padding: "20px 20px 10px" }}>
        <div className="flex-row items-center justify-between">
          <h2 className="flex-row items-center gap-2" style={{ fontSize: "1.25rem", fontWeight: "600" }}>
            <Activity className="status-running" size={20} /> Registry
          </h2>
          <span className="mono text-xs text-muted pb-1 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
            {isSelecting ? "SWITCHING" : isFetching ? "SYNCING" : "LIVE"}
          </span>
        </div>
        <p className="text-muted text-sm mt-2">Active runs on OpenTask control plane.</p>
      </div>

      <div className="list-container" style={{ flex: 1, padding: "10px 20px" }}>
        {runs.length ? (
          runs.map((run) => {
            const summary = summarizeRun(run);
            const isSelected = activeRunId === run.runId;
            return (
              <button
                key={run.runId}
                className={`card flex-col ${isSelected ? "selected shadow-ambient" : ""}`}
                style={{
                  textAlign: "left",
                  borderColor: isSelected ? "var(--accent-primary)" : "",
                  boxShadow: isSelected ? "0 0 0 1px var(--accent-primary-glow), var(--shadow-card)" : "",
                }}
                onClick={() => onSelectRun(run.runId)}
              >
                <div className="flex-row items-center justify-between mb-4">
                  <strong style={{ fontSize: "1.05rem", lineHeight: "1.2" }}>{run.title}</strong>
                  <span className={`status-pill ${statusTone(run.status)} ${statusBgTone(run.status)}`}>
                    {run.status}
                  </span>
                </div>
                
                <div className="mono text-xs text-muted mb-4">
                  {run.runId.substring(0, 18)}...
                </div>

                <div className="flex-row items-center gap-4 text-xs text-muted mt-2">
                  <div className="flex-row items-center gap-2">
                    <Box size={14} /> {summary.total} nodes
                  </div>
                  <div className="flex-row items-center gap-2">
                    <Cpu size={14} /> {summary.progress}%
                  </div>
                  <div className="flex-row items-center gap-2" style={{ marginLeft: "auto" }}>
                    <Clock size={14} /> {formatTime(run.updatedAt).split(',')[1]?.trim() || formatTime(run.updatedAt)}
                  </div>
                </div>
              </button>
            );
          })
        ) : (
          <div className="flex-col items-center gap-3 p-6 text-center text-muted">
            <ShieldAlert size={32} style={{ opacity: 0.5 }} />
            <p className="text-sm">No indexed runs. Waiting for registry sync.</p>
          </div>
        )}
      </div>

      <div style={{ padding: "20px", borderTop: "1px solid var(--border-subtle)" }}>
        <details className="text-sm">
          <summary className="kicker" style={{ cursor: "pointer", listStyle: "none" }}>
            Operator Hatch (Debug)
          </summary>
          <div className="flex-col gap-3 mt-4">
            <button
              className="btn-secondary"
              style={{ width: "100%" }}
              disabled={isCreating}
              onClick={() => onCreateRun("Debug run", "Inspect the repo and write a short report.")}
            >
              {isCreating ? "Creating..." : "Create default debug run"}
            </button>
            {createError && <p className="text-xs status-failed">{createError}</p>}
          </div>
        </details>
      </div>
    </aside>
  );
}
