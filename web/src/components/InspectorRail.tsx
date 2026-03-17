import { CheckCircle2, Pause, Play, RefreshCw, Send, SkipForward } from "lucide-react";
import { useState } from "react";

import type { RunNode, RunNodeDocument, RunState } from "../types";
import {
  countDeclaredDocuments,
  deliveryLabel,
  documentPreviewLabel,
  formatTime,
  nodeDependencyLabel,
  nodeKindLabel,
  sortDocuments,
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
  const [documentSelection, setDocumentSelection] = useState<{ nodeId: string | null; path: string | null }>({
    nodeId: null,
    path: null,
  });
  const subjectNode = selectedNode ?? focusNode;
  const orderedDocuments = sortDocuments(documents);
  const activeDocumentPath = documentSelection.nodeId === subjectNode?.id ? documentSelection.path : null;
  const activeDocument =
    orderedDocuments.find((document) => document.path === activeDocumentPath) ?? orderedDocuments[0] ?? null;

  return (
    <aside className="surface-panel details-pane">
      <div className="pane-header">
        <div>
          <span className="eyebrow">Details</span>
          <h2>{subjectNode?.title ?? activeRun?.title ?? "No selection"}</h2>
        </div>
        {subjectNode ? (
          <span className={`status-pill ${statusTone(subjectNode.status)} ${statusBgTone(subjectNode.status)}`}>
            {subjectNode.status}
          </span>
        ) : null}
      </div>

      <div className="pane-scroll details-scroll">
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

        {subjectNode ? (
          <section className="details-section node-summary-card">
            <div className="section-head">
              <div>
                <span className="eyebrow">Node summary</span>
                <h3>{subjectNode.title}</h3>
              </div>
              <span className="quiet-meta">{countDeclaredDocuments(subjectNode)} docs</span>
            </div>
            <div className="details-meta-grid">
              <div title={`Stage type: ${nodeKindLabel(subjectNode.kind)}`}>
                <span className="eyebrow">Type</span>
                <strong>{nodeKindLabel(subjectNode.kind)}</strong>
              </div>
              <div title={nodeDependencyLabel(subjectNode)}>
                <span className="eyebrow">Dependency</span>
                <strong>{nodeDependencyLabel(subjectNode)}</strong>
              </div>
              <div title="Started time">
                <span className="eyebrow">Started</span>
                <strong>{formatTime(subjectNode.startedAt)}</strong>
              </div>
              <div title="Completed time">
                <span className="eyebrow">Completed</span>
                <strong>{formatTime(subjectNode.completedAt)}</strong>
              </div>
              <div title="Output mode">
                <span className="eyebrow">Mode</span>
                <strong>{subjectNode.outputsMode}</strong>
              </div>
              <div title="Artifact count">
                <span className="eyebrow">Artifacts</span>
                <strong>{subjectNode.artifactPaths.length}</strong>
              </div>
            </div>
          </section>
        ) : (
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
        )}

        {subjectNode ? (
          <section className="details-section">
            <div className="section-head">
              <div>
                <span className="eyebrow">Documents</span>
                <h3>{subjectNode.title}</h3>
              </div>
              <span className="quiet-meta">{orderedDocuments.length} docs</span>
            </div>

            {orderedDocuments.length ? (
              <>
                <div className="doc-chip-row">
                  {orderedDocuments.map((document) => (
                    <button
                      key={document.path}
                      type="button"
                      className={`doc-chip ${activeDocument?.path === document.path ? "active" : ""}`}
                      title={`${document.path} · ${document.format}`}
                      onClick={() => setDocumentSelection({ nodeId: subjectNode.id, path: document.path })}
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
                <p>Progress, plan, findings, reports, and results will show up here when they exist.</p>
              </div>
            )}
          </section>
        ) : null}

        <section className="details-section metadata-grid">
          <article className="metadata-card">
            <span className="eyebrow">Progress</span>
            <strong>{activeRun?.lastProgressMessage ?? "No progress update yet"}</strong>
            <p>{formatTime(activeRun?.lastProgressMessageAt)}</p>
          </article>
          <article className="metadata-card">
            <span className="eyebrow">Delivery</span>
            <strong>{deliveryLabel(activeRun?.deliveryContext)}</strong>
            <p>{activeRun?.workflowId ?? "No workflow selected"}</p>
          </article>
          <article className="metadata-card">
            <span className="eyebrow">Run ID</span>
            <strong>{activeRun?.runId ?? "n/a"}</strong>
            <p>{activeRun?.lastEvent ?? "No event yet"}</p>
          </article>
          <article className="metadata-card">
            <span className="eyebrow">Session</span>
            <strong>{subjectNode?.childSessionKey ?? subjectNode?.sessionKey ?? activeRun?.rootSessionKey ?? "n/a"}</strong>
            <p>Updated {formatTime(activeRun?.updatedAt)}</p>
          </article>
        </section>

        {subjectNode?.artifactPaths.length ? (
          <section className="details-section">
            <span className="eyebrow">Artifact paths</span>
            <div className="path-list">
              {subjectNode.artifactPaths.map((path) => (
                <code key={path}>{path}</code>
              ))}
            </div>
          </section>
        ) : null}

        {selectedNode?.notes.length ? (
          <section className="details-section info-card">
            <span className="eyebrow">Notes</span>
            <strong>{selectedNode.notes[0]}</strong>
            {selectedNode.notes.length > 1 ? <p>{selectedNode.notes.slice(1).join(" · ")}</p> : null}
          </section>
        ) : null}

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

        {actionError ? <div className="error-banner">{actionError}</div> : null}
      </div>
    </aside>
  );
}
