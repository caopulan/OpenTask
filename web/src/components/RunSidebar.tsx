import { Activity, Plus, Sparkles } from "lucide-react";

import type { RunState } from "../types";
import { currentFocusLabel, formatTime, statusBgTone, statusTone, summarizeRun } from "../utils";

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
    <aside className="surface-panel runs-rail">
      <div className="rail-header">
        <div>
          <span className="eyebrow">Runs</span>
          <h2>OpenTask runs</h2>
        </div>
        <span className="sync-pill">{isSelecting ? "switching" : isFetching ? "syncing" : "live"}</span>
      </div>

      <div className="rail-list">
        {runs.length ? (
          runs.map((run) => {
            const summary = summarizeRun(run);
            const isActive = activeRunId === run.runId;
            return (
              <button
                key={run.runId}
                type="button"
                className={`run-card ${isActive ? "active" : ""}`}
                onClick={() => onSelectRun(run.runId)}
              >
                <div className="run-card-head">
                  <div>
                    <h3>{run.title}</h3>
                    <p>{currentFocusLabel(run)}</p>
                  </div>
                  <span className={`status-pill ${statusTone(run.status)} ${statusBgTone(run.status)}`}>{run.status}</span>
                </div>

                <div className="mini-progress">
                  <div className="mini-progress-bar">
                    <div style={{ width: `${summary.progress}%` }} />
                  </div>
                  <span>{summary.progress}%</span>
                </div>

                <div className="run-card-meta">
                  <span>
                    <Activity size={14} />
                    {summary.completed}/{summary.total} done
                  </span>
                  <span>Updated {formatTime(run.updatedAt)}</span>
                </div>
              </button>
            );
          })
        ) : (
          <div className="empty-state compact">
            <h3>No runs available</h3>
            <p>Waiting for the control plane to index a runtime directory.</p>
          </div>
        )}
      </div>

      <details className="advanced-box" open={false}>
        <summary>
          <Sparkles size={14} />
          Advanced
        </summary>
        <div className="advanced-content">
          <button
            type="button"
            className="btn-secondary full-width"
            disabled={isCreating}
            onClick={() => onCreateRun("Debug run", "Inspect the repo and write a short report.")}
          >
            <Plus size={16} />
            {isCreating ? "Creating…" : "Create debug run"}
          </button>
          {createError ? <p className="error-text">{createError}</p> : null}
        </div>
      </details>
    </aside>
  );
}
