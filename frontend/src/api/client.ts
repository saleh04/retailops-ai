import type {
  AnalysisResponse,
  ConnectionResponse,
  ConversationDetail,
  ConversationSummary,
} from './types';

export type {
  AnalysisMetadata,
  AnalysisResponse,
  AnalysisStatus,
  ConnectionResponse,
  ConversationDetail,
  ConversationSummary,
  DescribeTableData,
  MessageRecord,
  QueryData,
  QueryStatus,
  SchemaToolData,
  SchemaToolResult,
  SQLExecutionResult,
} from './types';

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:5000').replace(
  /\/+$/,
  '',
);

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/** The backend answers a failed analysis with HTTP 500 but a full response body. */
export class AnalysisFailedError extends Error {
  readonly status = 500;
  readonly response: AnalysisResponse;

  constructor(response: AnalysisResponse) {
    super(response.error ?? 'The analysis failed.');
    this.name = 'AnalysisFailedError';
    this.response = response;
  }
}

function extractDetail(body: unknown): string | null {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
    }
  }
  return null;
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, 'Could not reach the RetailOps AI API.');
  }

  if (response.status === 204) return null;

  const raw = await response.text();
  let body: unknown = null;
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractDetail(body) ?? `The server responded with ${response.status}.`,
    );
  }

  return body;
}

export function getConnection(): Promise<ConnectionResponse> {
  return request('/api/v1/connections') as Promise<ConnectionResponse>;
}

export function createConnection(databaseUrl: string): Promise<ConnectionResponse> {
  return request('/api/v1/connections', {
    method: 'POST',
    body: JSON.stringify({ database_url: databaseUrl }),
  }) as Promise<ConnectionResponse>;
}

export function deleteConnection(): Promise<void> {
  return request('/api/v1/connections', { method: 'DELETE' }) as Promise<void>;
}

export function listConversations(connectionId?: string): Promise<ConversationSummary[]> {
  const query = connectionId ? `?connection_id=${encodeURIComponent(connectionId)}` : '';
  return request(`/api/v1/conversations${query}`) as Promise<ConversationSummary[]>;
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return request(`/api/v1/conversations/${encodeURIComponent(id)}`) as Promise<ConversationDetail>;
}

export function deleteConversation(id: string): Promise<void> {
  return request(`/api/v1/conversations/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }) as Promise<void>;
}

/**
 * A failed analysis still returns a full `AnalysisResponse` body with HTTP 500,
 * and the turn is persisted. It is therefore data, not an error.
 */
export async function analyze(
  question: string,
  conversationId?: string | null,
): Promise<AnalysisResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/analysis`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        question,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
    });
  } catch {
    throw new ApiError(0, 'Could not reach the RetailOps AI API.');
  }

  const raw = await response.text();
  let body: unknown = null;
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = null;
    }
  }

  if (body && typeof body === 'object' && 'status' in body && 'queries' in body) {
    return body as AnalysisResponse;
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractDetail(body) ?? `The analysis failed with status ${response.status}.`,
    );
  }

  return body as AnalysisResponse;
}
