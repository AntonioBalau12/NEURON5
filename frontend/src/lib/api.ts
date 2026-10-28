/**
 * Typed client for the NEURON5 API v1.
 *
 * The contract lives in backend/docs/API_CONTRACT.md. Everything here is
 * intentionally dependency-free so it can run in the browser only (fetch).
 */

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000').replace(/\/+$/, '');
export const API_PREFIX = '/api/v1';

/** Absolute URL for an /api/v1 path (used by fetch, WS and download anchors). */
export function apiUrl(path: string): string {
  const suffix = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE}${API_PREFIX}${suffix}`;
}

/** ws:// or wss:// URL for a streaming path, derived from API_BASE. */
export function wsUrl(path: string, query: Record<string, string | number | undefined> = {}): string {
  const url = new URL(apiUrl(path));
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  return url.toString();
}

/* ------------------------------------------------------------------ errors */

export interface ApiErrorInit {
  status?: number;
  code: string;
  message: string;
  requestId?: string;
  details?: unknown;
}

/** Normalised error for every failure the UI can encounter. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  readonly details?: unknown;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status ?? 0;
    this.code = init.code;
    this.requestId = init.requestId;
    this.details = init.details;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

interface ErrorEnvelope {
  error?: {
    code?: unknown;
    message?: unknown;
    details?: unknown;
  };
  requestId?: unknown;
}

/* ------------------------------------------------------------------ fetch */

export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  body?: BodyInit | null;
  json?: unknown;
}

/**
 * Calls the API with the session cookie, normalises the contract error
 * envelope, and never throws a raw SyntaxError for non-JSON responses.
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { json, headers: rawHeaders, body, ...rest } = options;
  const headers = new Headers(rawHeaders);
  headers.set('Accept', 'application/json');

  let finalBody = body;
  if (json !== undefined) {
    finalBody = JSON.stringify(json);
    headers.set('Content-Type', 'application/json');
  } else if (
    finalBody !== undefined &&
    finalBody !== null &&
    !(typeof FormData !== 'undefined' && finalBody instanceof FormData) &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...rest,
      headers,
      body: finalBody,
      credentials: 'include',
      cache: 'no-store',
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: `Could not reach the API at ${API_BASE}. Check that the backend is running.`,
    });
  }

  const headerRequestId = response.headers.get('X-Request-Id') ?? undefined;
  const raw = await response.text().catch(() => '');
  let payload: unknown = null;
  if (raw.length > 0) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const envelope: ErrorEnvelope = isRecord(payload) ? payload : {};
    const apiError = isRecord(envelope.error) ? envelope.error : null;
    const code = apiError && typeof apiError.code === 'string' ? apiError.code : `HTTP_${response.status}`;
    const message =
      apiError && typeof apiError.message === 'string'
        ? apiError.message
        : raw.trim().slice(0, 240) || response.statusText || 'The request failed.';
    throw new ApiError({
      status: response.status,
      code,
      message,
      requestId: typeof envelope.requestId === 'string' ? envelope.requestId : headerRequestId,
      details: apiError?.details,
    });
  }

  if (response.status === 204) return undefined as T;

  if (payload === null && raw.trim().length > 0) {
    throw new ApiError({
      status: response.status,
      code: 'INVALID_RESPONSE',
      message: 'The API returned a non-JSON response.',
      requestId: headerRequestId,
    });
  }

  return payload as T;
}

function isAbortError(error: unknown): boolean {
  return isRecord(error) && error.name === 'AbortError';
}

/* --------------------------------------------------------------- sessions */

export interface SessionInfo {
  sessionId: string;
  createdAt: string;
  expiresAt: string;
}

export const sessionsApi = {
  current: () => apiFetch<SessionInfo>('/sessions/current'),
  create: () => apiFetch<SessionInfo>('/sessions', { method: 'POST' }),
};

/** GET /sessions/current, falling back to POST /sessions on 401. */
export async function ensureSession(): Promise<SessionInfo> {
  try {
    return await sessionsApi.current();
  } catch (error) {
    if (isApiError(error) && (error.status === 401 || error.code === 'SESSION_REQUIRED')) {
      return sessionsApi.create();
    }
    throw error;
  }
}

/* --------------------------------------------------------------- datasets */

export type DatasetMode = 'manual' | 'bulk';

export interface DatasetMappingInput {
  textColumn: string;
  dateColumn: string | null;
  idColumn: string | null;
  resultColumn: string;
}

export interface DatasetMapping extends DatasetMappingInput {
  confirmed: boolean;
  autoDetected: boolean;
}

export interface PreviewPage {
  columns: string[];
  rows: string[][];
  offset: number;
  limit: number;
  total: number;
}

export interface Dataset {
  id: string;
  mode: DatasetMode;
  createdAt: string;
  byteSize: number;
  encoding: string;
  delimiter: string;
  hasHeader: boolean;
  columns: string[];
  rowCount: number | null;
  mapping: DatasetMapping | null;
  warnings: string[];
  preview: PreviewPage;
}

export interface CreateManualDatasetBody {
  columns?: string[];
  rows: (string | Record<string, string>)[][];
}

export type BulkDelimiter = ',' | ';' | '\t';

export const datasetsApi = {
  createManual: (body: CreateManualDatasetBody) =>
    apiFetch<Dataset>('/datasets/manual', { method: 'POST', json: body }),
  uploadBulk: (file: File, delimiter?: BulkDelimiter) => {
    const form = new FormData();
    form.append('file', file);
    if (delimiter) form.append('delimiter', delimiter);
    return apiFetch<Dataset>('/datasets/bulk', { method: 'POST', body: form });
  },
  get: (id: string) => apiFetch<Dataset>(`/datasets/${encodeURIComponent(id)}`),
  preview: (id: string, offset = 0, limit = 50) =>
    apiFetch<PreviewPage>(
      `/datasets/${encodeURIComponent(id)}/preview?offset=${offset}&limit=${limit}`,
    ),
  updateMapping: (id: string, mapping: DatasetMappingInput) =>
    apiFetch<Dataset>(`/datasets/${encodeURIComponent(id)}/mapping`, {
      method: 'PUT',
      json: mapping,
    }),
};

/* ------------------------------------------------------------------- jobs */

export type JobStatus = 'queued' | 'running' | 'finalizing' | 'succeeded' | 'failed' | 'cancelled';
export type JobStage = 'queued' | 'parse' | 'classify' | 'write' | 'validate' | 'done' | 'failed';

export interface JobCounters {
  true: number;
  false: number;
  unsure: number;
  fallback: number;
  errors: number;
}

export interface JobProgress {
  stage: JobStage;
  processedRows: number | null;
  totalRows: number | null;
  percent: number | null;
}

export interface Job {
  id: string;
  datasetId: string;
  status: JobStatus;
  createdAt: string;
  startedAt: string | null;
  deadlineAt: string | null;
  finishedAt: string | null;
  progress: JobProgress;
  counters: JobCounters;
  resultAvailable: boolean;
  failureReason: string | null;
  warnings: string[];
}

export interface CreateJobResponse {
  job: Pick<Job, 'id' | 'status'>;
  replayed: boolean;
}

export const jobsApi = {
  create: (datasetId: string, idempotencyKey: string) =>
    apiFetch<CreateJobResponse>('/jobs', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      json: { datasetId },
    }),
  get: (id: string) => apiFetch<Job>(`/jobs/${encodeURIComponent(id)}`),
  events: (id: string, afterSequenceId = 0, limit = 200) =>
    apiFetch<JobEventsResponse>(
      `/jobs/${encodeURIComponent(id)}/events?afterSequenceId=${afterSequenceId}&limit=${limit}`,
    ),
};

export function makeIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `fe-${crypto.randomUUID()}`;
  }
  const random = Math.random().toString(36).slice(2, 12);
  return `fe-${Date.now().toString(36)}-${random}`;
}

/* ---------------------------------------------------------------- events */

export const EVENT_LEVELS = ['TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'] as const;
export type EventLevel = (typeof EVENT_LEVELS)[number];

export const EVENT_TYPES = [
  'job.started',
  'step.started',
  'step.completed',
  'row.failed',
  'progress.updated',
  'log.recorded',
  'job.completed',
  'job.failed',
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export interface JobEvent {
  sequenceId: number;
  jobId: string;
  timestamp: string;
  level: EventLevel;
  type: EventType;
  component: string;
  step: string | null;
  message: string;
  data: Record<string, unknown> | null;
}

export interface JobEventsResponse {
  events: JobEvent[];
  lastSequenceId: number;
  truncated: boolean;
  total: number;
}

/* ------------------------------------------------------- websocket frames */

export interface WsHandshakeFrame {
  kind: 'handshake';
  protocolVersion: number;
  jobId: string;
  status: JobStatus;
  lastSequenceId: number;
  replayAvailable: boolean;
  serverTime: string;
}

export interface WsSnapshotFrame {
  kind: 'snapshot';
  job: Job;
  gap: boolean;
  replayFrom: number;
}

export interface WsEventFrame {
  kind: 'event';
  event: JobEvent;
}

export interface WsHeartbeatFrame {
  kind: 'heartbeat';
  serverTime: string;
}

export type WsFrame = WsHandshakeFrame | WsSnapshotFrame | WsEventFrame | WsHeartbeatFrame;

/** Parses a WS text frame defensively; returns null for anything malformed. */
export function parseWsFrame(raw: string): WsFrame | null {
  if (!raw) return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(value) || typeof value.kind !== 'string') return null;

  switch (value.kind) {
    case 'handshake':
      if (typeof value.jobId !== 'string' || typeof value.lastSequenceId !== 'number') return null;
      return value as unknown as WsHandshakeFrame;
    case 'snapshot':
      if (!isRecord(value.job) || typeof value.job.id !== 'string') return null;
      return value as unknown as WsSnapshotFrame;
    case 'event':
      if (!isRecord(value.event) || typeof value.event.sequenceId !== 'number') return null;
      return value as unknown as WsEventFrame;
    case 'heartbeat':
      return value as unknown as WsHeartbeatFrame;
    default:
      return null;
  }
}

/* --------------------------------------------------------------- results */

export interface ResultOutput {
  fileName: string;
  bytes: number;
  contentType: string;
}

export interface ResultSummary {
  jobId: string;
  status: JobStatus;
  totalRows: number | null;
  counts: JobCounters;
  durationSeconds: number | null;
  warnings: string[];
  failureReason: string | null;
  output: ResultOutput | null;
  errorsCount: number;
}

export interface ResultRowError {
  rowId: string;
  lineNumber: number | null;
  column: string | null;
  code: string;
  message: string;
}

export interface Paginated<T> {
  items: T[];
  offset: number;
  limit: number;
  total: number;
}

export const resultsApi = {
  summary: (jobId: string) =>
    apiFetch<ResultSummary>(`/jobs/${encodeURIComponent(jobId)}/result/summary`),
  preview: (jobId: string, offset = 0, limit = 20) =>
    apiFetch<PreviewPage>(
      `/jobs/${encodeURIComponent(jobId)}/result/preview?offset=${offset}&limit=${limit}`,
    ),
  errors: (jobId: string, offset = 0, limit = 10) =>
    apiFetch<Paginated<ResultRowError>>(
      `/jobs/${encodeURIComponent(jobId)}/result/errors?offset=${offset}&limit=${limit}`,
    ),
  csvUrl: (jobId: string) => apiUrl(`/jobs/${encodeURIComponent(jobId)}/result.csv`),
};

/* -------------------------------------------------------------- guardrails */

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  finalizing: 'Finalizing',
  succeeded: 'Succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export const JOB_STAGES: JobStage[] = ['queued', 'parse', 'classify', 'write', 'validate', 'done', 'failed'];

export function isTerminalStatus(status: JobStatus): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled';
}

export function isJobStage(value: unknown): value is JobStage {
  return typeof value === 'string' && (JOB_STAGES as string[]).includes(value);
}
