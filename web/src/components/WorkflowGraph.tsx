import { useEffect } from "react";
import { ReactFlow, useNodesState, useEdgesState, Background, Controls } from "@xyflow/react";
import dagre from "dagre";
import type { RunState } from "../types";
import { RunNodeCard } from "./nodes/RunNodeCard";

const nodeTypes = {
  runNode: RunNodeCard,
};

function getLayoutedElements(nodes: any[], edges: any[]) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  // LR = Left to Right layout
  dagreGraph.setGraph({ rankdir: "LR", ranksep: 100, nodesep: 60 });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 280, height: 160 });
  });

  dagre.layout(dagreGraph);

  const newNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 140,
        y: nodeWithPosition.y - 80,
      },
    };
  });

  return { nodes: newNodes, edges };
}

export function WorkflowGraph({
  run,
  selectedNodeId,
  onNodeSelect,
}: {
  run: RunState | undefined;
  selectedNodeId: string | null;
  onNodeSelect: (id: string | null) => void;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<any>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<any>([]);

  useEffect(() => {
    if (!run) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const flowNodes = run.nodes.map((node) => ({
      id: node.id,
      type: "runNode",
      position: { x: 0, y: 0 },
      data: { node, isSelected: selectedNodeId === node.id },
    }));

    const flowEdges = run.nodes.flatMap((node) =>
      node.needs.map((dep) => ({
        id: `e-${dep}-${node.id}`,
        source: dep,
        target: node.id,
        animated: node.status === "running" || node.status === "ready",
        style: { stroke: "var(--border-strong)", strokeWidth: 2 },
      }))
    );

    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(flowNodes, flowEdges);

    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  }, [run, selectedNodeId, setNodes, setEdges]);

  if (!run) {
    return (
      <div className="flex-col items-center justify-center h-full text-muted">
        <h3>No graph mounted</h3>
        <p className="mt-2 text-sm max-w-md text-center">
          The control plane stays read-mostly: pick a run on the left and the workflow map will render here.
        </p>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "100%", background: "var(--bg-base)", borderRadius: "var(--radius-lg)" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onNodeSelect(node.id)}
        onPaneClick={() => onNodeSelect(null)}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="var(--border-strong)" gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
