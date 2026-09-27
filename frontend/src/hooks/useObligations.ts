import { useMutation, useQuery } from '@tanstack/react-query';
import {
  deleteContract,
  getHealth,
  patchEdge,
  reviewConflict,
  reviewObligation,
  setObligationStatus,
  updateEvent,
} from '../lib/api';
import type {
  Analysis,
  ConflictReviewRequest,
  EdgeReviewRequest,
  EventDateRequest,
  Health,
  ObligationReviewRequest,
  ObligationStatusRequest,
} from '../types/api';

export function useReviewObligation() {
  return useMutation<
    Analysis,
    Error,
    { contractId: string; obligationId: string; body: ObligationReviewRequest }
  >({
    mutationFn: ({ contractId, obligationId, body }) =>
      reviewObligation(contractId, obligationId, body),
  });
}

export function useSetObligationStatus() {
  return useMutation<
    Analysis,
    Error,
    { contractId: string; obligationId: string; body: ObligationStatusRequest }
  >({
    mutationFn: ({ contractId, obligationId, body }) =>
      setObligationStatus(contractId, obligationId, body),
  });
}

export function useDeleteContract() {
  return useMutation<void, Error, string>({
    mutationFn: (contractId: string) => deleteContract(contractId),
  });
}

export function useReviewConflict() {
  return useMutation<
    Analysis,
    Error,
    { conflictId: string; body: ConflictReviewRequest }
  >({
    mutationFn: ({ conflictId, body }) =>
      reviewConflict(conflictId, body),
  });
}

export function usePatchEdge() {
  return useMutation<
    Analysis,
    Error,
    { edgeId: string; body: EdgeReviewRequest }
  >({
    mutationFn: ({ edgeId, body }) => patchEdge(edgeId, body),
  });
}

export function useUpdateEvent() {
  return useMutation<
    Analysis,
    Error,
    { contractId: string; key: string; body: EventDateRequest }
  >({
    mutationFn: ({ contractId, key, body }) =>
      updateEvent(contractId, key, body),
  });
}

export function useHealth() {
  return useQuery<Health, Error>({
    queryKey: ['health'],
    queryFn: () => getHealth(),
    staleTime: 60 * 1000,
  });
}
