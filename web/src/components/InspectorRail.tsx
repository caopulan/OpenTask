import { CheckCircle2, Pause, Play, RefreshCw, Send, SkipForward } from "lucide-react";
import { useState } from "react";

import type { RunNode, RunNodeDocument, RunState } from "../types";
import {
  deliveryLabel,
  documentPreviewLabel,
  formatTime,
  nodeDependencyLabel,
  nodeKindLabel,
  statusBgTone,
  statusTone,
} from "../utils";

export function InspectorRail({
  activeRun,
  selectedNode,
  focusNode,
  actionMutation,
  outboundMessage,
  setOutboundMessage,
  cronPatch,
  setCronPatch,
  submitCronPatch,
  actionError,
  documents,
  documentsLoading,
}: {
  activeRun: RunState | undefined;
  selectedNode: RunNode | null;
  focusNode: RunNode | null;
  actionMutation: {
    isPending: boolean;
    mutate: (payload: { action: string; nodeId?: string; message?: string; patch?: Record<string, unknown> }) => void;
  };
  outboundMessage: string;
  setOutboundMessage: (msg: string) => void;
  cronPatch: string;
  setCronPatch: (patch: string) => void;
  submitCronPatch: () => void;
  actionError: string | null;
  documents: RunNodeDocument[];
  documentsLoading: boolean;
}) {
  const [activeDocumentPath, setActiveDocumentPath] = useState<string | null>(null);
  const activeDocument =
    documents.find((document) => document.path === activeDocumentPath) ?? documents[0] ?? null;

  return (
    <aside className="surface-panel details-rail">
      <div className="details-header">
        <div>
          <span className="eyebrow">Details</span>
          <h2>{selectedNode?.title ?? activeRun?.title ?? "No selection"}</h2>
        </div>
        {selectedNode ? (
          <span className={`status-pill ${statusTone(selectedNode.status)} ${statusBgTone(selectedNode.status)}`}>
            {selectedNode.status}
          </span>
        ) : null}
      </div>

      <div className="details-scroll">
        <section className="details-section">
          <span className="eyebrow">Operator actions</span>
          <div className="action-cluster">
            <button
              type="button"
              className="btn-primary"
              disabled={!activeRun || actionMutation.isPending}
              onClick={() => actionMutation.mutate({ action: activeRun?.status === "paused" ? "resume" : "pause" })}
            >
              {activeRun?.status === "paused" ? <Play size={16} /> : <Pause size={16} />}
              {activeRun?.status === "paused" ? "Resume run" : "Pause run"}
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={!selectedNode || actionMutation.isPending}
              onClick={() => selectedNode && actionMutation.mutate({ action: "retry", nodeId: selectedNode.id })}
            >
              <RefreshCw size={16} />
              Retry
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={!selectedNode || actionMutation.isPending}
              onClick={() => selectedNode && actionMutation.mutate({ action: "skip", nodeId: selectedNode.id })}
            >
              <SkipForward size={16} />
              Skip
            </button>
            {selectedNode?.kind === "approval" ? (
              <button
                type="button"
                className="btn-secondary"
                disabled={actionMutation.isPending}
                onClick={() => actionMutation.mutate({ action: "approve", nodeId: selectedNode.id })}
              >
                <CheckCircle2 size={16} />
                Approve
              </button>
            ) : null}
          </div>
        </section>

        <section className="details-section info-card">
          <span className="eyebrow">Current focus</span>
          {focusNode ? (
            <>
              <strong>{focusNode.title}</strong>
              <p>
                {nodeKindLabel(focusNode.kind)} · {nodeDependencyLabel(focusNode)}
              </p>
            </>
          ) : (
            <>
              <strong>Nothing is waiting on you</strong>
              <p>This run does not have an active stage right now.</p>
            </>
          )}
        </section>

        {selectedNode ? (
          <section className="details-section">
            <div className="section-head">
              <div>
                <span className="eyebrow">Outcome preview</span>
                <h3>{selectedNode.title}</h3>
              </div>
              <span className="quiet-meta">{documents.length} docs</span>
            </div>

            {documents.length ? (
              <>
                <div className="doc-chip-row">
                  {documents.map((document) => (
                    <button
                      key={document.path}
                      type="button"
                      className={`doc-chip ${activeDocument?.path === document.path ? "active" : ""}`}
                      onClick={() => setActiveDocumentPath(document.path)}
                    >
                      {document.label}
                    </button>
                  ))}
                </div>

                {activeDocument ? (
                  <article className="document-card">
                    <div className="document-head">
                      <div>
                        <strong>{documentPreviewLabel(activeDocument)}</strong>
                        <p>{activeDocument.path}</p>
                      </div>
                      <span className="quiet-meta">{activeDocument.format}</span>
                    </div>
                    <pre>{activeDocument.content}</pre>
                  </article>
                ) : null}
              </>
            ) : (
              <div className="document-card empty">
                <strong>{documentsLoading ? "Loading preview…" : "No preview yet"}</strong>
                <p>Available node docs will show up here once the stage has written report or working-memory files.</p>
              </div>
            )}
          </section>
        ) : null}

        <section className="details-section metadata-grid">
          <article className="metadata-card">
            <span className="eyebrow">Delivery</span>
            <strong>{deliveryLabel(activeRun?.deliveryContext)}</strong>
            <p>Last progress: {activeRun?.lastProgressMessage ?? "none sent"}</p>
          </article>
          <article className="metadata-card">
            <span className="eyebrow">Run IDs</span>
            <strong>{activeRun?.runId ?? "n/a"}</strong>
            <p>{activeRun?.workflowId ?? "No workflow selected"}</p>
          </article>
          <article className="metadata-card">
            <span className="eyebrow">Sessions</span>
            <strong>{selectedNode?.childSessionKey ?? selectedNode?.sessionKey ?? activeRun?.rootSessionKey ?? "n/a"}</strong>
            <p>Updated {formatTime(activeRun?.updatedAt)}</p>
          </article>
        </section>

        <details className="advanced-box">
          <summary>Advanced controls</summary>
          <div className="advanced-content">
            <button
              type="button"
              className="btn-secondary full-width"
              disabled={!activeRun || actionMutation.isPending}
              onClick={() => actionMutation.mutate({ action: "tick" })}
            >
              <RefreshCw size={16} />
              Force tick
            </button>

            <label className="field-block">
              <span className="eyebrow">Send message</span>
              <textarea
                className="input-base"
                rows={3}
                value={outboundMessage}
                onChange={(event) => setOutboundMessage(event.target.value)}
                placeholder="Send an operator-visible update"
              />
            </label>
            <button
              type="button"
              className="btn-secondary full-width"
              disabled={actionMutation.isPending || !activeRun?.deliveryContext?.to}
              onClick={() => actionMutation.mutate({ action: "send_message", message: outboundMessage })}
            >
              <Send size={16} />
              Dispatch message
            </button>

            <label className="field-block">
              <span className="eyebrow">Patch schedule</span>
              <textarea
                className="input-base mono"
                rows={4}
                value={cronPatch}
                onChange={(event) => setCronPatch(event.target.value)}
                placeholder='{"enabled": true}'
              />
            </label>
            <button
              type="button"
              className="btn-secondary full-width"
              disabled={actionMutation.isPending}
              onClick={submitCronPatch}
            >
              Apply patch
            </button>
          </div>
        </details>

        {selectedNode?.artifactPaths.length ? (
          <section className="details-section">
            <span className="eyebrow">Artifact paths</span>
            <div className="path-list">
              {selectedNode.artifactPaths.map((path) => (
                <code key={path}>{path}</code>
              ))}
            </div>
          </section>
        ) : null}

        {actionError ? <div className="error-banner">{actionError}</div> : null}
      </div>
    </aside>
  );
}
