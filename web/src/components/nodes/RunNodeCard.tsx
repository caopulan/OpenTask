import { Handle, Position } from "@xyflow/react";
import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from "lucide-react";

import type { RunNode } from "../../types";
import { countDeclaredDocuments, nodeDependencyLabel, nodeKindLabel, statusBgTone, statusTone } from "../../utils";

export function RunNodeCard({ data, isConnectable }: { data: { node: RunNode; isSelected: boolean }; isConnectable: boolean }) {
  const node = data.node;
  const isSelected = data.isSelected;
  const statusIcon =
    node.status === "completed" ? (
      <CheckCircle2 size={18} className={statusTone(node.status)} />
    ) : node.status === "failed" ? (
      <AlertCircle size={18} className={statusTone(node.status)} />
    ) : node.status === "running" ? (
      <LoaderCircle size={18} className={`${statusTone(node.status)} spin`} />
    ) : (
      <Clock3 size={18} className={statusTone(node.status)} />
    );

  return (
    <div className={`flow-node ${isSelected ? "selected" : ""}`}>
      <Handle type="target" position={Position.Top} isConnectable={isConnectable} />

      <div className="flow-node-head">
        <span className="eyebrow">{node.id}</span>
        {statusIcon}
      </div>

      <h4>{node.title}</h4>
      <p>{nodeDependencyLabel(node)}</p>

      <div className="flow-node-tags">
        <span>{nodeKindLabel(node.kind)}</span>
        <span>{countDeclaredDocuments(node)} docs</span>
      </div>

      <span className={`status-pill ${statusTone(node.status)} ${statusBgTone(node.status)}`}>{node.status}</span>

      <Handle type="source" position={Position.Bottom} isConnectable={isConnectable} />
    </div>
  );
}
