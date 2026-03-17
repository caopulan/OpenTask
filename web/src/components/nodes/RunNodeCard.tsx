import { Handle, Position } from "@xyflow/react";
import type { RunNode } from "../../types";
import { statusTone, nodeKindLabel, formatTime } from "../../utils";
import { CheckCircle2, Clock, AlertCircle, Loader2 } from "lucide-react";

export function RunNodeCard({ data, isConnectable }: any) {
  const node: RunNode = data.node;
  const isSelected: boolean = data.isSelected;

  const StatusIcon = () => {
    switch (node.status) {
      case "completed":
        return <CheckCircle2 size={16} className={statusTone(node.status)} />;
      case "failed":
        return <AlertCircle size={16} className={statusTone(node.status)} />;
      case "running":
        return <Loader2 size={16} className={`${statusTone(node.status)} is-running-pulse`} style={{ animation: "spin 2s linear infinite" }} />;
      case "waiting":
      case "ready":
        return <Clock size={16} className={statusTone(node.status)} />;
      default:
        return <div className={`status-pill ${statusTone(node.status).replace('status-', 'bg-')}`} style={{ width: '8px', height: '8px', padding: 0, borderRadius: '50%' }} />;
    }
  };

  return (
    <div className={`run-node-custom ${isSelected ? "selected" : ""}`}>
      <Handle type="target" position={Position.Left} isConnectable={isConnectable} className="react-flow__handle react-flow__handle-left" />
      
      <div className="node-header">
        <div className="flex-row items-center gap-2">
          <span className="mono text-xs text-muted">
            {node.id.length > 8 ? `${node.id.substring(0, 8)}...` : node.id}
          </span>
        </div>
        <StatusIcon />
      </div>

      <div className="node-title">{node.title}</div>
      
      <div className="node-meta">
        <span className="bg-surface" style={{ padding: '2px 6px', borderRadius: '4px' }}>
          {nodeKindLabel(node.kind)}
        </span>
        <span className="bg-surface" style={{ padding: '2px 6px', borderRadius: '4px' }}>
          {node.outputsMode}
        </span>
      </div>

      <div className="flex-row justify-between items-center mt-4">
        <div className="flex-col gap-1">
          <span className="kicker">Started</span>
          <span className="mono text-xs max-w-full truncate">{formatTime(node.startedAt).split(',')[1]?.trim() || 'N/A'}</span>
        </div>
        <div className="flex-col gap-1 text-right">
          <span className="kicker">Completed</span>
          <span className="mono text-xs">{formatTime(node.completedAt).split(',')[1]?.trim() || 'N/A'}</span>
        </div>
      </div>

      <Handle type="source" position={Position.Right} isConnectable={isConnectable} className="react-flow__handle react-flow__handle-right" />
    </div>
  );
}
