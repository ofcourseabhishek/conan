import type {
  Analysis,
  ApiError,
  ConflictReviewRequest,
  EdgeReviewRequest,
  EventDateRequest,
  Health,
  JobOut,
  ObligationReviewRequest,
  ObligationStatusRequest,
  UploadResponse,
} from '../types/api';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${path}`;

  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;
    try {
      const errorBody = await response.json();
      if (errorBody && typeof errorBody === 'object') {
        const apiError = errorBody as Partial<ApiError>;
        if (apiError.message) {
          errorMessage = apiError.action
            ? `${apiError.message} (${apiError.action})`
            : apiError.message;
        } else if ('detail' in errorBody) {
          const detail = (errorBody as { detail: unknown }).detail;
          if (typeof detail === 'string') {
            errorMessage = detail;
          } else if (Array.isArray(detail)) {
            errorMessage = detail
              .map((d: { msg?: string }) => d.msg || JSON.stringify(d))
              .join('; ');
          } else {
            errorMessage = JSON.stringify(detail);
          }
        }
      }
    } catch {
      if (response.statusText) {
        errorMessage = `Request failed: ${response.statusText}`;
      }
    }
    throw new Error(errorMessage);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function uploadContract(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return request<UploadResponse>('/api/contracts', {
    method: 'POST',
    body: formData,
  });
}

export async function createSampleContract(): Promise<UploadResponse> {
  return request<UploadResponse>('/api/contracts/sample', {
    method: 'POST',
  });
}

export async function getJob(jobId: string): Promise<JobOut> {
  return request<JobOut>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export async function getContractAnalysis(contractId: string): Promise<Analysis> {
  return request<Analysis>(`/api/contracts/${encodeURIComponent(contractId)}/analysis`);
}

export async function deleteContract(contractId: string): Promise<void> {
  return request<void>(`/api/contracts/${encodeURIComponent(contractId)}`, {
    method: 'DELETE',
  });
}

// Obligation IDs (O-001…) are only unique within a contract, so these routes need contract_id.
export async function reviewObligation(
  contractId: string,
  obligationId: string,
  body: ObligationReviewRequest
): Promise<Analysis> {
  const query = `contract_id=${encodeURIComponent(contractId)}`;
  return request<Analysis>(`/api/obligations/${encodeURIComponent(obligationId)}?${query}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function setObligationStatus(
  contractId: string,
  obligationId: string,
  body: ObligationStatusRequest
): Promise<Analysis> {
  const query = `contract_id=${encodeURIComponent(contractId)}`;
  return request<Analysis>(`/api/obligations/${encodeURIComponent(obligationId)}/status?${query}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function reviewConflict(
  conflictId: string,
  body: ConflictReviewRequest
): Promise<Analysis> {
  return request<Analysis>(`/api/conflicts/${encodeURIComponent(conflictId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function patchEdge(
  edgeId: string,
  body: EdgeReviewRequest
): Promise<Analysis> {
  return request<Analysis>(`/api/edges/${encodeURIComponent(edgeId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function updateEvent(
  contractId: string,
  key: string,
  body: EventDateRequest
): Promise<Analysis> {
  return request<Analysis>(`/api/contracts/${encodeURIComponent(contractId)}/events/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

export async function getHealth(): Promise<Health> {
  return request<Health>('/api/health');
}

export function getExportUrl(contractId: string, format: 'ics' | 'csv'): string {
  return `${BASE_URL}/api/contracts/${encodeURIComponent(contractId)}/export.${format}`;
}
