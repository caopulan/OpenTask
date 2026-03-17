import type { RunState, RunNode } from "../types";
import { formatTime, deliveryLabel, statusTone, statusBgTone, nodeKindLabel } from "../utils";
import { Play, Pause, RefreshCw, CheckCircle, SkipForward, ArrowRight } from "lucide-react";

export function InspectorRail({
  activeRun,
  selectedNode,
  actionMutation,
  outboundMessage,
  setOutboundMessage,
  cronPatch,
  setCronPatch,
  submitCronPatch,
  actionError,
}: {
  activeRun: RunState | undefined;
  selectedNode: RunNode | null;
  actionMutation: any;
  outboundMessage: string;
  setOutboundMessage: (msg: string) => void;
  cronPatch: string;
  setCronPatch: (patch: string) => void;
  submitCronPatch: () => void;
  actionError: string | null;
}) {
  return (
    <aside className="glass-panel flex-col" style={{ overflow: "hidden", padding: "16px", paddingRight: "4px" }}>
      <div className="list-container" style={{ flex: 1, paddingRight: "12px" }}>
        {/* Run Controls & Details */}
        <section className="mb-4">
          <div className="flex-row items-center justify-between mb-4">
            <div>
              <span className="kicker">Session Ledger</span>
              <h2 className="text-sm font-semibold truncate max-w-[200px]" style={{ fontSize: "1.1rem" }}>
                {selectedNode?.title ?? activeRun?.runId ?? "No run"}
              </h2>
            </div>
          </div>

          <div className="flex-row gap-2 mb-4">
            <button
              className="btn-primary"
              disabled={!activeRun || actionMutation.isPending}
              onClick={() => actionMutation.mutate({ action: activeRun?.status === "paused" ? "resume" : "pause" })}
            >
              {activeRun?.status === "paused" ? <Play size={16} /> : <Pause size={16} />}
              {activeRun?.status === "paused" ? "Resume" : "Pause"}
            </button>
            <button
              className="btn-secondary"
              disabled={!activeRun || actionMutation.isPending}
              onClick={() => actionMutation.mutate({ action: "tick" })}
            >
              <RefreshCw size={16} /> Force Tick
            </button>
          </div>

          <div className="card flex-col gap-3">
            <div className="flex-col gap-1">
              <span className="kicker">Root Session</span>
              <span className="mono text-sm">{activeRun?.rootSessionKey ?? activeRun?.driverSessionKey ?? "n/a"}</span>
            </div>
            <div className="flex-col gap-1">
              <span className="kicker">Delivery Target</span>
              <span className="mono text-sm">{deliveryLabel(activeRun?.deliveryContext)}</span>
            </div>
            <div className="flex-col gap-1">
              <span className="kicker">Last Progress</span>
              <span className="text-sm">{activeRun?.lastProgressMessage ?? "none sent"}</span>
              <span className="mono text-xs text-muted">{formatTime(activeRun?.lastProgressMessageAt)}</span>
            </div>
          </div>
        </section>

        {/* Node Inspector */}
        {selectedNode && (
          <section className="mt-4 mb-4">
            <div className="flex-row items-center justify-between mb-2">
              <span className="kicker">Node Inspector</span>
              <span className={`status-pill ${statusTone(selectedNode.status)} ${statusBgTone(selectedNode.status)}`}>
                {selectedNode.status}
              </span>
            </div>

            <div className="card flex-col gap-4">
              <div className="flex-row items-center gap-2 flex-wrap pb-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                <span className="bg-surface mono text-xs px-2 py-1 rounded">{nodeKindLabel(selectedNode.kind)}</span>
                <span className="bg-surface mono text-xs px-2 py-1 rounded">{selectedNode.outputsMode}</span>
                <span className="bg-surface mono text-xs px-2 py-1 rounded">{selectedNode.needs.length ? `${selectedNode.needs.length} deps` : "entry"}</span>
              </div>

              <div className="flex-col gap-3">
                <div className="flex-col gap-1">
                  <span className="kicker">Session Binding</span>
                  <span className="mono text-sm text-secondary">{selectedNode.childSessionKey ?? selectedNode.sessionKey ?? "pending"}</span>
                </div>
                <div className="flex-col gap-1">
                  <span className="kicker">Artifact Paths</span>
                  {selectedNode.artifactPaths.length ? (
                    <ul className="pl-4 text-sm mono text-secondary m-0">
                      {selectedNode.artifactPaths.map(path => <li key={path}>{path}</li>)}
                    </ul>
                  ) : <span className="mono text-sm text-muted">none declared</span>}
                </div>
              </div>

              {/* Node actions */}
              <div className="flex-col gap-2 mt-2 pt-4" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <div className="flex-row gap-2 flex-wrap">
                  <button className="btn-secondary" style={{ flex: 1, padding: "8px" }} disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ action: "retry", nodeId: selectedNode.id })}>
                    <RefreshCw size={14} /> Retry
                  </button>
                  <button className="btn-secondary" style={{ flex: 1, padding: "8px" }} disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ action: "skip", nodeId: selectedNode.id })}>
                    <SkipForward size={14} /> Skip
                  </button>
                </div>
                {selectedNode.kind === "approval" && (
                  <button className="btn-primary" style={{ width: "100%", padding: "8px" }} disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ action: "approve", nodeId: selectedNode.id })}>
                    <CheckCircle size={14} /> Approve Gate
                  </button>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Override Composers */}
        <section className="mt-4 flex-col gap-4">
          <div className="card flex-col gap-2">
            <span className="kicker">Manual Override</span>
            <textarea 
              className="input-base" 
              rows={3} 
              value={outboundMessage} 
              onChange={(e) => setOutboundMessage(e.target.value)} 
              placeholder="Send instruction..."
            />
            <button 
              className="btn-primary mt-2" 
              disabled={actionMutation.isPending || !activeRun?.deliveryContext?.to}
              onClick={() => actionMutation.mutate({ action: "send_message", message: outboundMessage })}
            >
              <ArrowRight size={14} /> Dispatch
            </button>
          </div>

          <div className="card flex-col gap-2">
            <span className="kicker">Scheduler Override</span>
            <textarea 
              className="input-base mono text-xs" 
              rows={4} 
              value={cronPatch} 
              onChange={(e) => setCronPatch(e.target.value)} 
              placeholder="JSON patch..."
            />
            <button 
              className="btn-secondary mt-2" 
              disabled={actionMutation.isPending}
              onClick={submitCronPatch}
            >
              Apply Patch
            </button>
          </div>
        </section>

        {actionError && (
          <div className="mt-4 p-3 bg-failed text-failed rounded text-sm mono">
            {actionError}
          </div>
        )}
      </div>
    </aside>
  );
}
