import { useEffect } from "react";
import { Background, Controls, ReactFlow, useEdgesState, useNodesState, type Edge, type Node } from "@xyflow/react";
import dagre from "dagre";

import type { RunState } from "../types";
import { RunNodeCard } from "./nodes/RunNodeCard";

type FlowNodeData = {
  node: RunState["nodes"][number];
  isSelected: boolean;
};

const nodeTypes = {
  runNode: RunNodeCard,
};

function getLayoutedElements(nodes: Array<Node<FlowNodeData>>, edges: Array<Edge>) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: "TB", ranksep: 72, nodesep: 48, marginx: 24, marginy: 24 });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source as string, edge.target as string);
  });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id as string, { width: 280, height: 180 });
  });

  dagre.layout(dagreGraph);

  return {
    nodes: nodes.map((node) => {
      const layout = dagreGraph.node(node.id as string);
      return {
        ...node,
        position: {
          x: layout.x - 140,
          y: layout.y - 90,
        },
      };
    }),
    edges,
  };
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
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<FlowNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

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
        style: { stroke: "var(--line-strong)", strokeWidth: 1.6 },
      })),
    );

    const layouted = getLayoutedElements(flowNodes, flowEdges);
    setNodes(layouted.nodes);
    setEdges(layouted.edges);
  }, [run, selectedNodeId, setEdges, setNodes]);

  if (!run) {
    return (
      <div className="empty-state">
        <h3>No flow selected</h3>
        <p>Select a run first. The dependency graph stays available as a secondary diagnostic view.</p>
      </div>
    );
  }

  return (
    <div className="flow-panel">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onNodeSelect(node.id)}
        onPaneClick={() => onNodeSelect(null)}
        fitView
        fitViewOptions={{ padding: 0.16, minZoom: 0.65, maxZoom: 1.1 }}
        minZoom={0.4}
        maxZoom={1.4}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="var(--line-soft)" gap={24} size={1} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
