import React, { useState, useMemo, useCallback } from 'react';
import type {
  ObligationOut,
  EventOut,
  EdgeOut,
  EventKey,
} from '../types/api';
import { useUpdateEvent } from '../hooks/useObligations';

export interface ContractTimelineProps {
  contractId: string;
  events?: EventOut[];
  obligations?: ObligationOut[];
  edges?: EdgeOut[];
  onRefresh: () => void;
  isOffline?: boolean;
}

interface ResolvedTimelineItem {
  id: string;
  kind: 'event' | 'obligation';
  dateStr: string;
  timestamp: number;
  event?: EventOut;
  obligation?: ObligationOut;
}

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

export const ContractTimeline: React.FC<ContractTimelineProps> = ({
  contractId,
  events = [],
  obligations = [],
  edges: _edges = [],
  onRefresh,
  isOffline = false,
}) => {
  // Active editing state for setting an event date
  // editingEventKey is the key of the event being updated
  const [editingEventKey, setEditingEventKey] = useState<string | null>(null);
  const [inputDate, setInputDate] = useState<string>('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [filterType, setFilterType] = useState<'all' | 'events' | 'obligations'>('all');

  const updateEventMutation = useUpdateEvent();

  // Map of obligations by ID for fast lookup
  const obligationMap = useMemo(() => {
    const map = new Map<string, ObligationOut>();
    for (const ob of obligations) {
      map.set(ob.id, ob);
    }
    return map;
  }, [obligations]);

  // Map of events by key
  const eventMap = useMemo(() => {
    const map = new Map<string, EventOut>();
    for (const ev of events) {
      map.set(ev.key, ev);
    }
    return map;
  }, [events]);

  // Collect all resolved items (events with date or obligations with resolved due_date)
  const resolvedItems = useMemo<ResolvedTimelineItem[]>(() => {
    const items: ResolvedTimelineItem[] = [];

    // 1. Events that have dates
    for (const ev of events) {
      if (ev.date) {
        const time = new Date(ev.date).getTime();
        items.push({
          id: `event-${ev.key}`,
          kind: 'event',
          dateStr: ev.date,
          timestamp: isNaN(time) ? 0 : time,
          event: ev,
        });
      }
    }

    // 2. Obligations that have resolved due_date
    for (const ob of obligations) {
      if (ob.due_date && ob.resolution_status === 'resolved') {
        const time = new Date(ob.due_date).getTime();
        items.push({
          id: `ob-${ob.id}`,
          kind: 'obligation',
          dateStr: ob.due_date,
          timestamp: isNaN(time) ? 0 : time,
          obligation: ob,
        });
      }
    }

    // Sort chronologically (oldest to newest)
    items.sort((a, b) => a.timestamp - b.timestamp);
    return items;
  }, [events, obligations]);

  // Collect unresolved trigger obligations
  const unresolvedTriggerObligations = useMemo(() => {
    return obligations.filter((ob) => ob.resolution_status === 'unresolved_trigger');
  }, [obligations]);

  // Other unresolved obligations (e.g. conditional_pending, ambiguous)
  const otherUnresolvedObligations = useMemo(() => {
    return obligations.filter(
      (ob) =>
        ob.resolution_status !== 'resolved' &&
        ob.resolution_status !== 'unresolved_trigger' &&
        ob.resolution_status !== 'no_deadline'
    );
  }, [obligations]);

  // Unresolved events (events that have no date yet)
  const unresolvedEvents = useMemo(() => {
    return events.filter((ev) => !ev.date);
  }, [events]);

  // Filter resolved items
  const filteredResolvedItems = useMemo(() => {
    if (filterType === 'events') {
      return resolvedItems.filter((item) => item.kind === 'event');
    }
    if (filterType === 'obligations') {
      return resolvedItems.filter((item) => item.kind === 'obligation');
    }
    return resolvedItems;
  }, [resolvedItems, filterType]);

  // Trigger date submission
  const handleSaveEventDate = useCallback(
    (eventKey: string) => {
      if (isOffline) {
        setActionError('Event date updates are not available in offline demo.');
        return;
      }
      if (!inputDate) {
        setActionError('Please select a valid date.');
        return;
      }

      setActionError(null);
      updateEventMutation.mutate(
        {
          contractId,
          key: eventKey,
          body: { date: inputDate },
        },
        {
          onSuccess: () => {
            setEditingEventKey(null);
            setInputDate('');
            onRefresh();
          },
          onError: (err) => {
            setActionError(err.message || 'Failed to update event date.');
          },
        }
      );
    },
    [contractId, inputDate, updateEventMutation, onRefresh, isOffline]
  );

  const handleStartEditing = useCallback(
    (eventKey: string, currentDate?: string | null) => {
      if (isOffline) return;
      setEditingEventKey(eventKey);
      setInputDate(currentDate || '');
      setActionError(null);
    },
    [isOffline]
  );

  const handleCancelEditing = useCallback(() => {
    setEditingEventKey(null);
    setInputDate('');
    setActionError(null);
    updateEventMutation.reset();
  }, [updateEventMutation]);

  const totalActionable = unresolvedTriggerObligations.length + unresolvedEvents.length;

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
      {/* Header bar */}
      <div className="p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-200 bg-slate-50">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-indigo-950/80 border border-indigo-800/80 flex items-center justify-center text-indigo-300 shrink-0">
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
                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-white">Contract Timeline</h2>
              <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                {resolvedItems.length} resolved
              </span>
              {totalActionable > 0 && (
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-amber-950/80 text-amber-300 border border-amber-800">
                  {totalActionable} awaiting trigger
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Chronological milestones, resolved deadlines, and pending triggers
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {resolvedItems.length > 0 && (
            <div className="inline-flex rounded-lg bg-slate-800/80 p-0.5 border border-slate-700 text-xs">
              <button
                type="button"
                onClick={() => setFilterType('all')}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterType === 'all'
                    ? 'bg-slate-700 text-white font-medium shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                All ({resolvedItems.length})
              </button>
              <button
                type="button"
                onClick={() => setFilterType('events')}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterType === 'events'
                    ? 'bg-slate-700 text-white font-medium shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Events
              </button>
              <button
                type="button"
                onClick={() => setFilterType('obligations')}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterType === 'obligations'
                    ? 'bg-slate-700 text-white font-medium shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Obligations
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-300 hover:text-white transition-colors"
            aria-label={isExpanded ? 'Collapse timeline' : 'Expand timeline'}
          >
            {isExpanded ? 'Collapse' : 'Expand'}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="p-5 space-y-6">
          {/* Action error banner if mutation failed */}
          {actionError && (
            <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-800/80 text-xs text-rose-300 flex items-center justify-between">
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

          {/* Section: Unresolved Triggers & Actionable Deadlines */}
          {(unresolvedTriggerObligations.length > 0 || unresolvedEvents.length > 0) && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                <h3 className="text-xs font-mono uppercase tracking-wider text-amber-300 font-semibold">
                  Awaiting Trigger Dates ({unresolvedTriggerObligations.length} obligations, {unresolvedEvents.length} events)
                </h3>
              </div>
              <p className="text-xs text-amber-200/80">
                These obligations rely on relative deadlines anchored to specific milestones. Enter the trigger event date below to automatically compute and resolve the downstream deadlines.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                {/* 1. Obligations with resolution_status === 'unresolved_trigger' */}
                {unresolvedTriggerObligations.map((ob) => {
                  const targetEventKey = ob.trigger_event as EventKey | null;
                  const matchingEvent = targetEventKey ? eventMap.get(targetEventKey) : undefined;
                  const isEditingThis = editingEventKey === targetEventKey;

                  return (
                    <div
                      key={ob.id}
                      className="p-3.5 rounded-lg border border-amber-200 bg-white space-y-2.5 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase font-semibold bg-amber-950/80 text-amber-300 border border-amber-800">
                              Needs trigger date
                            </span>
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-300 border border-slate-700">
                              {ob.category}
                            </span>
                            <span className="text-[11px] font-semibold text-slate-200">
                              {ob.actor}
                            </span>
                          </div>
                          <p className="text-xs text-slate-100 font-medium">
                            {ob.action} {ob.object || ''}
                          </p>
                        </div>
                      </div>

                      {/* Trigger explanation */}
                      <div className="text-[11px] text-amber-200/90 bg-amber-950/40 p-2 rounded border border-amber-900/40">
                        <span className="font-semibold text-amber-300">Trigger needed: </span>
                        {ob.trigger_label || ob.trigger_event || 'Specific contract event'}
                        {ob.deadline_rule?.raw_text && (
                          <div className="text-[10px] text-slate-400 mt-0.5 italic">
                            Rule: &ldquo;{ob.deadline_rule.raw_text}&rdquo;
                          </div>
                        )}
                      </div>

                      {/* Set date button or inline input */}
                      {targetEventKey && (
                        <div>
                          {isEditingThis ? (
                            <div className="space-y-1.5 pt-1">
                              <label className="block text-[10px] font-mono text-slate-400 uppercase">
                                Set date for: {matchingEvent?.label || targetEventKey}
                              </label>
                              <div className="flex items-center gap-2">
                                <input
                                  type="date"
                                  value={inputDate}
                                  onChange={(e) => setInputDate(e.target.value)}
                                  className="px-2.5 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
                                />
                                <button
                                  type="button"
                                  onClick={() => handleSaveEventDate(targetEventKey)}
                                  disabled={updateEventMutation.isPending || !inputDate}
                                  className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-500 text-slate-950 text-xs font-semibold transition-colors disabled:opacity-50"
                                >
                                  {updateEventMutation.isPending ? 'Saving...' : 'Save'}
                                </button>
                                <button
                                  type="button"
                                  onClick={handleCancelEditing}
                                  disabled={updateEventMutation.isPending}
                                  className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-300"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => !isOffline && handleStartEditing(targetEventKey)}
                              disabled={isOffline}
                              title={isOffline ? 'Not available in offline demo' : undefined}
                              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-amber-300 hover:text-amber-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              <span>📅 Set trigger date ({matchingEvent?.label || targetEventKey})</span>
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* 2. Unresolved Events that have dependent obligations */}
                {unresolvedEvents.map((ev) => {
                  const isEditingThis = editingEventKey === ev.key;
                  const dependentCount = ev.dependent_obligation_ids.length;

                  return (
                    <div
                      key={ev.key}
                      className="p-3.5 rounded-lg border border-slate-200 bg-white space-y-2.5 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-indigo-950/80 text-indigo-300 border border-indigo-800">
                              Event
                            </span>
                            <span className="text-xs font-semibold text-slate-200">
                              {ev.label}
                            </span>
                          </div>
                          <p className="text-[11px] font-mono text-slate-400 mt-0.5">
                            Key: {ev.key}
                          </p>
                        </div>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-950/70 text-amber-300 border border-amber-800/80">
                          Date unset
                        </span>
                      </div>

                      {/* Visual indicator of downstream dependent obligations */}
                      {dependentCount > 0 ? (
                        <div className="p-2 rounded bg-slate-850/80 border border-slate-800 space-y-1">
                          <div className="flex items-center gap-1 text-[11px] font-medium text-amber-300">
                            <span>⚡ Downstream impact:</span>
                            <span>blocks {dependentCount} obligation{dependentCount === 1 ? '' : 's'}</span>
                          </div>
                          <ul className="text-[10px] text-slate-400 space-y-0.5 pl-2 list-disc list-inside">
                            {ev.dependent_obligation_ids.slice(0, 3).map((depId) => {
                              const dep = obligationMap.get(depId);
                              return (
                                <li key={depId} className="truncate">
                                  {dep ? `${dep.actor}: ${dep.action}` : depId}
                                </li>
                              );
                            })}
                            {dependentCount > 3 && (
                              <li className="text-slate-500 italic">
                                + {dependentCount - 3} more obligations
                              </li>
                            )}
                          </ul>
                        </div>
                      ) : (
                        <p className="text-[11px] text-slate-500 italic">
                          No obligations directly waiting on this event.
                        </p>
                      )}

                      {/* Inline date edit */}
                      {isEditingThis ? (
                        <div className="space-y-1.5 pt-1">
                          <label className="block text-[10px] font-mono text-slate-400 uppercase">
                            Set date for {ev.label}
                          </label>
                          <div className="flex items-center gap-2">
                            <input
                              type="date"
                              value={inputDate}
                              onChange={(e) => setInputDate(e.target.value)}
                              className="px-2.5 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                            />
                            <button
                              type="button"
                              onClick={() => handleSaveEventDate(ev.key)}
                              disabled={updateEventMutation.isPending || !inputDate}
                              className="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition-colors disabled:opacity-50"
                            >
                              {updateEventMutation.isPending ? 'Saving...' : 'Save'}
                            </button>
                            <button
                              type="button"
                              onClick={handleCancelEditing}
                              disabled={updateEventMutation.isPending}
                              className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-300"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => !isOffline && handleStartEditing(ev.key)}
                          disabled={isOffline}
                          title={isOffline ? 'Not available in offline demo' : undefined}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          📅 Set event date
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Other unresolved obligations (e.g. conditional_pending) */}
          {otherUnresolvedObligations.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2">
              <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold">
                Other Pending Deadlines ({otherUnresolvedObligations.length})
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {otherUnresolvedObligations.map((ob) => (
                  <div
                    key={ob.id}
                    className="p-2.5 rounded-lg border border-slate-800/80 bg-slate-850/60 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-semibold text-slate-200 truncate">{ob.actor}</span>
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-mono text-amber-300/90 capitalize">
                        {ob.resolution_status.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <p className="text-slate-300 line-clamp-1">{ob.action} {ob.object || ''}</p>
                    {ob.condition_text && (
                      <p className="text-[10px] text-slate-400 italic line-clamp-1">
                        If: {ob.condition_text}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section: Chronological Timeline of Resolved Items */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold">
                Chronological Schedule ({filteredResolvedItems.length} milestone{filteredResolvedItems.length === 1 ? '' : 's'})
              </h3>
            </div>

            {filteredResolvedItems.length === 0 ? (
              <div className="p-8 rounded-xl border border-dashed border-slate-800 text-center space-y-1.5">
                <p className="text-sm font-medium text-slate-300">
                  No resolved timeline dates found
                </p>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Provide trigger event dates above or ensure the contract contains absolute dates to generate the chronological timeline.
                </p>
              </div>
            ) : (
              <div className="relative pl-6 sm:pl-8 space-y-6 before:absolute before:left-2.5 sm:before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
                {filteredResolvedItems.map((item) => {
                  const isEvent = item.kind === 'event';
                  const isObligation = item.kind === 'obligation';
                  const ev = item.event;
                  const ob = item.obligation;
                  const isEditingThis = isEvent && ev && editingEventKey === ev.key;

                  return (
                    <div key={item.id} className="relative group">
                      {/* Timeline dot */}
                      <div
                        className={`absolute -left-[27px] sm:-left-[31px] top-1.5 w-4 h-4 rounded-full border-2 transition-transform group-hover:scale-110 ${
                          isEvent
                            ? 'bg-indigo-900 border-indigo-400'
                            : ob?.status === 'done'
                            ? 'bg-emerald-900 border-emerald-400'
                            : 'bg-slate-900 border-sky-400'
                        }`}
                      />

                      {/* Timeline Card */}
                      <div className="p-4 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-colors space-y-2 shadow-sm">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5">
                          <div className="flex items-center gap-2 flex-wrap">
                            {/* Date Badge */}
                            <span className="px-2.5 py-0.5 rounded text-xs font-mono font-semibold bg-slate-800 text-slate-200 border border-slate-700">
                              {formatDate(item.dateStr)}
                            </span>

                            {/* Kind Badge */}
                            {isEvent && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-indigo-950/70 text-indigo-300 border border-indigo-800">
                                Milestone Event
                              </span>
                            )}
                            {isObligation && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-sky-950/70 text-sky-300 border border-sky-800">
                                Obligation Due
                              </span>
                            )}

                            {/* Provenance badge if available */}
                            {ob?.date_provenance && (
                              <span className="text-[10px] font-mono text-slate-400">
                                source: {ob.date_provenance.replace(/_/g, ' ')}
                              </span>
                            )}
                            {ev?.date_source && (
                              <span className="text-[10px] font-mono text-slate-400">
                                source: {ev.date_source.replace(/_/g, ' ')}
                              </span>
                            )}
                          </div>

                          {/* Quick action for event to change date */}
                          {isEvent && ev && (
                            <button
                              type="button"
                              onClick={() => !isOffline && handleStartEditing(ev.key, ev.date)}
                              disabled={isOffline}
                              title={isOffline ? 'Not available in offline demo' : undefined}
                              className="text-[11px] text-slate-400 hover:text-slate-200 self-start sm:self-auto transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              ✏ Edit Date
                            </button>
                          )}
                        </div>

                        {/* Card Content */}
                        {isEvent && ev && (
                          <div className="space-y-1.5 pt-1">
                            <h4 className="text-sm font-semibold text-white">
                              {ev.label}
                            </h4>
                            <p className="text-xs font-mono text-slate-400">
                              Event key: <span className="text-slate-300">{ev.key}</span>
                            </p>

                            {/* Downstream impact banner */}
                            {ev.dependent_obligation_ids.length > 0 && (
                              <div className="pt-1.5 flex items-center gap-1.5 flex-wrap text-xs">
                                <span className="text-amber-300/90 font-medium">
                                  ⚡ Drives {ev.dependent_obligation_ids.length} downstream deadline{ev.dependent_obligation_ids.length === 1 ? '' : 's'}:
                                </span>
                                {ev.dependent_obligation_ids.map((depId) => {
                                  const dep = obligationMap.get(depId);
                                  return (
                                    <span
                                      key={depId}
                                      className="px-2 py-0.5 rounded bg-slate-800 text-[11px] font-mono text-slate-300 border border-slate-700"
                                    >
                                      {dep ? dep.actor : depId}
                                    </span>
                                  );
                                })}
                              </div>
                            )}

                            {/* Inline edit form */}
                            {isEditingThis && (
                              <div className="mt-2 p-3 rounded-lg bg-slate-800/90 border border-slate-700 space-y-2">
                                <label className="block text-[10px] font-mono text-slate-400 uppercase">
                                  Change date for {ev.label}
                                </label>
                                <div className="flex items-center gap-2 flex-wrap">
                                  <input
                                    type="date"
                                    value={inputDate}
                                    onChange={(e) => setInputDate(e.target.value)}
                                    className="px-2.5 py-1 rounded bg-slate-900 border border-slate-600 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => handleSaveEventDate(ev.key)}
                                    disabled={updateEventMutation.isPending || !inputDate}
                                    className="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition-colors disabled:opacity-50"
                                  >
                                    {updateEventMutation.isPending ? 'Saving...' : 'Update'}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={handleCancelEditing}
                                    className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs text-slate-300"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        {isObligation && ob && (
                          <div className="space-y-1.5 pt-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-semibold text-slate-100 text-xs">
                                {ob.actor}
                              </span>
                              {ob.counterparty && (
                                <span className="text-[11px] text-slate-400">
                                  &rarr; {ob.counterparty}
                                </span>
                              )}
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-400 border border-slate-700">
                                {ob.category}
                              </span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-400 border border-slate-700">
                                {ob.modality}
                              </span>
                            </div>

                            <p className="text-xs text-slate-200 font-medium">
                              {ob.action} {ob.object ? ob.object : ''}
                            </p>

                            {ob.deadline_rule?.raw_text && (
                              <p className="text-[11px] text-slate-400 italic">
                                &ldquo;{ob.deadline_rule.raw_text}&rdquo;
                              </p>
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
        </div>
      )}
    </div>
  );
};

export default ContractTimeline;
