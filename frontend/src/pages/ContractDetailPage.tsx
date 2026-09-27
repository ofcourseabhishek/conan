import React, { useState, useMemo, useCallback } from 'react';
import { useParams, Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useContractAnalysis } from '../hooks/useContract';
import { useDeleteContract, useReviewObligation, useSetObligationStatus } from '../hooks/useObligations';
import { ContractTimeline } from '../components/ContractTimeline';
import { ContractDependencyGraph } from '../components/ContractDependencyGraph';
import { ObligationRiskSection } from '../components/ObligationRiskSection';
import { ConflictPanel } from '../components/ConflictPanel';
import { ContractExportDropdown } from '../components/ContractExportDropdown';
import type {
  ObligationOut,
  ObligationPatch,
  Party,
  RiskBand,
  ObligationStatus,
  ReviewState,
  Modality,
  Category,
} from '../types/api';

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
      return 'bg-rose-950/70 text-rose-300 border-rose-800';
    case 'high':
      return 'bg-amber-950/70 text-amber-300 border-amber-800';
    case 'medium':
      return 'bg-yellow-950/70 text-yellow-300 border-yellow-800';
    case 'low':
      return 'bg-emerald-950/70 text-emerald-300 border-emerald-800';
    default:
      return 'bg-slate-800 text-slate-300 border-slate-700';
  }
}

function getReviewStateBadgeClass(state: ReviewState): string {
  switch (state) {
    case 'confirmed':
      return 'bg-emerald-950/60 text-emerald-300 border-emerald-800';
    case 'edited':
      return 'bg-sky-950/60 text-sky-300 border-sky-800';
    case 'rejected':
      return 'bg-rose-950/60 text-rose-300 border-rose-800';
    case 'proposed':
    default:
      return 'bg-slate-800 text-slate-400 border-slate-700';
  }
}

function getStatusBadgeClass(status: ObligationStatus): string {
  switch (status) {
    case 'done':
      return 'bg-emerald-950/60 text-emerald-300 border-emerald-800';
    case 'blocked':
      return 'bg-rose-950/60 text-rose-300 border-rose-800';
    case 'waived':
      return 'bg-slate-800 text-slate-400 border-slate-700';
    case 'open':
    default:
      return 'bg-blue-950/60 text-blue-300 border-blue-800';
  }
}

function getModalityBadgeClass(modality: Modality): string {
  switch (modality) {
    case 'must':
      return 'bg-sky-950/60 text-sky-300 border-sky-800';
    case 'must_not':
      return 'bg-rose-950/60 text-rose-300 border-rose-800';
    case 'may':
      return 'bg-slate-800 text-slate-400 border-slate-700';
  }
}

export const ContractDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const contractId = id?.trim();
  const location = useLocation();
  const navigate = useNavigate();
  const requestedView = location.pathname.split('/')[3] || 'overview';
  const activeView = requestedView === 'conflicts' || !['overview', 'obligations', 'timeline', 'dependencies', 'risk'].includes(requestedView)
    ? (requestedView === 'conflicts' ? 'risk' : 'overview')
    : requestedView;

  const [searchParams] = useSearchParams();
  const isOffline = searchParams.get('offline') === '1' || contractId === 'demo';

  const {
    data: analysis,
    isLoading,
    isError,
    error,
    refetch,
  } = useContractAnalysis(contractId, isOffline);

  // Table filtering states
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedObligation, setSelectedObligation] = useState<ObligationOut | null>(null);
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [riskBandFilter, setRiskBandFilter] = useState('ALL');
  const [reviewStateFilter, setReviewStateFilter] = useState('ALL');

  // Review Drawer state (separate from the Evidence/Source Inspection Drawer)
  const [reviewDrawerObligation, setReviewDrawerObligation] = useState<ObligationOut | null>(null);
  const [reviewMode, setReviewMode] = useState<'view' | 'edit'>('view');
  const [reviewNote, setReviewNote] = useState('');
  const [editFields, setEditFields] = useState<ObligationPatch>({});
  const [reviewError, setReviewError] = useState<string | null>(null);

  // Mutation hooks
  const reviewMutation = useReviewObligation();
  const statusMutation = useSetObligationStatus();
  const deleteMutation = useDeleteContract();
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const openReviewDrawer = useCallback((ob: ObligationOut) => {
    setReviewDrawerObligation(ob);
    setReviewMode('view');
    setReviewNote('');
    setEditFields({});
    setReviewError(null);
    reviewMutation.reset();
    statusMutation.reset();
  }, [reviewMutation, statusMutation]);

  const closeReviewDrawer = useCallback(() => {
    setReviewDrawerObligation(null);
    setReviewMode('view');
    setReviewNote('');
    setEditFields({});
    setReviewError(null);
  }, []);

  const handleConfirm = useCallback(() => {
    if (!reviewDrawerObligation || isOffline) return;
    setReviewError(null);
    reviewMutation.mutate(
      {
        contractId: contractId!,
        obligationId: reviewDrawerObligation.id,
        body: { action: 'confirm', note: reviewNote || undefined },
      },
      {
        onSuccess: () => {
          closeReviewDrawer();
          refetch();
        },
        onError: (err) => setReviewError(err.message),
      }
    );
  }, [contractId, reviewDrawerObligation, reviewNote, reviewMutation, closeReviewDrawer, refetch, isOffline]);

  const handleReject = useCallback(() => {
    if (!reviewDrawerObligation || isOffline) return;
    setReviewError(null);
    reviewMutation.mutate(
      {
        contractId: contractId!,
        obligationId: reviewDrawerObligation.id,
        body: { action: 'reject', note: reviewNote || undefined },
      },
      {
        onSuccess: () => {
          closeReviewDrawer();
          refetch();
        },
        onError: (err) => setReviewError(err.message),
      }
    );
  }, [contractId, reviewDrawerObligation, reviewNote, reviewMutation, closeReviewDrawer, refetch, isOffline]);

  const handleStartEdit = useCallback(() => {
    if (!reviewDrawerObligation || isOffline) return;
    setReviewMode('edit');
    setEditFields({
      actor: reviewDrawerObligation.actor,
      counterparty: reviewDrawerObligation.counterparty ?? '',
      action: reviewDrawerObligation.action,
      object: reviewDrawerObligation.object ?? '',
      modality: reviewDrawerObligation.modality,
      category: reviewDrawerObligation.category,
    });
  }, [reviewDrawerObligation, isOffline]);

  const handleSaveEdit = useCallback(() => {
    if (!reviewDrawerObligation || isOffline) return;
    setReviewError(null);
    // Build a clean patch with only changed fields
    const patch: ObligationPatch = {};
    if (editFields.actor !== undefined && editFields.actor !== reviewDrawerObligation.actor) patch.actor = editFields.actor;
    if (editFields.counterparty !== undefined && editFields.counterparty !== (reviewDrawerObligation.counterparty ?? '')) patch.counterparty = editFields.counterparty || null;
    if (editFields.action !== undefined && editFields.action !== reviewDrawerObligation.action) patch.action = editFields.action;
    if (editFields.object !== undefined && editFields.object !== (reviewDrawerObligation.object ?? '')) patch.object = editFields.object || null;
    if (editFields.modality !== undefined && editFields.modality !== reviewDrawerObligation.modality) patch.modality = editFields.modality;
    if (editFields.category !== undefined && editFields.category !== reviewDrawerObligation.category) patch.category = editFields.category;

    const hasChanges = Object.keys(patch).length > 0;

    if (!hasChanges) {
      setReviewMode('view');
      return;
    }

    reviewMutation.mutate(
      {
        contractId: contractId!,
        obligationId: reviewDrawerObligation.id,
        body: { action: 'edit', patch, note: reviewNote || undefined },
      },
      {
        onSuccess: () => {
          closeReviewDrawer();
          refetch();
        },
        onError: (err) => setReviewError(err.message),
      }
    );
  }, [contractId, reviewDrawerObligation, editFields, reviewNote, reviewMutation, closeReviewDrawer, refetch, isOffline]);

  // "Simulate blocked" (TRD §11): sets the status through the API so risk propagates downstream.
  const handleSetStatus = useCallback((status: ObligationStatus) => {
    if (!reviewDrawerObligation || isOffline) return;
    setReviewError(null);
    statusMutation.mutate(
      {
        contractId: contractId!,
        obligationId: reviewDrawerObligation.id,
        body: { status },
      },
      {
        onSuccess: () => {
          closeReviewDrawer();
          refetch();
        },
        onError: (err) => setReviewError(err.message),
      }
    );
  }, [contractId, reviewDrawerObligation, statusMutation, closeReviewDrawer, refetch, isOffline]);

  const handleDelete = useCallback(() => {
    if (!contractId || isOffline) return;
    deleteMutation.mutate(contractId, {
      onSuccess: () => navigate('/upload', { replace: true }),
    });
  }, [contractId, deleteMutation, navigate, isOffline]);

  const isMutating = reviewMutation.isPending || statusMutation.isPending;

  const CATEGORY_OPTIONS: Category[] = ['payment', 'renewal', 'termination', 'compliance', 'delivery', 'penalty', 'confidentiality', 'other'];
  const MODALITY_OPTIONS: Modality[] = ['must', 'must_not', 'may'];

  const handleClearFilters = () => {
    setSearchQuery('');
    setCategoryFilter('ALL');
    setStatusFilter('ALL');
    setRiskBandFilter('ALL');
    setReviewStateFilter('ALL');
  };

  const isFilterActive =
    searchQuery.trim() !== '' ||
    categoryFilter !== 'ALL' ||
    statusFilter !== 'ALL' ||
    riskBandFilter !== 'ALL' ||
    reviewStateFilter !== 'ALL';

  // Derived filter options from actual obligations returned by the backend
  const availableCategories = useMemo(() => {
    if (!analysis?.obligations) return [];
    const set = new Set<string>();
    analysis.obligations.forEach((o) => {
      if (o.category) set.add(o.category);
    });
    return Array.from(set).sort();
  }, [analysis?.obligations]);

  const availableStatuses = useMemo(() => {
    if (!analysis?.obligations) return [];
    const set = new Set<string>();
    analysis.obligations.forEach((o) => {
      if (o.status) set.add(o.status);
    });
    return Array.from(set).sort();
  }, [analysis?.obligations]);

  const availableRiskBands = useMemo(() => {
    if (!analysis?.obligations) return [];
    const set = new Set<string>();
    analysis.obligations.forEach((o) => {
      if (o.risk?.band) set.add(o.risk.band);
    });
    const order: Record<string, number> = {
      critical: 1,
      high: 2,
      medium: 3,
      low: 4,
    };
    return Array.from(set).sort((a, b) => (order[a] ?? 99) - (order[b] ?? 99));
  }, [analysis?.obligations]);

  const availableReviewStates = useMemo(() => {
    if (!analysis?.obligations) return [];
    const set = new Set<string>();
    analysis.obligations.forEach((o) => {
      if (o.review_state) set.add(o.review_state);
    });
    return Array.from(set).sort();
  }, [analysis?.obligations]);

  // Obligation lookup map for fast downstream/upstream context
  const obligationMap = useMemo(() => {
    const map = new Map<string, ObligationOut>();
    if (analysis?.obligations) {
      analysis.obligations.forEach((o) => {
        map.set(o.id, o);
      });
    }
    return map;
  }, [analysis?.obligations]);

  // Aggregate risk band counts directly from backend obligation.risk.band
  const riskCounts = useMemo(() => {
    const counts: Record<RiskBand, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
    };
    if (analysis?.obligations) {
      for (const ob of analysis.obligations) {
        if (ob.risk?.band && ob.risk.band in counts) {
          counts[ob.risk.band]++;
        }
      }
    }
    return counts;
  }, [analysis?.obligations]);

  // Set of obligation IDs associated with open contractual conflicts (Step 36)
  const conflictedObligationIds = useMemo(() => {
    const set = new Set<string>();
    if (analysis?.conflicts) {
      for (const c of analysis.conflicts) {
        if (c.status === 'open' && c.obligation_ids) {
          c.obligation_ids.forEach((id) => set.add(id));
        }
      }
    }
    return set;
  }, [analysis?.conflicts]);

  // Frontend-only filtered obligations
  const filteredObligations = useMemo(() => {
    if (!analysis?.obligations) return [];
    const query = searchQuery.trim().toLowerCase();

    return analysis.obligations.filter((ob: ObligationOut) => {
      // 1. Search filter across: actor, counterparty, action, object, category, evidence_quote
      if (query) {
        const matchActor = ob.actor?.toLowerCase().includes(query) ?? false;
        const matchCounterparty =
          ob.counterparty?.toLowerCase().includes(query) ?? false;
        const matchAction = ob.action?.toLowerCase().includes(query) ?? false;
        const matchObject = ob.object?.toLowerCase().includes(query) ?? false;
        const matchCategory = ob.category?.toLowerCase().includes(query) ?? false;
        const matchEvidence =
          ob.evidence_quote?.toLowerCase().includes(query) ?? false;

        if (
          !matchActor &&
          !matchCounterparty &&
          !matchAction &&
          !matchObject &&
          !matchCategory &&
          !matchEvidence
        ) {
          return false;
        }
      }

      // 2. Category filter
      if (categoryFilter !== 'ALL' && ob.category !== categoryFilter) {
        return false;
      }

      // 3. Status filter
      if (statusFilter !== 'ALL' && ob.status !== statusFilter) {
        return false;
      }

      // 4. Risk band filter
      if (riskBandFilter !== 'ALL' && ob.risk?.band !== riskBandFilter) {
        return false;
      }

      // 5. Review state filter
      if (
        reviewStateFilter !== 'ALL' &&
        ob.review_state !== reviewStateFilter
      ) {
        return false;
      }

      return true;
    });
  }, [
    analysis?.obligations,
    searchQuery,
    categoryFilter,
    statusFilter,
    riskBandFilter,
    reviewStateFilter,
  ]);

  // 1. Missing Route ID state
  if (!contractId) {
    return (
      <div className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 py-16">
        <div className="p-8 rounded-xl border border-rose-800/80 bg-rose-950/40 text-center space-y-4">
          <div className="w-12 h-12 rounded-lg bg-rose-900/60 border border-rose-700/80 flex items-center justify-center mx-auto text-rose-300">
            <svg
              className="w-6 h-6"
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
          <h2 className="text-lg font-semibold text-rose-100">
            Missing Contract Identifier
          </h2>
          <p className="text-sm text-rose-300 max-w-md mx-auto">
            No valid contract ID was found in the route. Please check the URL or upload a new contract.
          </p>
          <div className="pt-2">
            <Link
              to="/upload"
              className="inline-flex items-center px-4 py-2 rounded-md bg-slate-100 hover:bg-white text-slate-950 font-semibold text-xs transition-colors"
            >
              Go to Upload
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // 2. Loading state with Conan branding
  if (isLoading) {
    return (
      <div className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 py-20 flex flex-col items-center justify-center text-center space-y-4">
        <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-300 shadow-lg">
          <div className="w-6 h-6 border-2 border-slate-600 border-t-white rounded-full animate-spin" />
        </div>
        <div className="space-y-1">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
            Conan Intelligence
          </span>
          <h2 className="text-lg font-semibold text-white">
            Loading Contract Analysis...
          </h2>
          <p className="text-xs text-slate-400 max-w-sm">
            Retrieving verified obligations, dependency links, and risk scores.
          </p>
        </div>
      </div>
    );
  }

  // 3. Error state with recovery actions
  if (isError || !analysis) {
    return (
      <div className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 py-16">
        <div className="p-6 rounded-xl border border-rose-800/80 bg-rose-950/40 space-y-4">
          <div className="flex items-start space-x-3">
            <div className="w-8 h-8 rounded-lg bg-rose-900/60 border border-rose-700/80 flex items-center justify-center shrink-0 text-rose-300">
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
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-rose-100">
                Failed to Load Contract Analysis
              </h2>
              <p className="text-xs text-rose-200">
                {error?.message || 'Could not retrieve analysis data for this contract from the backend.'}
              </p>
              <p className="text-[11px] text-slate-400 pt-1 font-mono">
                Contract ID: <span className="text-slate-300">{contractId}</span>
              </p>
            </div>
          </div>

          <div className="pt-3 border-t border-rose-900/60 flex items-center space-x-3">
            <button
              type="button"
              onClick={() => refetch()}
              className="px-3.5 py-1.5 rounded bg-rose-900/80 hover:bg-rose-900 text-xs font-medium text-white transition-colors"
            >
              Retry
            </button>
            <Link
              to="/upload"
              className="px-3.5 py-1.5 rounded bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition-colors"
            >
              Back to Upload
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // 4. Successful state: extract data
  const { contract, stats, obligations, edges, events, conflicts, clauses, as_of, disclaimer } = analysis;

  return (
    <div className="contract-app min-h-screen flex-1">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col lg:flex-row">
        <aside className="contract-sidebar border-b border-slate-200 bg-white lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:shrink-0 lg:border-b-0 lg:border-r">
          <div className="flex items-center gap-3 px-5 py-4 lg:border-b lg:border-slate-200 lg:px-6 lg:py-5">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-sky-200 bg-sky-50 text-sky-700">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="M12 3v18M5 7h14M7 7l-4 9h8L7 7Zm10 0-4 9h8l-4-9ZM5 21h14" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </span>
            <div className="min-w-0"><p className="text-sm font-semibold tracking-tight text-slate-900">Conan</p><p className="text-xs text-slate-500">Contract workspace</p></div>
          </div>
          <nav aria-label="Contract sections" className="flex flex-wrap gap-1 px-3 py-2 lg:block lg:space-y-1 lg:px-3 lg:py-5">
            {[
              ['Overview', ''],
              ['Obligations', '/obligations'],
              ['Timeline', '/timeline'],
              ['Dependencies', '/dependencies'],
              ['Risk & Conflicts', '/risk'],
            ].map(([label, path]) => {
              const selected = (path === '' && activeView === 'overview') || path.slice(1) === activeView || (path === '/risk' && activeView === 'risk');
              return (
                <Link
                  key={label}
                  to={`/contracts/${contractId}${path}${location.search}`}
                  aria-current={selected ? 'page' : undefined}
                  className={`inline-flex shrink-0 items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-colors lg:flex ${selected ? 'bg-sky-50 text-sky-800 ring-1 ring-inset ring-sky-200' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'}`}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
          <div className="hidden border-t border-slate-200 px-6 py-4 text-xs text-slate-500 lg:block">
            <span className="mb-2 block font-medium uppercase tracking-wide text-slate-400">Current contract</span>
            <span className="block truncate font-medium text-slate-700" title={contract.name}>{contract.name || 'Untitled Contract'}</span>
            <span className="mt-1 block">{isOffline ? 'Offline demo · Read-only' : 'Analysis workspace'}</span>
          </div>
        </aside>
        <main className="min-w-0 flex-1">
    <div className="mx-auto w-full max-w-7xl space-y-7 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      {/* Clean Navigation Row: Back to Upload on left, Pipeline / Version on right */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
        <Link
          to="/upload"
          className="inline-flex items-center gap-2 text-xs font-medium text-slate-400 hover:text-white transition-colors group"
        >
          <svg
            className="w-4 h-4 text-slate-500 group-hover:text-slate-300 transition-transform group-hover:-translate-x-0.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span>Back to Upload</span>
        </Link>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono font-medium text-slate-400 bg-slate-900 border border-slate-800 shadow-sm">
            Pipeline {contract.pipeline_version}
          </span>
        </div>
      </div>

      {/* Clear Offline Demo / Read-Only Banner */}
      {isOffline && (
        <div className="p-4 sm:p-5 rounded-xl border border-amber-500/40 bg-gradient-to-r from-amber-950/70 via-amber-900/30 to-amber-950/70 text-amber-200 shadow-lg shadow-amber-950/30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-start sm:items-center gap-3.5">
            <div className="w-9 h-9 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center shrink-0 text-amber-400 mt-0.5 sm:mt-0">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="space-y-0.5">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-amber-100 text-sm tracking-tight">
                  Offline Demo Mode (Read-Only)
                </h3>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                </span>
              </div>
              <p className="text-xs text-amber-300/80">
                Viewing bundled local contract data. Modifications, review submissions, and live exports are restricted.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
            <span className="px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold tracking-wider uppercase bg-amber-900/60 text-amber-300 border border-amber-700/80">
              Bundled Fixture
            </span>
          </div>
        </div>
      )}

      {/* Contract Header */}
      <div className="p-6 sm:p-7 rounded-2xl border border-slate-800 bg-slate-900/90 shadow-xl space-y-6">
        <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
          <div className="space-y-4 flex-1 min-w-0">
            {/* Title & Status Badges */}
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="min-w-0 flex-1 text-2xl sm:text-3xl font-extrabold tracking-tight text-white break-words">
                  {contract.name || 'Untitled Contract'}
                </h1>
                <div className="flex items-center gap-2 shrink-0">
                  {contract.is_sample && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-purple-950/80 text-purple-300 border border-purple-700/80 shadow-sm">
                      Sample Contract
                    </span>
                  )}
                  {isOffline && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-amber-950/80 text-amber-300 border border-amber-700/80 shadow-sm">
                      Offline Demo
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Separate Metadata Chips: Source File, Contract ID, Page Count, Analyzed Date */}
            <div className="flex flex-wrap items-center gap-2.5">
              {contract.filename && (
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/80 text-xs text-slate-300 shadow-sm">
                  <svg className="w-3.5 h-3.5 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span className="text-slate-400 text-[10px] uppercase font-semibold tracking-wider">Source</span>
                  <span className="font-mono text-slate-200 truncate max-w-[200px] sm:max-w-xs" title={contract.filename}>
                    {contract.filename}
                  </span>
                </div>
              )}

              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/80 text-xs text-slate-300 shadow-sm">
                <svg className="w-3.5 h-3.5 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" />
                </svg>
                <span className="text-slate-400 text-[10px] uppercase font-semibold tracking-wider">ID</span>
                <span className="min-w-0 max-w-[180px] truncate font-mono text-slate-200" title={contract.id}>{contract.id}</span>
              </div>

              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/80 text-xs text-slate-300 shadow-sm">
                <svg className="w-3.5 h-3.5 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
                <span className="text-slate-400 text-[10px] uppercase font-semibold tracking-wider">Pages</span>
                <span className="font-medium text-slate-200">{contract.page_count}</span>
              </div>

              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/80 text-xs text-slate-300 shadow-sm">
                <svg className="w-3.5 h-3.5 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <span className="text-slate-400 text-[10px] uppercase font-semibold tracking-wider">Analyzed</span>
                <span className="font-medium text-slate-200">{formatDate(as_of)}</span>
              </div>
            </div>
          </div>

          {/* Export and Upload Actions: Properly Aligned */}
          <div className="flex items-center gap-3 shrink-0 self-start lg:self-auto pt-1 lg:pt-0">
            <ContractExportDropdown
              contractId={contract.id}
              contractName={contract.name}
              isOffline={isOffline}
            />
            <Link
              to="/upload"
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-200 hover:text-white transition-colors shrink-0 shadow-sm"
            >
              <svg className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>Upload Contract</span>
            </Link>
            {!isOffline && (
              confirmingDelete ? (
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={handleDelete}
                    disabled={deleteMutation.isPending}
                    className="px-3 py-1.5 rounded-md bg-rose-800 hover:bg-rose-700 text-xs font-semibold text-white transition-colors disabled:opacity-50"
                  >
                    {deleteMutation.isPending ? 'Deleting...' : 'Delete permanently'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setConfirmingDelete(false); deleteMutation.reset(); }}
                    disabled={deleteMutation.isPending}
                    className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-300 transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(true)}
                  className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-rose-900/70 border border-slate-700 hover:border-rose-800 text-xs font-medium text-slate-300 hover:text-rose-100 transition-colors shrink-0"
                >
                  Delete
                </button>
              )
            )}
          </div>
          {deleteMutation.isError && (
            <p role="alert" className="text-xs text-rose-300">Delete failed: {deleteMutation.error.message}</p>
          )}
        </div>

        {/* Responsive Customer / Supplier Party Cards */}
        <div className="pt-5 border-t border-slate-800/90 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold">
              Identified Contract Parties
            </span>
            {contract.parties && contract.parties.length > 0 && (
              <span className="text-[11px] font-mono text-slate-500">
                {contract.parties.length} {contract.parties.length === 1 ? 'party' : 'parties'} detected
              </span>
            )}
          </div>
          {contract.parties && contract.parties.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {contract.parties.map((party: Party, idx: number) => {
                const roleLower = party.role?.toLowerCase() || '';
                const isCustomer = roleLower.includes('customer') || roleLower.includes('client') || roleLower.includes('buyer');
                const isSupplier = roleLower.includes('supplier') || roleLower.includes('vendor') || roleLower.includes('seller') || roleLower.includes('provider');

                const roleBadgeClass = isCustomer
                  ? 'bg-blue-950/70 text-blue-300 border-blue-800/80'
                  : isSupplier
                  ? 'bg-emerald-950/70 text-emerald-300 border-emerald-800/80'
                  : 'bg-slate-800 text-slate-300 border-slate-700';

                return (
                  <div
                    key={idx}
                    className="min-w-0 p-3.5 rounded-xl bg-slate-800/50 border border-slate-700/80 hover:border-slate-600 transition-colors flex items-start gap-3 shadow-sm"
                  >
                    <div
                      className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border ${
                        isCustomer
                          ? 'bg-blue-900/30 border-blue-700/50 text-blue-400'
                          : isSupplier
                          ? 'bg-emerald-900/30 border-emerald-700/50 text-emerald-400'
                          : 'bg-slate-800 border-slate-700 text-slate-400'
                      }`}
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                        />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center justify-between gap-x-1.5 gap-y-1">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                          {party.role ? party.role : 'Party'}
                        </span>
                        {party.role && (
                          <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider border font-medium ${roleBadgeClass}`}>
                            {party.role}
                          </span>
                        )}
                      </div>
                      <p className="text-sm font-semibold text-white truncate" title={party.name}>
                        {party.name}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-slate-500 italic bg-slate-800/30 p-3.5 rounded-lg border border-slate-800/80">
              No parties identified in this contract.
            </p>
          )}
        </div>
      </div>

      {/* Summary Statistics: Responsive Grid with Five Metrics */}
      {activeView === 'overview' && (stats ? (
        <div className="space-y-4">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Contract at a glance</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">Portfolio summary</h2>
            </div>
            <span className="hidden sm:inline text-xs text-slate-500">Live from this contract analysis</span>
          </div>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            <Link to={`/contracts/${contractId}/obligations${location.search}`} className="overview-metric group border-l-4 border-l-sky-500">
              <span className="overview-metric-label">Obligations</span>
              <span className="overview-metric-value">{stats.obligations}</span>
              <span className="overview-metric-note">Extracted commitments <span aria-hidden="true">→</span></span>
            </Link>
            <Link to={`/contracts/${contractId}/timeline${location.search}`} className="overview-metric group border-l-4 border-l-amber-400">
              <span className="overview-metric-label">Awaiting dates</span>
              <span className="overview-metric-value">{stats.unresolved_dates}</span>
              <span className="overview-metric-note">Unresolved deadlines <span aria-hidden="true">→</span></span>
            </Link>
            <Link to={`/contracts/${contractId}/risk${location.search}`} className="overview-metric group border-l-4 border-l-rose-400">
              <span className="overview-metric-label">Open conflicts</span>
              <span className="overview-metric-value">{conflicts.filter((conflict) => conflict.status === 'open').length}</span>
              <span className="overview-metric-note">Potential inconsistencies <span aria-hidden="true">→</span></span>
            </Link>
            <Link to={`/contracts/${contractId}/dependencies${location.search}`} className="overview-metric group border-l-4 border-l-indigo-400">
              <span className="overview-metric-label">Dependencies</span>
              <span className="overview-metric-value">{edges.length}</span>
              <span className="overview-metric-note">Linked obligations <span aria-hidden="true">→</span></span>
            </Link>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
            <span><strong className="font-semibold text-slate-900">{stats.clauses}</strong> clauses analyzed</span>
            <span><strong className="font-semibold text-slate-900">{stats.needs_review}</strong> obligations need review</span>
            <span><strong className="font-semibold text-slate-900">{stats.clauses_without_obligations}</strong> clauses without obligations</span>
          </div>

          {/* Stats Warnings if any */}
          {stats.warnings && stats.warnings.length > 0 && (
            <div className="p-3.5 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800 space-y-1">
              <span className="font-semibold block text-amber-900">
                Analysis Warnings ({stats.warnings.length})
              </span>
              <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                {stats.warnings.map((w: string, idx: number) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="p-4 rounded-lg bg-slate-900/40 border border-slate-800 text-xs text-slate-500 italic">
          No statistics available for this analysis.
        </div>
      ))}

      {/* Contract Risk Overview (Step 35) */}
      {(activeView === 'overview' || activeView === 'risk') && <div className="p-5 rounded-xl border border-slate-200 bg-white space-y-3.5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-rose-950/60 border border-rose-800/80 flex items-center justify-center text-rose-300 shrink-0">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">Risk Overview</h2>
              <p className="text-xs text-slate-400">
                Operational exposure and attention priority breakdown
              </p>
            </div>
          </div>
          <span className="px-2.5 py-1 rounded text-[11px] font-mono bg-slate-800 text-slate-400 border border-slate-700 italic self-start sm:self-auto">
            Attention priority, not probability of breach
          </span>
        </div>

        {/* 4 Risk Band Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {/* Critical */}
          <button
            type="button"
            onClick={() => { setRiskBandFilter(riskBandFilter === 'critical' ? 'ALL' : 'critical'); navigate(`/contracts/${contractId}/obligations${location.search}`); }}
            className={`p-3 rounded-lg border text-left transition-all ${
              riskBandFilter === 'critical'
                ? 'bg-rose-950/90 border-rose-600 ring-1 ring-rose-500'
                : 'bg-rose-950/40 border-rose-900/70 hover:bg-rose-950/60'
            }`}
          >
            <span className="text-[10px] font-mono uppercase tracking-wider text-rose-400 font-semibold block">
              Critical Risk
            </span>
            <div className="flex items-baseline justify-between mt-1">
              <p className="text-2xl font-bold font-mono text-rose-200">
                {riskCounts.critical}
              </p>
              <span className="text-[10px] text-rose-400/80 font-mono">
                {obligations.length > 0 ? Math.round((riskCounts.critical / obligations.length) * 100) : 0}%
              </span>
            </div>
          </button>

          {/* High */}
          <button
            type="button"
            onClick={() => { setRiskBandFilter(riskBandFilter === 'high' ? 'ALL' : 'high'); navigate(`/contracts/${contractId}/obligations${location.search}`); }}
            className={`p-3 rounded-lg border text-left transition-all ${
              riskBandFilter === 'high'
                ? 'bg-amber-950/90 border-amber-600 ring-1 ring-amber-500'
                : 'bg-amber-950/40 border-amber-900/70 hover:bg-amber-950/60'
            }`}
          >
            <span className="text-[10px] font-mono uppercase tracking-wider text-amber-400 font-semibold block">
              High Risk
            </span>
            <div className="flex items-baseline justify-between mt-1">
              <p className="text-2xl font-bold font-mono text-amber-200">
                {riskCounts.high}
              </p>
              <span className="text-[10px] text-amber-400/80 font-mono">
                {obligations.length > 0 ? Math.round((riskCounts.high / obligations.length) * 100) : 0}%
              </span>
            </div>
          </button>

          {/* Medium */}
          <button
            type="button"
            onClick={() => { setRiskBandFilter(riskBandFilter === 'medium' ? 'ALL' : 'medium'); navigate(`/contracts/${contractId}/obligations${location.search}`); }}
            className={`p-3 rounded-lg border text-left transition-all ${
              riskBandFilter === 'medium'
                ? 'bg-yellow-950/90 border-yellow-600 ring-1 ring-yellow-500'
                : 'bg-yellow-950/40 border-yellow-900/70 hover:bg-yellow-950/60'
            }`}
          >
            <span className="text-[10px] font-mono uppercase tracking-wider text-yellow-400 font-semibold block">
              Medium Risk
            </span>
            <div className="flex items-baseline justify-between mt-1">
              <p className="text-2xl font-bold font-mono text-yellow-200">
                {riskCounts.medium}
              </p>
              <span className="text-[10px] text-yellow-400/80 font-mono">
                {obligations.length > 0 ? Math.round((riskCounts.medium / obligations.length) * 100) : 0}%
              </span>
            </div>
          </button>

          {/* Low */}
          <button
            type="button"
            onClick={() => { setRiskBandFilter(riskBandFilter === 'low' ? 'ALL' : 'low'); navigate(`/contracts/${contractId}/obligations${location.search}`); }}
            className={`p-3 rounded-lg border text-left transition-all ${
              riskBandFilter === 'low'
                ? 'bg-emerald-950/90 border-emerald-600 ring-1 ring-emerald-500'
                : 'bg-emerald-950/40 border-emerald-900/70 hover:bg-emerald-950/60'
            }`}
          >
            <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold block">
              Low Risk
            </span>
            <div className="flex items-baseline justify-between mt-1">
              <p className="text-2xl font-bold font-mono text-emerald-200">
                {riskCounts.low}
              </p>
              <span className="text-[10px] text-emerald-400/80 font-mono">
                {obligations.length > 0 ? Math.round((riskCounts.low / obligations.length) * 100) : 0}%
              </span>
            </div>
          </button>
        </div>

        {/* Proportional Risk Distribution Bar */}
        {obligations.length > 0 && (
          <div className="space-y-1 pt-1">
            <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden flex">
              {riskCounts.critical > 0 && (
                <div
                  className="bg-rose-500 h-full"
                  style={{ width: `${(riskCounts.critical / obligations.length) * 100}%` }}
                  title={`Critical: ${riskCounts.critical} obligations`}
                />
              )}
              {riskCounts.high > 0 && (
                <div
                  className="bg-amber-500 h-full"
                  style={{ width: `${(riskCounts.high / obligations.length) * 100}%` }}
                  title={`High: ${riskCounts.high} obligations`}
                />
              )}
              {riskCounts.medium > 0 && (
                <div
                  className="bg-yellow-500 h-full"
                  style={{ width: `${(riskCounts.medium / obligations.length) * 100}%` }}
                  title={`Medium: ${riskCounts.medium} obligations`}
                />
              )}
              {riskCounts.low > 0 && (
                <div
                  className="bg-emerald-500 h-full"
                  style={{ width: `${(riskCounts.low / obligations.length) * 100}%` }}
                  title={`Low: ${riskCounts.low} obligations`}
                />
              )}
            </div>
          </div>
        )}
      </div>}

      {/* Contract Inconsistencies Panel (Step 36) */}
      {activeView === 'risk' && <>
        <section className="overview-card rounded-xl border border-slate-200 bg-white p-5">
          <div className="mb-4"><h2 className="text-lg font-semibold text-slate-900">Obligation risk details</h2><p className="mt-1 text-sm text-slate-500">Scores, bands, and factors supplied by the contract analysis</p></div>
          {obligations.length ? (
            <div className="space-y-2">
              {obligations.map((ob) => (
                <details key={ob.id} className="rounded-lg border border-slate-200 bg-white px-4 py-3">
                  <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="min-w-0"><span className="font-medium text-slate-800">{ob.action}{ob.object ? ` ${ob.object}` : ''}</span><span className="ml-2 text-slate-500">{ob.actor}</span></span>
                    <span className={`rounded-md border px-2 py-1 text-xs font-medium capitalize ${getRiskBadgeClass(ob.risk.band)}`}>{ob.risk.band} · {ob.risk.score}</span>
                  </summary>
                  <div className="mt-4 border-t border-slate-100 pt-4">
                    <ObligationRiskSection risk={ob.risk} obligationMap={obligationMap} />
                  </div>
                </details>
              ))}
            </div>
          ) : <p className="text-sm text-slate-500">No obligation risk details are available.</p>}
        </section>
        <ConflictPanel
        conflicts={conflicts}
        clauses={clauses}
        obligations={obligations}
        onRefresh={() => refetch()}
        onSelectObligation={(ob) => setSelectedObligation(ob)}
        isOffline={isOffline}
        />
      </>}

      {activeView === 'overview' && (
        <>
        <section className="overview-card rounded-xl border border-slate-200 bg-white p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div><h2 className="text-lg font-semibold text-slate-900">Open conflicts</h2><p className="mt-1 text-sm text-slate-500">Potential inconsistencies flagged for review</p></div>
            <Link to={`/contracts/${contractId}/risk${location.search}`} className="shrink-0 text-sm font-medium text-sky-700 hover:text-sky-900">Review all</Link>
          </div>
          {conflicts.some((conflict) => conflict.status === 'open') ? (
            <ul className="divide-y divide-slate-100">
              {conflicts.filter((conflict) => conflict.status === 'open').slice(0, 3).map((conflict) => (
                <li key={conflict.id} className="py-3">
                  <p className="text-sm font-medium text-slate-800">{conflict.description}</p>
                  <p className="mt-1 text-xs text-slate-500">{conflict.kind.replace(/_/g, ' ')} · {conflict.source === 'llm' ? 'AI flagged' : 'Rule detected'}</p>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-slate-500">No open conflicts are currently flagged.</p>}
        </section>
        <div className="grid gap-4 xl:grid-cols-2">
          <section className="overview-card rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div><h2 className="text-lg font-semibold text-slate-900">Obligation snapshot</h2><p className="mt-1 text-sm text-slate-500">A quick look at extracted commitments</p></div>
              <Link to={`/contracts/${contractId}/obligations${location.search}`} className="shrink-0 text-sm font-medium text-sky-700 hover:text-sky-900">View all</Link>
            </div>
            {obligations.length ? (
              <div className="divide-y divide-slate-100">
                {obligations.slice(0, 4).map((ob) => (
                  <button key={ob.id} type="button" onClick={() => setSelectedObligation(ob)} className="flex w-full items-start justify-between gap-4 py-3 text-left hover:bg-slate-50">
                    <span className="min-w-0"><span className="block truncate text-sm font-medium text-slate-800">{ob.action}{ob.object ? ` ${ob.object}` : ''}</span><span className="mt-1 block text-xs text-slate-500">{ob.actor} · {ob.category}</span></span>
                    <span className={`shrink-0 rounded-md border px-2 py-1 text-xs font-medium capitalize ${getRiskBadgeClass(ob.risk.band)}`}>{ob.risk.band}</span>
                  </button>
                ))}
              </div>
            ) : <p className="text-sm text-slate-500">No obligations were identified.</p>}
          </section>

          <section className="overview-card rounded-xl border border-slate-200 bg-white p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div><h2 className="text-lg font-semibold text-slate-900">Key events</h2><p className="mt-1 text-sm text-slate-500">Contract dates and linked milestones</p></div>
              <Link to={`/contracts/${contractId}/timeline${location.search}`} className="shrink-0 text-sm font-medium text-sky-700 hover:text-sky-900">Open timeline</Link>
            </div>
            {events.some((event) => event.date) ? (
              <ul className="space-y-3">
                {events.filter((event) => event.date).slice(0, 4).map((event) => (
                  <li key={event.key} className="flex items-center justify-between gap-4 rounded-lg border border-slate-100 bg-slate-50/70 px-3.5 py-3">
                    <span className="min-w-0 truncate text-sm font-medium text-slate-800">{event.label}</span>
                    <time className="shrink-0 text-sm tabular-nums text-slate-600">{formatDate(event.date)}</time>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-slate-500">No dated events are available yet.</p>}
          </section>
        </div>
        </>
      )}

      {/* Contract Timeline (Step 33) */}
      {activeView === 'timeline' && <ContractTimeline
        contractId={contract.id}
        events={events}
        obligations={obligations}
        edges={edges}
        onRefresh={() => refetch()}
        isOffline={isOffline}
      />}

      {/* Contract Dependency Graph (Step 34) */}
      {activeView === 'dependencies' && <ContractDependencyGraph
        contractId={contract.id}
        obligations={obligations}
        edges={edges}
        onRefresh={() => refetch()}
        onSelectObligation={(ob) => setSelectedObligation(ob)}
        onReviewObligation={(ob) => openReviewDrawer(ob)}
        isOffline={isOffline}
      />}

      {/* Obligations Section */}
      {activeView === 'obligations' && <div className="space-y-4">
        {/* Section Header with "X of Y obligations" display */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="space-y-0.5">
            <h2 className="text-lg font-semibold text-white">
              Contract Obligations
            </h2>
            <p className="text-xs text-slate-400">
              Extracted operational commitments, modalities, and risk levels
            </p>
          </div>
          <span className="px-2.5 py-1 text-xs font-mono rounded bg-slate-800 text-slate-300 border border-slate-700 self-start sm:self-auto">
            {filteredObligations.length} of {obligations.length} obligations
          </span>
        </div>

        {obligations.length === 0 ? (
          <div className="p-8 rounded-xl border border-slate-800 bg-slate-900/40 text-center space-y-2">
            <p className="text-sm font-medium text-slate-300">
              No obligations extracted
            </p>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              No operational commitments were extracted from this document, or extraction yielded zero results.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Search and Filters Bar */}
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-3">
              <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center">
                {/* Search Input */}
                <div className="relative flex-1">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
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
                        d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                      />
                    </svg>
                  </div>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by actor, counterparty, action, object, category, or evidence quote..."
                    className="w-full pl-9 pr-8 py-2 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-400 focus:border-slate-500 transition-colors"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery('')}
                      className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-slate-500 hover:text-slate-300 text-xs"
                      aria-label="Clear search input"
                    >
                      ✕
                    </button>
                  )}
                </div>

                {/* Clear Filters Button (When any filter/search is active) */}
                {isFilterActive && (
                  <button
                    type="button"
                    onClick={handleClearFilters}
                    className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition-colors whitespace-nowrap self-start md:self-auto"
                  >
                    Clear filters
                  </button>
                )}
              </div>

              {/* Dropdown Filters Row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-2 border-t border-slate-800/60">
                {/* Category Dropdown */}
                <div className="space-y-1">
                  <label className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">
                    Category
                  </label>
                  <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-400 font-mono capitalize"
                  >
                    <option value="ALL">All Categories</option>
                    {availableCategories.map((cat: string) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Status Dropdown */}
                <div className="space-y-1">
                  <label className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">
                    Status
                  </label>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-400 font-mono capitalize"
                  >
                    <option value="ALL">All Statuses</option>
                    {availableStatuses.map((st: string) => (
                      <option key={st} value={st}>
                        {st}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Risk Band Dropdown */}
                <div className="space-y-1">
                  <label className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">
                    Risk Band
                  </label>
                  <select
                    value={riskBandFilter}
                    onChange={(e) => setRiskBandFilter(e.target.value)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-400 font-mono capitalize"
                  >
                    <option value="ALL">All Risk Bands</option>
                    {availableRiskBands.map((band: string) => (
                      <option key={band} value={band}>
                        {band}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Review State Dropdown */}
                <div className="space-y-1">
                  <label className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">
                    Review State
                  </label>
                  <select
                    value={reviewStateFilter}
                    onChange={(e) => setReviewStateFilter(e.target.value)}
                    className="w-full px-2.5 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-400 font-mono capitalize"
                  >
                    <option value="ALL">All Review States</option>
                    {availableReviewStates.map((rs: string) => (
                      <option key={rs} value={rs}>
                        {rs}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Filtered Empty State vs Table */}
            {filteredObligations.length === 0 ? (
              <div className="p-8 rounded-xl border border-slate-800 bg-slate-900/40 text-center space-y-3">
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
                      d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
                    />
                  </svg>
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-medium text-slate-200">
                    No obligations match the current filters.
                  </p>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    Try adjusting your search keywords or reset the dropdown filters to show matching obligations.
                  </p>
                </div>
                <div>
                  <button
                    type="button"
                    onClick={handleClearFilters}
                    className="px-3.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-200 hover:text-white transition-colors"
                  >
                    Clear filters
                  </button>
                </div>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-850 text-slate-400 font-mono uppercase text-[11px] border-b border-slate-800">
                    <tr>
                      <th scope="col" className="px-4 py-3 min-w-[140px]">Actor</th>
                      <th scope="col" className="px-4 py-3 min-w-[200px]">Action & Object</th>
                      <th scope="col" className="px-4 py-3 min-w-[120px]">Category & Modality</th>
                      <th scope="col" className="px-4 py-3 min-w-[120px]">Due Date</th>
                      <th scope="col" className="px-4 py-3 min-w-[110px]">Risk</th>
                      <th scope="col" className="px-4 py-3 min-w-[100px]">Review</th>
                      <th scope="col" className="px-4 py-3 min-w-[90px]">Status</th>
                      <th scope="col" className="px-4 py-3 min-w-[200px]">Evidence</th>
                      <th scope="col" className="px-4 py-3 min-w-[80px]">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80">
                    {filteredObligations.map((ob: ObligationOut) => (
                      <tr key={ob.id} className="hover:bg-slate-800/40 transition-colors">
                        {/* Actor */}
                        <td
                            className="px-4 py-3.5 align-top cursor-pointer hover:bg-slate-800/40 transition-colors"
                            onClick={() => setSelectedObligation(ob)}
                          >
                          <span className="font-semibold text-slate-200 block">
                            {ob.actor || '—'}
                          </span>
                          {ob.counterparty && (
                            <span className="text-[11px] text-slate-400 block">
                              to {ob.counterparty}
                            </span>
                          )}
                          {conflictedObligationIds.has(ob.id) && (
                            <div className="mt-1.5">
                              <span
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-950/90 text-amber-300 border border-amber-800/80 shadow-xs"
                                title="Potential contractual inconsistency detected involving this obligation"
                              >
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                                Inconsistency Detected
                              </span>
                            </div>
                          )}
                        </td>

                        {/* Action & Object */}
                        <td className="px-4 py-3.5 align-top">
                          <p className="text-slate-100 font-medium leading-relaxed">
                            {ob.action}
                            {ob.object ? ` ${ob.object}` : ''}
                          </p>
                          {ob.is_conditional && ob.condition_text && (
                            <p className="text-[11px] text-slate-400 mt-1 italic">
                              Condition: {ob.condition_text}
                            </p>
                          )}
                        </td>

                        {/* Category & Modality */}
                        <td className="px-4 py-3.5 align-top space-y-1">
                          <div>
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-300 border border-slate-700">
                              {ob.category}
                            </span>
                          </div>
                          <div>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase border ${getModalityBadgeClass(
                                ob.modality
                              )}`}
                            >
                              {ob.modality}
                            </span>
                          </div>
                        </td>

                        {/* Due Date & Resolution */}
                        <td className="px-4 py-3.5 align-top space-y-0.5 font-mono">
                          <span className="text-slate-200 block text-[11px]">
                            {formatDate(ob.due_date)}
                          </span>
                          {ob.resolution_status && ob.resolution_status !== 'resolved' && (
                            <span className="text-[10px] text-amber-400/90 block capitalize">
                              {ob.resolution_status.replace(/_/g, ' ')}
                            </span>
                          )}
                        </td>

                        {/* Risk */}
                        <td className="px-4 py-3.5 align-top">
                          <div className="space-y-1">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono uppercase font-medium border ${getRiskBadgeClass(
                                ob.risk.band
                              )}`}
                            >
                              {ob.risk.band} ({ob.risk.score})
                            </span>
                            {ob.risk.label && (
                              <span className="text-[11px] text-slate-400 block leading-tight">
                                {ob.risk.label}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Review State */}
                        <td className="px-4 py-3.5 align-top space-y-1">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono capitalize border ${getReviewStateBadgeClass(
                              ob.review_state
                            )}`}
                          >
                            {ob.review_state}
                          </span>
                          {ob.needs_review && (
                            <span className="block text-[10px] text-amber-400 font-medium">
                              Review Needed
                            </span>
                          )}
                        </td>

                        {/* Status */}
                        <td className="px-4 py-3.5 align-top">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono capitalize border ${getStatusBadgeClass(
                              ob.status
                            )}`}
                          >
                            {ob.status}
                          </span>
                        </td>

                        {/* Evidence Indicator */}
                        <td className="px-4 py-3.5 align-top">
                          {ob.evidence_quote ? (
                            <div className="space-y-1 max-w-xs">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span
                                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                                    ob.evidence_status === 'verified'
                                      ? 'bg-emerald-950/50 text-emerald-300 border-emerald-800/80'
                                      : 'bg-amber-950/50 text-amber-300 border-amber-800/80'
                                  }`}
                                >
                                  {ob.evidence_status === 'verified'
                                    ? '✓ Verified'
                                    : '⚠ Unverified'}
                                </span>
                                <span className="text-[11px] font-mono text-slate-400">
                                  p. {ob.page_start}
                                  {ob.page_end && ob.page_end !== ob.page_start
                                    ? `–${ob.page_end}`
                                    : ''}
                                  {ob.page_approx ? ' (approx)' : ''}
                                </span>
                              </div>
                              <p
                                className="text-xs text-slate-400 italic line-clamp-2"
                                title={ob.evidence_quote}
                              >
                                &ldquo;{ob.evidence_quote}&rdquo;
                              </p>
                            </div>
                          ) : (
                            <span className="text-xs text-slate-500 italic">
                              No quote linked
                            </span>
                          )}
                        </td>

                        {/* Review Action */}
                        <td className="px-4 py-3.5 align-top">
                          <button
                            type="button"
                            onClick={() => !isOffline && openReviewDrawer(ob)}
                            disabled={isOffline}
                            title={isOffline ? 'Not available in offline demo' : 'Review obligation'}
                            className="px-2.5 py-1 rounded-md bg-indigo-950/60 hover:bg-indigo-900/70 border border-indigo-800/80 text-[11px] font-medium text-indigo-300 hover:text-indigo-200 transition-colors whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            Review
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>}

      {/* Backend Legal/Operational Disclaimer */}
      {disclaimer && (
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400 space-y-1">
          <span className="font-semibold text-slate-300 block">Notice</span>
          <p className="leading-relaxed">{disclaimer}</p>
        </div>
      )}
            {/* Evidence / Source Inspection Drawer */}
      {selectedObligation && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <button
            type="button"
            aria-label="Close source inspection"
            className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm"
            onClick={() => setSelectedObligation(null)}
          />

          {/* Drawer */}
          <aside
            className="relative z-10 h-full w-full max-w-xl overflow-y-auto border-l border-slate-700 bg-slate-950 shadow-2xl"
            aria-label="Source Inspection"
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800 bg-slate-950/95 px-6 py-4 backdrop-blur">
              <div>
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
                  Evidence &amp; provenance
                </p>
                <h2 className="mt-1 text-lg font-semibold text-white">
                  Source Inspection
                </h2>
              </div>

              <button
                type="button"
                aria-label="Close source inspection"
                onClick={() => setSelectedObligation(null)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="space-y-6 p-6">
              {/* Obligation details */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Obligation
                </h3>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] uppercase text-slate-500">Actor</p>
                    <p className="mt-1 text-sm text-slate-200">
                      {selectedObligation.actor || '—'}
                    </p>
                  </div>

                  <div>
                    <p className="text-[10px] uppercase text-slate-500">
                      Counterparty
                    </p>
                    <p className="mt-1 text-sm text-slate-200">
                      {selectedObligation.counterparty || 'None specified'}
                    </p>
                  </div>

                  <div>
                    <p className="text-[10px] uppercase text-slate-500">Action</p>
                    <p className="mt-1 text-sm text-slate-200">
                      {selectedObligation.action || '—'}
                    </p>
                  </div>

                  <div>
                    <p className="text-[10px] uppercase text-slate-500">Object</p>
                    <p className="mt-1 text-sm text-slate-200">
                      {selectedObligation.object || '—'}
                    </p>
                  </div>

                  <div>
                    <p className="text-[10px] uppercase text-slate-500">Modality</p>
                    <p className="mt-1 text-sm text-slate-200">
                      {selectedObligation.modality || '—'}
                    </p>
                  </div>

                  <div>
                    <p className="text-[10px] uppercase text-slate-500">Category</p>
                    <p className="mt-1 text-sm text-slate-200">
                      {selectedObligation.category || '—'}
                    </p>
                  </div>
                </div>
              </section>

              {/* Evidence */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Evidence
                </h3>

                {selectedObligation.evidence_quote ? (
                  <blockquote className="rounded-xl border border-slate-700 bg-slate-900/70 p-4 text-sm leading-relaxed text-slate-200">
                    “{selectedObligation.evidence_quote}”
                  </blockquote>
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-4 text-sm italic text-slate-500">
                    No Evidence Quote Available
                  </div>
                )}

                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <span className="rounded-md border border-slate-700 px-2 py-1 text-slate-400">
                    Status: {selectedObligation.evidence_status || '—'}
                  </span>

                  {selectedObligation.page_start != null && (
                    <span className="rounded-md border border-slate-700 px-2 py-1 text-slate-400">
                      Page: {selectedObligation.page_start}
                      {selectedObligation.page_end &&
                      selectedObligation.page_end !== selectedObligation.page_start
                        ? `–${selectedObligation.page_end}`
                        : ''}
                      {selectedObligation.page_approx ? ' (approx)' : ''}
                    </span>
                  )}
                </div>
              </section>

              {/* Confidence */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Confidence &amp; provenance
                </h3>

                <div className="space-y-3">
                  {selectedObligation.evidence_score != null && (
                    <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                      <span className="text-xs text-slate-400">
                        Evidence score
                      </span>
                      <span className="text-sm font-mono text-slate-200">
                        {(selectedObligation.evidence_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}

                  {selectedObligation.llm_confidence != null && (
                    <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                      <span className="text-xs text-slate-400">
                        LLM confidence
                      </span>
                      <span className="text-sm font-mono text-slate-200">
                        {(selectedObligation.llm_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}

                  {selectedObligation.date_provenance && (
                    <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                      <p className="text-[10px] uppercase text-slate-500">
                        Date provenance
                      </p>
                      <p className="mt-1 text-xs text-slate-300">
                        {selectedObligation.date_provenance}
                      </p>
                    </div>
                  )}

                  {selectedObligation.field_provenance && (
                    <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-3">
                      <p className="mb-2 text-[10px] uppercase text-slate-500">
                        Field provenance
                      </p>

                      <div className="space-y-1.5">
                        {Object.entries(selectedObligation.field_provenance).map(
                          ([field, provenance]) => (
                            <div
                              key={field}
                              className="flex items-center justify-between gap-3"
                            >
                              <span className="text-xs text-slate-400">
                                {field}
                              </span>
                              <span className="rounded-md border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300">
                                {String(provenance)}
                              </span>
                            </div>
                          )
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </section>

              {/* Risk Assessment (Step 35) */}
              {selectedObligation.risk && (
                <ObligationRiskSection
                  risk={selectedObligation.risk}
                  obligationMap={obligationMap}
                />
              )}
            </div>
          </aside>
        </div>
      )}

      {/* Obligation Review Drawer */}
      {reviewDrawerObligation && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <button
            type="button"
            aria-label="Close review drawer"
            className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm"
            onClick={closeReviewDrawer}
          />

          {/* Drawer */}
          <aside
            className="relative z-10 h-full w-full max-w-xl overflow-y-auto border-l border-slate-700 bg-slate-950 shadow-2xl"
            aria-label="Obligation Review"
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800 bg-slate-950/95 px-6 py-4 backdrop-blur">
              <div>
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
                  Obligation review
                </p>
                <h2 className="mt-1 text-lg font-semibold text-white">
                  {reviewMode === 'edit' ? 'Edit Fields' : 'Review Obligation'}
                </h2>
              </div>

              <button
                type="button"
                aria-label="Close review drawer"
                onClick={closeReviewDrawer}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="space-y-6 p-6">
              {/* Error Banner */}
              {reviewError && (
                <div className="rounded-lg border border-rose-800/80 bg-rose-950/40 px-4 py-3 text-xs text-rose-300">
                  <span className="font-semibold">Error:</span> {reviewError}
                </div>
              )}

              {/* Obligation Details Section */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Obligation Fields
                </h3>

                {reviewMode === 'edit' ? (
                  <div className="space-y-3">
                    <div>
                      <label className="text-[10px] uppercase text-slate-500 block mb-1">Actor</label>
                      <input
                        type="text"
                        value={editFields.actor ?? ''}
                        onChange={(e) => setEditFields({ ...editFields, actor: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase text-slate-500 block mb-1">Counterparty</label>
                      <input
                        type="text"
                        value={editFields.counterparty ?? ''}
                        onChange={(e) => setEditFields({ ...editFields, counterparty: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase text-slate-500 block mb-1">Action</label>
                      <input
                        type="text"
                        value={editFields.action ?? ''}
                        onChange={(e) => setEditFields({ ...editFields, action: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase text-slate-500 block mb-1">Object</label>
                      <input
                        type="text"
                        value={editFields.object ?? ''}
                        onChange={(e) => setEditFields({ ...editFields, object: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase text-slate-500 block mb-1">Modality</label>
                      <select
                        value={editFields.modality ?? ''}
                        onChange={(e) => setEditFields({ ...editFields, modality: e.target.value as Modality })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      >
                        {MODALITY_OPTIONS.map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] uppercase text-slate-500 block mb-1">Category</label>
                      <select
                        value={editFields.category ?? ''}
                        onChange={(e) => setEditFields({ ...editFields, category: e.target.value as Category })}
                        className="w-full px-3 py-2 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      >
                        {CATEGORY_OPTIONS.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-[10px] uppercase text-slate-500">Actor</p>
                      <p className="mt-1 text-sm text-slate-200">{reviewDrawerObligation.actor || '—'}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase text-slate-500">Counterparty</p>
                      <p className="mt-1 text-sm text-slate-200">{reviewDrawerObligation.counterparty || 'None specified'}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase text-slate-500">Action</p>
                      <p className="mt-1 text-sm text-slate-200">{reviewDrawerObligation.action || '—'}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase text-slate-500">Object</p>
                      <p className="mt-1 text-sm text-slate-200">{reviewDrawerObligation.object || '—'}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase text-slate-500">Modality</p>
                      <p className="mt-1 text-sm text-slate-200">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono uppercase border ${getModalityBadgeClass(reviewDrawerObligation.modality)}`}>
                          {reviewDrawerObligation.modality}
                        </span>
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase text-slate-500">Category</p>
                      <p className="mt-1 text-sm text-slate-200">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-300 border border-slate-700">
                          {reviewDrawerObligation.category}
                        </span>
                      </p>
                    </div>
                  </div>
                )}
              </section>

              {/* Due Date & Deadline */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Due Date &amp; Deadline
                </h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                    <span className="text-xs text-slate-400">Due date</span>
                    <span className="text-sm font-mono text-slate-200">{formatDate(reviewDrawerObligation.due_date)}</span>
                  </div>
                  {reviewDrawerObligation.deadline_rule && (
                    <>
                      <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                        <span className="text-xs text-slate-400">Rule kind</span>
                        <span className="text-sm font-mono text-slate-200 capitalize">{reviewDrawerObligation.deadline_rule.kind}</span>
                      </div>
                      {reviewDrawerObligation.deadline_rule.raw_text && (
                        <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                          <p className="text-[10px] uppercase text-slate-500">Raw date text</p>
                          <p className="mt-1 text-xs text-slate-300 italic">"{reviewDrawerObligation.deadline_rule.raw_text}"</p>
                        </div>
                      )}
                    </>
                  )}
                  <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                    <span className="text-xs text-slate-400">Resolution status</span>
                    <span className="text-sm font-mono text-slate-200 capitalize">{reviewDrawerObligation.resolution_status.replace(/_/g, ' ')}</span>
                  </div>
                </div>
              </section>

              {/* Evidence */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Evidence
                </h3>

                {reviewDrawerObligation.evidence_quote ? (
                  <blockquote className="rounded-xl border border-slate-700 bg-slate-900/70 p-4 text-sm leading-relaxed text-slate-200">
                    &ldquo;{reviewDrawerObligation.evidence_quote}&rdquo;
                  </blockquote>
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-4 text-sm italic text-slate-500">
                    No evidence quote available
                  </div>
                )}

                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <span className="rounded-md border border-slate-700 px-2 py-1 text-slate-400">
                    Status: {reviewDrawerObligation.evidence_status || '—'}
                  </span>
                  {reviewDrawerObligation.page_start != null && (
                    <span className="rounded-md border border-slate-700 px-2 py-1 text-slate-400">
                      Page: {reviewDrawerObligation.page_start}
                      {reviewDrawerObligation.page_end && reviewDrawerObligation.page_end !== reviewDrawerObligation.page_start
                        ? `–${reviewDrawerObligation.page_end}`
                        : ''}
                      {reviewDrawerObligation.page_approx ? ' (approx)' : ''}
                    </span>
                  )}
                </div>
              </section>

              {/* Confidence & Scores */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Confidence &amp; Scores
                </h3>
                <div className="space-y-2">
                  {reviewDrawerObligation.evidence_score != null && (
                    <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                      <span className="text-xs text-slate-400">Evidence score</span>
                      <span className="text-sm font-mono text-slate-200">
                        {(reviewDrawerObligation.evidence_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}
                  <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                    <span className="text-xs text-slate-400">Overall confidence</span>
                    <span className="text-sm font-mono text-slate-200">
                      {(reviewDrawerObligation.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  {reviewDrawerObligation.llm_confidence != null && (
                    <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                      <span className="text-xs text-slate-400">LLM confidence</span>
                      <span className="text-sm font-mono text-slate-200">
                        {(reviewDrawerObligation.llm_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}
                </div>
              </section>

              {/* Risk Assessment (Step 35) */}
              {reviewDrawerObligation.risk && (
                <ObligationRiskSection
                  risk={reviewDrawerObligation.risk}
                  obligationMap={obligationMap}
                />
              )}

              {/* Current Review State */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Review State
                </h3>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded text-xs font-mono capitalize border ${getReviewStateBadgeClass(reviewDrawerObligation.review_state)}`}>
                    {reviewDrawerObligation.review_state}
                  </span>
                  {reviewDrawerObligation.needs_review && (
                    <span className="text-[11px] text-amber-400 font-medium">Review Needed</span>
                  )}
                </div>
              </section>

              {/* Reviewer Note */}
              <section>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Reviewer Note <span className="text-slate-600 normal-case">(optional)</span>
                </h3>
                <textarea
                  value={reviewNote}
                  onChange={(e) => setReviewNote(e.target.value)}
                  placeholder="Add an optional note for this review action..."
                  rows={3}
                  className="w-full px-3 py-2 rounded-lg bg-slate-800/90 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-400 focus:border-slate-500 resize-y"
                />
              </section>

              {/* Action Buttons */}
              <section className="border-t border-slate-800 pt-5">
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Reviewer Actions
                </h3>

                {isOffline && (
                  <div className="mb-3 p-2.5 rounded bg-amber-950/40 border border-amber-900/60 text-amber-300 text-xs">
                    Review actions are disabled in offline demo mode.
                  </div>
                )}

                {reviewMode === 'edit' ? (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleSaveEdit}
                      disabled={isOffline || isMutating}
                      title={isOffline ? 'Not available in offline demo' : undefined}
                      className="flex-1 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {reviewMutation.isPending ? 'Saving...' : 'Save Changes'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setReviewMode('view')}
                      disabled={isMutating}
                      className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-300 hover:text-white transition-colors disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={handleConfirm}
                      disabled={isOffline || isMutating}
                      title={isOffline ? 'Not available in offline demo' : undefined}
                      className="px-4 py-2 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {reviewMutation.isPending ? 'Confirming...' : '✓ Confirm'}
                    </button>
                    <button
                      type="button"
                      onClick={handleReject}
                      disabled={isOffline || isMutating}
                      title={isOffline ? 'Not available in offline demo' : undefined}
                      className="px-4 py-2 rounded-lg bg-rose-800 hover:bg-rose-700 text-white text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {reviewMutation.isPending ? 'Rejecting...' : '✕ Reject'}
                    </button>
                    <button
                      type="button"
                      onClick={handleStartEdit}
                      disabled={isOffline || isMutating}
                      title={isOffline ? 'Not available in offline demo' : undefined}
                      className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs font-semibold text-slate-200 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      ✎ Edit Fields
                    </button>
                  </div>
                )}

                {reviewMode === 'view' && (
                  <div className="mt-5 pt-4 border-t border-slate-800 space-y-2">
                    <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
                      Status: <span className="font-mono normal-case tracking-normal text-slate-300">{reviewDrawerObligation.status}</span>
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      {reviewDrawerObligation.status !== 'blocked' && (
                        <button
                          type="button"
                          onClick={() => handleSetStatus('blocked')}
                          disabled={isOffline || isMutating}
                          title={isOffline ? 'Not available in offline demo' : undefined}
                          className="px-4 py-2 rounded-lg bg-amber-800 hover:bg-amber-700 text-white text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {statusMutation.isPending ? 'Updating...' : '⚠ Simulate blocked'}
                        </button>
                      )}
                      {reviewDrawerObligation.status !== 'done' && (
                        <button
                          type="button"
                          onClick={() => handleSetStatus('done')}
                          disabled={isOffline || isMutating}
                          title={isOffline ? 'Not available in offline demo' : undefined}
                          className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs font-semibold text-slate-200 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Mark done
                        </button>
                      )}
                      {reviewDrawerObligation.status !== 'open' && (
                        <button
                          type="button"
                          onClick={() => handleSetStatus('open')}
                          disabled={isOffline || isMutating}
                          title={isOffline ? 'Not available in offline demo' : undefined}
                          className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs font-semibold text-slate-200 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Reopen
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </section>
            </div>
          </aside>
        </div>
      )}
    </div>
        </main>
      </div>
    </div>
  );
};

export default ContractDetailPage;
