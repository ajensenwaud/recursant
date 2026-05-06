import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { meshVisualiser } from '../api/client';
import useSocket from '../hooks/useSocket';
import useMeshGraph from '../hooks/useMeshGraph';
import MeshGraph from '../components/MeshGraph';
import AgentDetailPopup from '../components/AgentDetailPopup';
import EdgeDetailPopup from '../components/EdgeDetailPopup';
import ToolDetailPopup from '../components/ToolDetailPopup';
import ToolEdgeDetailPopup from '../components/ToolEdgeDetailPopup';
import EventLog from '../components/EventLog';

export default function MeshVisualiser() {
  const { nodes, edges, eventLog, activeEdges, handleEvent, seedFromRest } = useMeshGraph();
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [popupPos, setPopupPos] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [edgePopupPos, setEdgePopupPos] = useState(null);
  const [selectedTool, setSelectedTool] = useState(null);
  const [toolPopupPos, setToolPopupPos] = useState(null);
  const [selectedToolEdge, setSelectedToolEdge] = useState(null);
  const [toolEdgePopupPos, setToolEdgePopupPos] = useState(null);

  // Load initial state from REST
  const { data: regData, isLoading: regLoading } = useQuery({
    queryKey: ['mesh-vis-registrations'],
    queryFn: () => meshVisualiser.registrations(),
  });

  const { data: auditData, isLoading: auditLoading } = useQuery({
    queryKey: ['mesh-vis-audit'],
    queryFn: () => meshVisualiser.audit({ per_page: 200 }),
  });

  const { data: policyData } = useQuery({
    queryKey: ['mesh-vis-policies'],
    queryFn: () => meshVisualiser.policies(),
  });

  const { data: toolsData, isLoading: toolsLoading } = useQuery({
    queryKey: ['mesh-vis-tools'],
    queryFn: () => meshVisualiser.toolsWithAssignments(),
  });

  // Seed graph once REST data is ready
  useEffect(() => {
    if (regData && auditData) {
      seedFromRest(
        regData.registrations || [],
        auditData.records || [],
        toolsData?.tools || [],
      );
    }
  }, [regData, auditData, toolsData, seedFromRest]);

  // Connect WebSocket for live updates
  useSocket('/mesh', handleEvent);

  const closeAllPopups = useCallback(() => {
    setSelectedAgent(null);
    setPopupPos(null);
    setSelectedEdge(null);
    setEdgePopupPos(null);
    setSelectedTool(null);
    setToolPopupPos(null);
    setSelectedToolEdge(null);
    setToolEdgePopupPos(null);
  }, []);

  const onNodeClick = useCallback((nodeData) => {
    closeAllPopups();
    if (nodeData.nodeType === 'tool') {
      setSelectedTool(nodeData);
      setToolPopupPos({ x: 200, y: 100 });
    } else {
      setSelectedAgent(nodeData);
      setPopupPos({ x: 200, y: 100 });
    }
  }, [closeAllPopups]);

  const onClosePopup = useCallback(() => {
    setSelectedAgent(null);
    setPopupPos(null);
  }, []);

  const onCloseToolPopup = useCallback(() => {
    setSelectedTool(null);
    setToolPopupPos(null);
  }, []);

  const onCloseToolEdgePopup = useCallback(() => {
    setSelectedToolEdge(null);
    setToolEdgePopupPos(null);
  }, []);

  const onEdgeClick = useCallback((edgeData, event) => {
    closeAllPopups();
    if (edgeData.edgeType === 'tool-assignment') {
      setSelectedToolEdge(edgeData);
      setToolEdgePopupPos({ x: event.clientX, y: event.clientY });
    } else {
      setSelectedEdge(edgeData);
      setEdgePopupPos({ x: event.clientX, y: event.clientY });
    }
  }, [closeAllPopups]);

  const onCloseEdgePopup = useCallback(() => {
    setSelectedEdge(null);
    setEdgePopupPos(null);
  }, []);

  const isLoading = regLoading || auditLoading || toolsLoading;
  const policies = policyData?.policies || [];

  // Compute counts — separate agents from tool nodes
  const agentCount = Array.from(nodes.values()).filter(n => n.nodeType !== 'tool').length;
  const toolCount = Array.from(nodes.values()).filter(n => n.nodeType === 'tool').length;
  const a2aEdgeCount = Array.from(edges.values()).filter(e => e.edgeType !== 'tool-assignment').length;

  return (
    <div className="-m-6 h-[calc(100vh-6rem)] flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white">
        <h1 className="text-lg font-bold text-gray-900">Mesh Visualiser</h1>
        <div className="flex items-center gap-4 text-sm text-gray-500">
          <span>{agentCount} agents</span>
          <span>{toolCount} tools</span>
          <span>{a2aEdgeCount} connections</span>
          <div className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-teal-500" />
            <span>Active</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
            <span>Blocked</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-sm bg-amber-500" />
            <span>Tool</span>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center flex-1">
          <div className="spinner" />
        </div>
      ) : (
        <div className="flex flex-1 min-h-0">
          {/* Graph canvas */}
          <div className="flex-1 min-w-0 relative">
            <MeshGraph
              nodes={nodes}
              edges={edges}
              activeEdges={activeEdges}
              onNodeClick={onNodeClick}
              onEdgeClick={onEdgeClick}
            />
          </div>

          {/* Event log sidebar */}
          <EventLog events={eventLog} />
        </div>
      )}

      {/* Agent detail popup */}
      <AgentDetailPopup
        agent={selectedAgent}
        position={popupPos}
        onClose={onClosePopup}
      />

      {/* Edge detail popup */}
      <EdgeDetailPopup
        edge={selectedEdge}
        position={edgePopupPos}
        policies={policies}
        onClose={onCloseEdgePopup}
      />

      {/* Tool detail popup */}
      <ToolDetailPopup
        tool={selectedTool}
        position={toolPopupPos}
        onClose={onCloseToolPopup}
      />

      {/* Tool edge detail popup */}
      <ToolEdgeDetailPopup
        edge={selectedToolEdge}
        position={toolEdgePopupPos}
        onClose={onCloseToolEdgePopup}
      />
    </div>
  );
}
