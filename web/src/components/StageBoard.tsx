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
            title={`${node.title}\n${nodeDependencyLabel(node)}\n${node.notes[0] ?? "Select to inspect details."}`}
            onClick={() => onSelectNode(node.id)}
          >
            <div className="stage-index">
              <span>{String(index + 1).padStart(2, "0")}</span>
            </div>
            <div className="stage-content">
              <div className="stage-header">
                <div className="stage-title-stack">
                  <div className="stage-title-row">
                    <h3>{node.title}</h3>
                    <span className={`status-pill ${statusTone(node.status)} ${statusBgTone(node.status)}`}>
                      {node.status}
                    </span>
                  </div>
                  <span className="stage-subtle">{nodeDependencyLabel(node)}</span>
                </div>
                <div className="stage-badges">
                  <span title={`Stage type: ${nodeKindLabel(node.kind)}`}>{nodeKindLabel(node.kind)}</span>
                  <span title="Declared document count">{countDeclaredDocuments(node)} docs</span>
                  <span title="Artifact count">{node.artifactPaths.length} outputs</span>
                </div>
              </div>

              <div className="stage-meta-row">
                <span title="Started time">Started {formatTime(node.startedAt)}</span>
                <span title="Completed time">Completed {formatTime(node.completedAt)}</span>
                <span title="Output mode">{node.outputsMode}</span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
