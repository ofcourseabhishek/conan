import React, { useState, useMemo, useCallback } from 'react';
import type {
  ConflictOut,
  ConflictKind,
  ClauseOut,
  ObligationOut,
} from '../types/api';
import { useReviewConflict } from '../hooks/useObligations';

export interface ConflictPanelProps {
  conflicts?: ConflictOut[];
  clauses?: ClauseOut[];
  obligations?: ObligationOut[];
  onRefresh: () => void;
  onSelectObligation?: (obligation: ObligationOut) => void;
  isOffline?: boolean;
}

function formatConflictKind(kind: ConflictKind): string {
  switch (kind) {
    case 'offset_mismatch':
      return 'Offset Mismatch';
    case 'day_type_mismatch':
      return 'Day Type Mismatch';
    case 'amount_mismatch':
      return 'Amount Mismatch';
    case 'date_mismatch':
      return 'Date Mismatch';
    case 'notice_period':
      return 'Notice Period Conflict';
    case 'llm':
      return 'AI Inconsistency Flag';
    default:
      return String(kind).replace(/_/g, ' ');
  }
}

export const ConflictPanel: React.FC<ConflictPanelProps> = ({
  conflicts = [],
  clauses = [],
  obligations = [],
  onRefresh,
  onSelectObligation,
  isOffline = false,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'open' | 'dismissed' | 'all'>('open');

  // Mutation state for active review (dismiss / reopen)
  const [activeConflictId, setActiveConflictId] = useState<string | null>(null);
  const [reviewAction, setReviewAction] = useState<'dismiss' | 'reopen'>('dismiss');
  const [reviewNote, setReviewNote] = useState<string>('');
  const [isConfirming, setIsConfirming] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const reviewConflictMutation = useReviewConflict();

  // Fast lookup for clauses by ID
  const clauseMap = useMemo(() => {
    const map = new Map<string, ClauseOut>();
    clauses.forEach((c) => map.set(c.id, c));
    return map;
  }, [clauses]);

  // Fast lookup for obligations by ID
  const obligationMap = useMemo(() => {
    const map = new Map<string, ObligationOut>();
    obligations.forEach((o) => map.set(o.id, o));
    return map;
  }, [obligations]);

  const openConflicts = useMemo(
    () => conflicts.filter((c) => c.status === 'open'),
    [conflicts]
  );
  const dismissedConflicts = useMemo(
    () => conflicts.filter((c) => c.status === 'dismissed'),
    [conflicts]
  );

  const displayedConflicts = useMemo(() => {
    if (activeTab === 'open') return openConflicts;
    if (activeTab === 'dismissed') return dismissedConflicts;
    return conflicts;
  }, [activeTab, openConflicts, dismissedConflicts, conflicts]);

  const handleStartReview = useCallback((conflictId: string, action: 'dismiss' | 'reopen') => {
    if (isOffline) return;
    setActiveConflictId(conflictId);
    setReviewAction(action);
    setReviewNote('');
    setIsConfirming(false);
    setActionError(null);
  }, [isOffline]);

  const handleCancelReview = useCallback(() => {
    setActiveConflictId(null);
    setReviewNote('');
    setIsConfirming(false);
    setActionError(null);
    reviewConflictMutation.reset();
  }, [reviewConflictMutation]);

  const handleSubmitReview = useCallback(
    (conflictId: string) => {
      if (isOffline) {
        setActionError('Conflict review is not available in offline demo.');
        return;
      }
      setActionError(null);
      reviewConflictMutation.mutate(
        {
          conflictId,
          body: {
            action: reviewAction,
            note: reviewNote.trim() || undefined,
          },
        },
        {
          onSuccess: () => {
            setActiveConflictId(null);
            setReviewNote('');
            setIsConfirming(false);
            onRefresh();
          },
          onError: (err) => {
            setActionError(err.message || `Failed to ${reviewAction} conflict.`);
          },
        }
      );
    },
    [reviewAction, reviewNote, reviewConflictMutation, onRefresh, isOffline]
  );

  if (conflicts.length === 0) {
    return null;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
      {/* Header bar */}
      <div className="p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 bg-slate-900/90">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-amber-950/70 border border-amber-800/80 flex items-center justify-center text-amber-300 shrink-0">
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
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-white">Contract Inconsistencies</h2>
              {openConflicts.length > 0 ? (
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-amber-950/90 text-amber-300 border border-amber-800 animate-pulse">
                  {openConflicts.length} OPEN
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-950/70 text-emerald-300 border border-emerald-800">
                  0 OPEN
                </span>
              )}
              {dismissedConflicts.length > 0 && (
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-400 border border-slate-700">
                  {dismissedConflicts.length} dismissed
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Conflicting operational commitments or inconsistent deadlines across document provisions
            </p>
          </div>
        </div>

        {/* Tab & Collapse controls */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex rounded-lg bg-slate-800/80 p-0.5 border border-slate-700 text-xs">
            <button
              type="button"
              onClick={() => setActiveTab('open')}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                activeTab === 'open'
                  ? 'bg-slate-700 text-white font-medium shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Open ({openConflicts.length})
            </button>
            {dismissedConflicts.length > 0 && (
              <button
                type="button"
                onClick={() => setActiveTab('dismissed')}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  activeTab === 'dismissed'
                    ? 'bg-slate-700 text-white font-medium shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Dismissed ({dismissedConflicts.length})
              </button>
            )}
            <button
              type="button"
              onClick={() => setActiveTab('all')}
              className={`px-2.5 py-1 rounded-md transition-colors ${
                activeTab === 'all'
                  ? 'bg-slate-700 text-white font-medium shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              All ({conflicts.length})
            </button>
          </div>

          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-300 hover:text-white transition-colors"
            aria-label={isExpanded ? 'Collapse inconsistencies panel' : 'Expand inconsistencies panel'}
          >
            {isExpanded ? 'Collapse' : 'Expand'}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="p-5 space-y-4">
          {/* Prominent Legal Order-of-Precedence Disclaimer Banner */}
          <div className="p-3.5 rounded-lg bg-slate-950/70 border border-amber-900/60 flex items-start gap-3">
            <span className="text-amber-400 text-sm mt-0.5 shrink-0">⚠️</span>
            <p className="text-xs text-amber-200/90 leading-relaxed font-sans">
              <strong className="font-semibold text-amber-300">Important Limitation: </strong>
              Conan detects and flags potential inconsistencies between provisions. It does not resolve ambiguities or decide which clause prevails. Review the contract&apos;s order-of-precedence clause or consult legal counsel.
            </p>
          </div>

          {/* Action error banner */}
          {actionError && (
            <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-xs text-rose-300 flex items-center justify-between">
              <span>{actionError}</span>
              <button
                type="button"
                onClick={() => setActionError(null)}
                className="text-rose-400 hover:text-rose-200 ml-3 text-sm"
              >
                ✕
              </button>
            </div>
          )}

          {/* Conflict List */}
          {displayedConflicts.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-500 italic rounded-lg border border-slate-800 bg-slate-950/40">
              No {activeTab} inconsistencies found for this contract.
            </div>
          ) : (
            <div className="space-y-4">
              {displayedConflicts.map((conflict) => {
                const isDismissed = conflict.status === 'dismissed';
                const isReviewingThis = activeConflictId === conflict.id;

                // Resolve Clause A details
                const clauseA = clauseMap.get(conflict.clause_a);
                const clauseB = clauseMap.get(conflict.clause_b);

                const sectionA = clauseA?.section_ref
                  ? `§${clauseA.section_ref}`
                  : conflict.clause_a;
                const pageA = clauseA?.page_start != null ? `p. ${clauseA.page_start}` : null;

                const sectionB = clauseB?.section_ref
                  ? `§${clauseB.section_ref}`
                  : conflict.clause_b;
                const pageB = clauseB?.page_start != null ? `p. ${clauseB.page_start}` : null;

                return (
                  <div
                    key={conflict.id}
                    className={`rounded-xl border transition-colors duration-200 ${
                      isDismissed
                        ? 'border-slate-200 bg-slate-50 opacity-80'
                        : 'border-l-4 border-l-rose-300 border-y-slate-200 border-r-slate-200 bg-white shadow-sm'
                    }`}
                  >
                    {/* Conflict Card Header */}
                    <div className="p-4 border-b border-slate-800/80 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Kind Badge */}
                        <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-amber-950/80 text-amber-300 border border-amber-800">
                          {formatConflictKind(conflict.kind)}
                        </span>

                        {/* Source Badge */}
                        <span className="px-1.5 py-0.2 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-400 border border-slate-700">
                          via {conflict.source}
                        </span>

                        {/* Status Badge */}
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase font-medium border ${
                            isDismissed
                              ? 'bg-slate-800 text-slate-400 border-slate-700'
                              : 'bg-rose-950/70 text-rose-300 border-rose-800'
                          }`}
                        >
                          {conflict.status}
                        </span>
                      </div>

                      {/* Top Action Toggle */}
                      {!isReviewingThis && (
                        <div className="self-start sm:self-auto">
                          {isDismissed ? (
                            <button
                              type="button"
                              onClick={() => !isOffline && handleStartReview(conflict.id, 'reopen')}
                              disabled={isOffline}
                              title={isOffline ? 'Not available in offline demo' : undefined}
                              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              ↺ Reopen Inconsistency
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => !isOffline && handleStartReview(conflict.id, 'dismiss')}
                              disabled={isOffline}
                              title={isOffline ? 'Not available in offline demo' : undefined}
                              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-amber-300 hover:text-amber-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              ✓ Dismiss Inconsistency
                            </button>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Conflict Body */}
                    <div className="p-4 space-y-3.5">
                      {/* Description */}
                      <p className="text-xs text-slate-200 leading-relaxed font-sans">
                        {conflict.description}
                      </p>

                      {/* Equal Dual-Provision Side-by-Side Presentation */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                        {/* Provision A */}
                        <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-950/70 space-y-2">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-slate-300 font-mono">
                              Provision A: {sectionA}
                            </span>
                            {pageA && (
                              <span className="text-[11px] font-mono text-slate-400">
                                {pageA}
                              </span>
                            )}
                          </div>
                          {conflict.quote_a ? (
                            <blockquote className="text-xs text-slate-300 italic border-l-2 border-slate-700 pl-2.5 leading-relaxed">
                              &ldquo;{conflict.quote_a}&rdquo;
                            </blockquote>
                          ) : (
                            <p className="text-xs text-slate-500 italic">No quote available</p>
                          )}
                        </div>

                        {/* Provision B */}
                        <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-950/70 space-y-2">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-slate-300 font-mono">
                              Provision B: {sectionB}
                            </span>
                            {pageB && (
                              <span className="text-[11px] font-mono text-slate-400">
                                {pageB}
                              </span>
                            )}
                          </div>
                          {conflict.quote_b ? (
                            <blockquote className="text-xs text-slate-300 italic border-l-2 border-slate-700 pl-2.5 leading-relaxed">
                              &ldquo;{conflict.quote_b}&rdquo;
                            </blockquote>
                          ) : (
                            <p className="text-xs text-slate-500 italic">No quote available</p>
                          )}
                        </div>
                      </div>

                      {/* Connected Obligations */}
                      {conflict.obligation_ids && conflict.obligation_ids.length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap pt-1 text-xs">
                          <span className="text-[11px] font-mono text-slate-400">
                            Affects obligations:
                          </span>
                          {conflict.obligation_ids.map((obId) => {
                            const ob = obligationMap.get(obId);
                            return (
                              <button
                                key={obId}
                                type="button"
                                onClick={() => ob && onSelectObligation?.(ob)}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors"
                                title={ob ? `${ob.actor}: ${ob.action}` : obId}
                              >
                                <span>{obId}</span>
                                {ob && <span className="text-slate-400 truncate max-w-[140px]">({ob.actor})</span>}
                              </button>
                            );
                          })}
                        </div>
                      )}

                      {/* Interactive Review Form when Dismissing or Reopening */}
                      {isReviewingThis && (
                        <div className="p-3.5 rounded-lg bg-slate-800/90 border border-slate-700 space-y-3 mt-3">
                          <div className="flex items-center justify-between">
                            <h4 className="text-xs font-semibold text-white">
                              {reviewAction === 'dismiss'
                                ? 'Dismiss this Inconsistency'
                                : 'Reopen this Inconsistency'}
                            </h4>
                            <span className="text-[10px] text-slate-400">
                              {reviewAction === 'dismiss'
                                ? 'Mark evaluated by counsel or order-of-precedence'
                                : 'Return to active open state'}
                            </span>
                          </div>

                          <div className="space-y-1.5">
                            <label className="block text-[10px] font-mono uppercase text-slate-400">
                              Reviewer Note (optional)
                            </label>
                            <textarea
                              rows={2}
                              value={reviewNote}
                              onChange={(e) => setReviewNote(e.target.value)}
                              placeholder={
                                reviewAction === 'dismiss'
                                  ? 'e.g. Schedule B controls per Section 12 Order of Precedence clause...'
                                  : 'e.g. Reopening after contract amendment review...'
                              }
                              className="w-full px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-amber-500 resize-y"
                            />
                          </div>

                          {/* Confirmation Check or Action Buttons */}
                          {isConfirming ? (
                            <div className="flex items-center gap-2 p-2 rounded bg-amber-950/40 border border-amber-900/60">
                              <span className="text-xs text-amber-200">
                                Confirm {reviewAction === 'dismiss' ? 'dismissal' : 'reopening'} of this inconsistency?
                              </span>
                              <button
                                type="button"
                                onClick={() => handleSubmitReview(conflict.id)}
                                disabled={isOffline || reviewConflictMutation.isPending}
                                title={isOffline ? 'Not available in offline demo' : undefined}
                                className={`px-2.5 py-1 rounded text-xs font-semibold text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                                  reviewAction === 'dismiss'
                                    ? 'bg-amber-600 hover:bg-amber-500 text-slate-950'
                                    : 'bg-indigo-600 hover:bg-indigo-500'
                                }`}
                              >
                                {reviewConflictMutation.isPending ? 'Updating...' : 'Yes, Confirm'}
                              </button>
                              <button
                                type="button"
                                onClick={() => setIsConfirming(false)}
                                disabled={reviewConflictMutation.isPending}
                                className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => !isOffline && setIsConfirming(true)}
                                disabled={isOffline}
                                title={isOffline ? 'Not available in offline demo' : undefined}
                                className={`px-3 py-1.5 rounded text-xs font-semibold text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                                  reviewAction === 'dismiss'
                                    ? 'bg-amber-600 hover:bg-amber-500 text-slate-950'
                                    : 'bg-indigo-600 hover:bg-indigo-500'
                                }`}
                              >
                                {reviewAction === 'dismiss' ? 'Proceed to Dismiss' : 'Proceed to Reopen'}
                              </button>
                              <button
                                type="button"
                                onClick={handleCancelReview}
                                className="px-2.5 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ConflictPanel;
