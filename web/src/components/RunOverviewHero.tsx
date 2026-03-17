import type { RunNode, RunState } from "../types";
import { formatTime, nodeDependencyLabel, nodeKindLabel, statusBgTone, statusTone } from "../utils";

export function RunOverviewHero({
  activeRun,
  summary,
  focusNode,
}: {
  activeRun: RunState | undefined;
  summary: {
    total: number;
    completed: number;
    running: number;
    actionable: number;
    blocked: number;
    progress: number;
  };
  focusNode: RunNode | null;
}) {
  if (!activeRun) {
    return (
      <section className="surface-panel overview-hero empty-state">
        <span className="eyebrow">Overview</span>
        <h1>Select a run</h1>
        <p>Choose a run from the left rail to see progress, stages, activity, and operator controls.</p>
      </section>
    );
  }

  return (
    <section className="surface-panel overview-hero">
      <div className="overview-header">
        <div className="overview-copy">
          <span className="eyebrow">Overview</span>
          <div className="title-row">
            <h1>{activeRun.title}</h1>
            <span className={`status-pill ${statusTone(activeRun.status)} ${statusBgTone(activeRun.status)}`}>
              {activeRun.status}
            </span>
          </div>
          <p>
            Workflow <strong>{activeRun.workflowId}</strong>
            {" · "}
            Last event <strong>{activeRun.lastEvent ?? "n/a"}</strong>
          </p>
        </div>
        <div className="overview-meta">
          <div>
            <span className="eyebrow">Last update</span>
            <strong>{formatTime(activeRun.updatedAt)}</strong>
          </div>
          <div>
            <span className="eyebrow">Created</span>
            <strong>{formatTime(activeRun.createdAt)}</strong>
          </div>
        </div>
      </div>

      <div className="progress-block">
        <div className="progress-copy">
          <div>
            <span className="eyebrow">Progress</span>
            <strong>{summary.progress}% complete</strong>
          </div>
          <span>
            {summary.completed}/{summary.total} stages finished
          </span>
        </div>
        <div className="progress-track" aria-hidden="true">
          <div className="progress-fill" style={{ width: `${summary.progress}%` }} />
        </div>
      </div>

      <div className="metric-grid">
        <article className="metric-card">
          <span className="eyebrow">Completed</span>
          <strong>{summary.completed}</strong>
          <span>Finished or terminal stages</span>
        </article>
        <article className="metric-card">
          <span className="eyebrow">Active</span>
          <strong>{summary.actionable}</strong>
          <span>Running now or ready to go</span>
        </article>
        <article className="metric-card">
          <span className="eyebrow">Blocked</span>
          <strong>{summary.blocked}</strong>
          <span>Waiting on deps, manual action, or files</span>
        </article>
        <article className="metric-card focus-card">
          <span className="eyebrow">Current focus</span>
          {focusNode ? (
            <>
              <strong>{focusNode.title}</strong>
              <span>
                {nodeKindLabel(focusNode.kind)} · {nodeDependencyLabel(focusNode)}
              </span>
            </>
          ) : (
            <>
              <strong>Run complete</strong>
              <span>No stage needs attention right now.</span>
            </>
          )}
        </article>
      </div>
    </section>
  );
}
