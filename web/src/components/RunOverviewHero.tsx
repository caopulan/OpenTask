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
        <p>Choose a run from the left rail to see progress, stages, flow, and operator controls.</p>
      </section>
    );
  }

  return (
    <section className="surface-panel overview-hero">
      <div className="overview-topline">
        <span className="eyebrow">Overview</span>
        <span className={`status-pill ${statusTone(activeRun.status)} ${statusBgTone(activeRun.status)}`}>
          {activeRun.status}
        </span>
      </div>

      <h1>{activeRun.title}</h1>

      <div className="overview-meta-row">
        <div className="overview-time" title={`Last updated ${formatTime(activeRun.updatedAt)}`}>
          <span className="eyebrow">Last update</span>
          <strong>{formatTime(activeRun.updatedAt)}</strong>
        </div>
        <div className="overview-time" title={`Created ${formatTime(activeRun.createdAt)}`}>
          <span className="eyebrow">Created</span>
          <strong>{formatTime(activeRun.createdAt)}</strong>
        </div>
      </div>

      <p className="overview-context">
        Workflow <strong>{activeRun.workflowId}</strong>
        {" · "}
        Last event <strong>{activeRun.lastEvent ?? "n/a"}</strong>
      </p>

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

      <div className="overview-stats">
        <article
          className="metric-card focus-card"
          title={
            focusNode
              ? `${focusNode.title} · ${nodeKindLabel(focusNode.kind)} · ${nodeDependencyLabel(focusNode)}`
              : "No stage needs attention right now."
          }
        >
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
        <article
          className="metric-chip completed"
          title="Finished or terminal stages"
        >
          <span>Completed</span>
          <strong>{summary.completed}</strong>
        </article>
        <article
          className="metric-chip active"
          title="Running now or ready to go"
        >
          <span>Active</span>
          <strong>{summary.actionable}</strong>
        </article>
        <article
          className="metric-chip blocked"
          title="Waiting on dependencies, manual action, or files"
        >
          <span>Blocked</span>
          <strong>{summary.blocked}</strong>
        </article>
      </div>
    </section>
  );
}
