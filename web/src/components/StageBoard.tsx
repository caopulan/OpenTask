import type { RunState } from "../types";
import {
  countDeclaredDocuments,
  formatTime,
  nodeDependencyLabel,
  nodeKindLabel,
  statusBgTone,
  statusTone,
} from "../utils";

export function StageBoard({
  run,
  selectedNodeId,
  onSelectNode,
}: {
  run: RunState | undefined;
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
}) {
  if (!run) {
    return (
      <div className="empty-state">
        <h3>No stages yet</h3>
        <p>When a run is selected, the workflow will appear here in execution order.</p>
      </div>
    );
  }

  return (
    <div className="stage-board">
      {run.nodes.map((node, index) => {
        const isSelected = selectedNodeId === node.id;
        return (
          <button
            key={node.id}
            type="button"
            className={`stage-card ${isSelected ? "selected" : ""}`}
            onClick={() => onSelectNode(node.id)}
          >
            <div className="stage-index">
              <span>{String(index + 1).padStart(2, "0")}</span>
            </div>
            <div className="stage-content">
              <div className="stage-header">
                <div>
                  <div className="stage-title-row">
                    <h3>{node.title}</h3>
                    <span className={`status-pill ${statusTone(node.status)} ${statusBgTone(node.status)}`}>
                      {node.status}
                    </span>
                  </div>
                  <p>{nodeDependencyLabel(node)}</p>
                </div>
                <div className="stage-badges">
                  <span>{nodeKindLabel(node.kind)}</span>
                  <span>{countDeclaredDocuments(node)} docs</span>
                  <span>{node.artifactPaths.length} outputs</span>
                </div>
              </div>

              <div className="stage-meta-grid">
                <div>
                  <span className="eyebrow">Started</span>
                  <strong>{formatTime(node.startedAt)}</strong>
                </div>
                <div>
                  <span className="eyebrow">Completed</span>
                  <strong>{formatTime(node.completedAt)}</strong>
                </div>
                <div>
                  <span className="eyebrow">Output mode</span>
                  <strong>{node.outputsMode}</strong>
                </div>
              </div>

              <div className="stage-foot">
                <p>{node.notes[0] ?? "Open the details rail to inspect artifacts, notes, and operator actions."}</p>
                <span className="stage-link">Open details</span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
