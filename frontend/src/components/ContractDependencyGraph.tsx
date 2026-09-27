import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  MiniMap,
  Panel,
  Handle,
  Position,
  MarkerType,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import type {
  ObligationOut,
  EdgeOut,
  Relation,
  RiskBand,
  ObligationStatus,
  Modality,
} from '../types/api';
import { usePatchEdge } from '../hooks/useObligations';

// ──────────────────────────────────────────────────────────────────────────────
// Helpers & Badge Utilities
// ──────────────────────────────────────────────────────────────────────────────

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

function getRiskBadgeClass(band: RiskBand): string {
  switch (band) {
    case 'critical':
      return 'bg-rose-950/80 text-rose-300 border-rose-800';
    case 'high':
      return 'bg-amber-950/80 text-amber-300 border-amber-800';
    case 'medium':
      return 'bg-yellow-950/80 text-yellow-300 border-yellow-800';
    case 'low':
      return 'bg-emerald-950/80 text-emerald-300 border-emerald-800';
    default:
      return 'bg-slate-800 text-slate-300 border-slate-700';
  }
}

function getStatusBadgeClass(status: ObligationStatus): string {
  switch (status) {
    case 'done':
      return 'bg-emerald-950/70 text-emerald-300 border-emerald-800';
    case 'blocked':
      return 'bg-rose-950/70 text-rose-300 border-rose-800';
    case 'waived':
      return 'bg-slate-800 text-slate-400 border-slate-700';
    case 'open':
    default:
      return 'bg-blue-950/70 text-blue-300 border-blue-800';
  }
}

function getModalityBadgeClass(modality: Modality): string {
  switch (modality) {
    case 'must':
      return 'bg-sky-950/70 text-sky-300 border-sky-800';
    case 'must_not':
      return 'bg-rose-950/70 text-rose-300 border-rose-800';
    case 'may':
    default:
      return 'bg-slate-800 text-slate-400 border-slate-700';
  }
}

function formatRelation(relation: Relation): string {
  switch (relation) {
    case 'must_precede':
      return 'must precede';
    case 'condition_for':
      return 'condition for';
    case 'depends_on':
      return 'depends on';
    case 'may_trigger':
      return 'may trigger';
    default:
      return relation;
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Custom Node Component
// ──────────────────────────────────────────────────────────────────────────────

interface ObligationNodeData {
  obligation: ObligationOut;
  onSelect?: (ob: ObligationOut) => void;
  onReview?: (ob: ObligationOut) => void;
  [key: string]: unknown;
}

const NODE_WIDTH = 280;
const NODE_HEIGHT = 135;

export const ObligationCustomNode: React.FC<NodeProps<Node<ObligationNodeData>>> = ({
  data,
}) => {
  const ob = data.obligation;

  const handleSelect = (e: React.MouseEvent) => {
    e.stopPropagation();
    data.onSelect?.(ob);
  };

  const handleReview = (e: React.MouseEvent) => {
    e.stopPropagation();
    data.onReview?.(ob);
  };

  return (
    <div
      onClick={handleSelect}
      className="w-[280px] rounded-xl border border-slate-200 bg-white p-3.5 shadow-md hover:border-indigo-300 transition-all cursor-pointer group text-left relative"
    >
      {/* Target handle for incoming edges */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2.5 !h-2.5 !bg-indigo-400 !border-2 !border-slate-900"
      />

      {/* Header: ID + Category + Modality */}
      <div className="flex items-center justify-between gap-1.5 mb-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="font-mono text-[10px] font-semibold text-slate-400 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">
            {ob.id}
          </span>
          <span className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 truncate">
            {ob.category}
          </span>
        </div>
        <span
          className={`font-mono text-[9px] uppercase px-1.5 py-0.5 rounded border ${getModalityBadgeClass(
            ob.modality
          )}`}
        >
          {ob.modality}
        </span>
      </div>

      {/* Actor & Action */}
      <div className="space-y-0.5 mb-2">
        <p className="text-xs font-semibold text-white truncate">
          {ob.actor}
          {ob.counterparty && (
            <span className="text-[11px] font-normal text-slate-400">
              {' '}&rarr; {ob.counterparty}
            </span>
          )}
        </p>
        <p className="text-[11px] text-slate-300 leading-snug line-clamp-2">
          {ob.action} {ob.object ? ob.object : ''}
        </p>
      </div>

      {/* Footer: Due date + Risk + Status */}
      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between gap-1 text-[10px]">
        {/* Due date */}
        <span className="font-mono text-slate-400 truncate">
          {ob.due_date ? formatDate(ob.due_date) : ob.resolution_status === 'unresolved_trigger' ? 'Needs trigger' : 'No date'}
        </span>

        {/* Badges */}
        <div className="flex items-center gap-1 shrink-0">
          {ob.risk?.band && (
            <span
              className={`font-mono px-1.5 py-0.2 rounded border text-[9px] font-medium ${getRiskBadgeClass(
                ob.risk.band
              )}`}
            >
              {ob.risk.band}
            </span>
          )}
          <span
            className={`font-mono px-1.5 py-0.2 rounded border text-[9px] capitalize ${getStatusBadgeClass(
              ob.status
            )}`}
          >
            {ob.status}
          </span>
        </div>
      </div>

      {/* Hover action overlay */}
      <div className="absolute top-2 right-2 hidden group-hover:flex items-center gap-1 z-20 bg-slate-900/90 rounded p-0.5 border border-slate-700 shadow-sm">
        <button
          type="button"
          onClick={handleSelect}
          title="Inspect Source"
          className="px-1.5 py-0.5 text-[9px] font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 rounded"
        >
          Inspect
        </button>
        {data.onReview && (
          <button
            type="button"
            onClick={handleReview}
            title="Review Obligation"
            className="px-1.5 py-0.5 text-[9px] font-medium bg-indigo-900/80 hover:bg-indigo-800 text-indigo-200 rounded"
          >
            Review
          </button>
        )}
      </div>

      {/* Source handle for outgoing edges */}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-2.5 !h-2.5 !bg-sky-400 !border-2 !border-slate-900"
      />
    </div>
  );
};

// ──────────────────────────────────────────────────────────────────────────────
// Dagre Auto-layout Function
// ──────────────────────────────────────────────────────────────────────────────

function layoutGraph(
  nodes: Node<ObligationNodeData>[],
  edges: Edge[],
  direction: 'LR' | 'TB' = 'LR'
): { nodes: Node<ObligationNodeData>[]; edges: Edge[] } {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: 45,
    ranksep: 90,
    marginx: 25,
    marginy: 25,
  });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      targetPosition: direction === 'LR' ? Position.Left : Position.Top,
      sourcePosition: direction === 'LR' ? Position.Right : Position.Bottom,
      position: {
        x: nodeWithPosition ? nodeWithPosition.x - NODE_WIDTH / 2 : 0,
        y: nodeWithPosition ? nodeWithPosition.y - NODE_HEIGHT / 2 : 0,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

// ──────────────────────────────────────────────────────────────────────────────
// Main ContractDependencyGraph Component
// ──────────────────────────────────────────────────────────────────────────────

export interface ContractDependencyGraphProps {
  contractId: string;
  obligations?: ObligationOut[];
  edges?: EdgeOut[];
  onRefresh?: () => void;
  onSelectObligation?: (obligation: ObligationOut) => void;
  onReviewObligation?: (obligation: ObligationOut) => void;
  isOffline?: boolean;
}

export const ContractDependencyGraph: React.FC<ContractDependencyGraphProps> = ({
  contractId: _contractId,
  obligations = [],
  edges = [],
  onRefresh,
  onSelectObligation,
  onReviewObligation,
  isOffline = false,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [direction, setDirection] = useState<'LR' | 'TB'>('LR');
  const [showRejected, setShowRejected] = useState<boolean>(false);

  // Review interaction state for proposed edges
  const [reviewingEdgeId, setReviewingEdgeId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState<string>('');
  const [edgeActionError, setEdgeActionError] = useState<string | null>(null);

  const patchEdgeMutation = usePatchEdge();

  // Custom node types definition
  const nodeTypes = useMemo(
    () => ({
      obligation: ObligationCustomNode,
    }),
    []
  );

  // Map of obligations by id
  const obligationMap = useMemo(() => {
    const map = new Map<string, ObligationOut>();
    obligations.forEach((ob) => map.set(ob.id, ob));
    return map;
  }, [obligations]);

  // Filter edges: hide rejected and auto_rejected by default
  const usableEdges = useMemo(() => {
    return edges.filter((edge) => {
      if (!showRejected && (edge.status === 'rejected' || edge.status === 'auto_rejected')) {
        return false;
      }
      return true;
    });
  }, [edges, showRejected]);

  // Identify proposed edges that require review
  const proposedEdges = useMemo(() => {
    return edges.filter((e) => e.status === 'proposed');
  }, [edges]);

  // Build raw nodes
  const initialNodes = useMemo<Node<ObligationNodeData>[]>(() => {
    // Only include obligations that are either connected by usableEdges or all obligations if graph is small
    // Here we include obligations connected to at least one edge, plus if no edges, all obligations.
    const connectedObligationIds = new Set<string>();
    usableEdges.forEach((e) => {
      connectedObligationIds.add(e.upstream_id);
      connectedObligationIds.add(e.downstream_id);
    });

    const targetObligations =
      connectedObligationIds.size > 0
        ? obligations.filter((ob) => connectedObligationIds.has(ob.id))
        : obligations;

    return targetObligations.map((ob) => ({
      id: ob.id,
      type: 'obligation',
      position: { x: 0, y: 0 },
      data: {
        obligation: ob,
        onSelect: onSelectObligation,
        onReview: isOffline ? undefined : onReviewObligation,
      },
    }));
  }, [obligations, usableEdges, onSelectObligation, onReviewObligation, isOffline]);

  // Build raw edges with styling according to status & evidence_status
  const initialEdges = useMemo<Edge[]>(() => {
    return usableEdges.map((edge) => {
      const isProposed = edge.status === 'proposed';
      const isUnverified = edge.evidence_status === 'unverified';

      // Edge stroke color & dash
      let strokeColor = '#818cf8'; // indigo-400 (confirmed)
      let strokeDash: string | undefined = undefined;
      let opacity = 1.0;

      if (isProposed) {
        strokeColor = '#f59e0b'; // amber-500 (proposed)
        strokeDash = '6,6';
      }

      if (isUnverified) {
        strokeColor = isProposed ? '#d97706' : '#64748b'; // muted/de-emphasized
        opacity = 0.55;
      }

      return {
        id: edge.id,
        source: edge.upstream_id,
        target: edge.downstream_id,
        label: formatRelation(edge.relation),
        animated: isProposed,
        style: {
          stroke: strokeColor,
          strokeWidth: 2,
          strokeDasharray: strokeDash,
          opacity,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: strokeColor,
          width: 14,
          height: 14,
        },
        labelStyle: {
          fill: '#cbd5e1',
          fontSize: 10,
          fontFamily: 'monospace',
          fontWeight: 500,
        },
        labelBgStyle: {
          fill: '#0f172a',
          fillOpacity: 0.9,
          stroke: '#334155',
          strokeWidth: 1,
          rx: 4,
          ry: 4,
        },
        labelBgPadding: [6, 3] as [number, number],
        data: { edge },
      };
    });
  }, [usableEdges]);

  // Apply Dagre auto-layout
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(() => {
    if (initialNodes.length === 0) {
      return { nodes: [], edges: [] };
    }
    return layoutGraph(initialNodes, initialEdges, direction);
  }, [initialNodes, initialEdges, direction]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<ObligationNodeData>>(layoutedNodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(layoutedEdges);

  // Sync state whenever layouted elements change
  useEffect(() => {
    setNodes(layoutedNodes);
    setFlowEdges(layoutedEdges);
  }, [layoutedNodes, layoutedEdges, setNodes, setFlowEdges]);

  // Edge review handler (Confirm / Reject)
  const handleReviewEdge = useCallback(
    (edgeId: string, action: 'confirm' | 'reject') => {
      if (isOffline) {
        setEdgeActionError('Dependency review is not available in offline demo.');
        return;
      }
      setEdgeActionError(null);
      patchEdgeMutation.mutate(
        {
          edgeId,
          body: {
            action,
            note: reviewNote.trim() || undefined,
          },
        },
        {
          onSuccess: () => {
            setReviewingEdgeId(null);
            setReviewNote('');
            onRefresh?.();
          },
          onError: (err) => {
            setEdgeActionError(err.message || `Failed to ${action} edge.`);
          },
        }
      );
    },
    [patchEdgeMutation, reviewNote, onRefresh, isOffline]
  );

  // When clicking an edge on the canvas
  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    const rawEdge = (edge.data as { edge?: EdgeOut } | undefined)?.edge;
    if (rawEdge && rawEdge.status === 'proposed') {
      setReviewingEdgeId(rawEdge.id);
      setReviewNote('');
      setEdgeActionError(null);
    }
  }, []);

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
      {/* Header bar */}
      <div className="p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-200 bg-slate-50">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-sky-950/80 border border-sky-800/80 flex items-center justify-center text-sky-300 shrink-0">
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 11.5V14m0-2.5v-6a1.5 1.5 0 113 0m-3 6a1.5 1.5 0 00-3 0v2a7.5 7.5 0 0015 0v-5a1.5 1.5 0 00-3 0m-6-3V11m0-5.5v-1a1.5 1.5 0 013 0v1m0 0V11m0-5.5a1.5 1.5 0 013 0v3m0 0V11"
              />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-white">Dependency Graph</h2>
              <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                {usableEdges.length} {usableEdges.length === 1 ? 'edge' : 'edges'} · {nodes.length} nodes
              </span>
              {proposedEdges.length > 0 && (
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-amber-950/80 text-amber-300 border border-amber-800">
                  {proposedEdges.length} proposed to review
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Interactive relationship network connecting upstream prerequisites to downstream commitments
            </p>
          </div>
        </div>

        {/* Right side controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {usableEdges.length > 0 && isExpanded && (
            <>
              {/* Direction toggle */}
              <div className="inline-flex rounded-lg bg-slate-800/80 p-0.5 border border-slate-700 text-xs">
                <button
                  type="button"
                  onClick={() => setDirection('LR')}
                  className={`px-2.5 py-1 rounded-md transition-colors ${
                    direction === 'LR'
                      ? 'bg-slate-700 text-white font-medium shadow-xs'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Left to Right Layout"
                >
                  Horizontal &rarr;
                </button>
                <button
                  type="button"
                  onClick={() => setDirection('TB')}
                  className={`px-2.5 py-1 rounded-md transition-colors ${
                    direction === 'TB'
                      ? 'bg-slate-700 text-white font-medium shadow-xs'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Top to Bottom Layout"
                >
                  Vertical &darr;
                </button>
              </div>

              {/* Show rejected toggle */}
              {edges.some((e) => e.status === 'rejected' || e.status === 'auto_rejected') && (
                <button
                  type="button"
                  onClick={() => setShowRejected(!showRejected)}
                  className={`px-2 py-1 rounded-md border text-xs transition-colors ${
                    showRejected
                      ? 'bg-slate-700 text-slate-200 border-slate-600'
                      : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                  }`}
                >
                  {showRejected ? 'Hide Rejected' : 'Show Rejected'}
                </button>
              )}
            </>
          )}

          {/* Collapse/Expand button */}
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-300 hover:text-white transition-colors"
            aria-label={isExpanded ? 'Collapse graph' : 'Expand graph'}
          >
            {isExpanded ? 'Collapse' : 'Expand'}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="space-y-4">
          {/* Proposed edges review panel */}
          {proposedEdges.length > 0 && (
            <div className="mx-5 mt-4 p-4 rounded-xl border border-amber-900/60 bg-amber-950/20 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                  <h3 className="text-xs font-mono uppercase tracking-wider text-amber-300 font-semibold">
                    Proposed Dependencies Pending Review ({proposedEdges.length})
                  </h3>
                </div>
                <span className="text-[11px] text-amber-200/70">
                  Click a dashed dependency edge or review below
                </span>
              </div>

              {edgeActionError && (
                <div className="p-2.5 rounded bg-rose-950/60 border border-rose-800/80 text-xs text-rose-300 flex items-center justify-between">
                  <span>{edgeActionError}</span>
                  <button
                    type="button"
                    onClick={() => setEdgeActionError(null)}
                    className="text-rose-400 hover:text-rose-200"
                  >
                    ✕
                  </button>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {proposedEdges.map((edge) => {
                  const upstream = obligationMap.get(edge.upstream_id);
                  const downstream = obligationMap.get(edge.downstream_id);
                  const isSelected = reviewingEdgeId === edge.id;

                  return (
                    <div
                      key={edge.id}
                      className={`p-3 rounded-lg border transition-all ${
                        isSelected
                          ? 'border-amber-500 bg-slate-900 shadow-md'
                          : 'border-slate-800 bg-slate-900/90 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div className="text-xs font-medium text-slate-200">
                          <span className="text-indigo-300 font-semibold">
                            {upstream ? upstream.actor : edge.upstream_id}
                          </span>
                          <span className="text-amber-400 font-mono text-[11px] mx-1.5 font-bold">
                            &rarr; {formatRelation(edge.relation)} &rarr;
                          </span>
                          <span className="text-sky-300 font-semibold">
                            {downstream ? downstream.actor : edge.downstream_id}
                          </span>
                        </div>
                        <span className="px-1.5 py-0.2 rounded text-[10px] font-mono uppercase bg-amber-950/80 text-amber-300 border border-amber-800 shrink-0">
                          Proposed
                        </span>
                      </div>

                      {/* Evidence / Rationale snippet */}
                      {edge.rationale && (
                        <p className="text-[11px] text-slate-400 line-clamp-2 italic mb-1">
                          Rationale: {edge.rationale}
                        </p>
                      )}
                      {edge.evidence_quote && (
                        <p className="text-[11px] text-slate-400 line-clamp-2 italic mb-2 bg-slate-850 p-1.5 rounded border border-slate-800">
                          &ldquo;{edge.evidence_quote}&rdquo; {edge.page ? `(p. ${edge.page})` : ''}
                        </p>
                      )}

                      {/* Review controls */}
                      {isSelected ? (
                        <div className="space-y-2 pt-1 border-t border-slate-800">
                          <input
                            type="text"
                            placeholder="Optional reviewer note..."
                            value={reviewNote}
                            onChange={(e) => setReviewNote(e.target.value)}
                            className="w-full px-2.5 py-1 text-xs rounded bg-slate-800 border border-slate-700 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                          />
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => handleReviewEdge(edge.id, 'confirm')}
                              disabled={isOffline || patchEdgeMutation.isPending}
                              title={isOffline ? 'Not available in offline demo' : undefined}
                              className="px-2.5 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {patchEdgeMutation.isPending ? 'Saving...' : '✓ Confirm'}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleReviewEdge(edge.id, 'reject')}
                              disabled={isOffline || patchEdgeMutation.isPending}
                              title={isOffline ? 'Not available in offline demo' : undefined}
                              className="px-2.5 py-1 rounded bg-rose-800 hover:bg-rose-700 text-white text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {patchEdgeMutation.isPending ? 'Saving...' : '✕ Reject'}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setReviewingEdgeId(null);
                                setReviewNote('');
                              }}
                              className="px-2 py-1 rounded bg-slate-800 text-slate-300 hover:text-white text-xs"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => {
                              if (!isOffline) {
                                setReviewingEdgeId(edge.id);
                                setReviewNote('');
                                setEdgeActionError(null);
                              }
                            }}
                            disabled={isOffline}
                            title={isOffline ? 'Not available in offline demo' : undefined}
                            className="text-[11px] font-medium text-amber-300 hover:text-amber-200 underline underline-offset-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline"
                          >
                            Review &amp; verify dependency &rarr;
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Graph canvas or empty state */}
          {usableEdges.length === 0 ? (
            <div className="p-12 text-center space-y-2 border-t border-slate-800/80">
              <div className="w-10 h-10 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center mx-auto text-slate-400">
                <svg
                  className="w-5 h-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
              </div>
              <p className="text-sm font-medium text-slate-200">
                No dependency edges found
              </p>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No relational dependencies (precedence, triggers, or conditions) have been identified among the obligations in this contract.
              </p>
            </div>
          ) : (
            <div className="relative h-[550px] w-full border-t border-slate-200 bg-slate-50">
              <ReactFlow
                nodes={nodes}
                edges={flowEdges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onEdgeClick={onEdgeClick}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.2}
                maxZoom={2.0}
                proOptions={{ hideAttribution: true }}
              >
                <Background
                  color="#cbd5e1"
                  gap={18}
                  size={1}
                  variant={BackgroundVariant.Dots}
                />
                <Controls
                  className="!bg-slate-900 !border !border-slate-700 !shadow-lg [&>button]:!bg-slate-800 [&>button]:!border-slate-700 [&>button]:!text-slate-300 [&>button:hover]:!bg-slate-700 [&>button:hover]:!text-white"
                  showInteractive={false}
                />
                <MiniMap
                  nodeColor="#475569"
                  maskColor="rgba(248, 250, 252, 0.75)"
                  className="!bg-slate-900 !border !border-slate-800 !rounded-lg overflow-hidden"
                />

                {/* Legend Panel */}
                <Panel
                  position="bottom-left"
                  className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg text-[11px] space-y-1.5 backdrop-blur-sm shadow-md"
                >
                  <div className="font-mono text-[10px] uppercase font-semibold text-slate-400">
                    Dependency Legend
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-0.5 bg-indigo-400 inline-block" />
                    <span className="text-slate-300">solid = confirmed dependency</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-0.5 border-t-2 border-dashed border-amber-400 inline-block" />
                    <span className="text-slate-300">dashed = proposed dependency</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-0.5 bg-slate-500 opacity-50 inline-block" />
                    <span className="text-slate-400">de-emphasized = unverified evidence</span>
                  </div>
                </Panel>
              </ReactFlow>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ContractDependencyGraph;
