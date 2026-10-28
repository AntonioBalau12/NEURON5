'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import JenkinsPipelineWorkflow from './JenkinsPipelineWorkflow';

import {
  ArrowLeft,
  Download,
  Radio,
  RefreshCw,
  ScrollText,
  Terminal,
  Trash2,
  WifiOff,
  XCircle,
} from 'lucide-react';
import {
  ApiError,
  EVENT_LEVELS,
  JOB_STATUS_LABEL,
  isApiError,
  isJobStage,
  isRecord,
  isTerminalStatus,
  jobsApi,
  parseWsFrame,
  wsUrl,
  type EventLevel,
  type Job,
  type JobCounters,
  type JobEvent,
  type JobStatus,
} from '@/lib/api';
import {
  Badge,
  Button,
  ErrorNotice,
  Spinner,
  StatusDot,
  WarningList,
  cx,
  formatClock,
  formatNumber,
  type BadgeTone,
} from './ui';

const MAX_VISIBLE_EVENTS = 1000;

type ConnectionState = 'connecting' | 'open' | 'reconnecting' | 'offline' | 'closed';

const LEVEL_CLASS: Record<EventLevel, string> = {
  TRACE: 'text-black/35',
  DEBUG: 'text-black/50',
  INFO: 'text-[#76910a]',
  WARN: 'text-amber-600',
  ERROR: 'text-red-600',
  FATAL: 'text-red-700 font-bold',
};

function stageRank(stage: string): number {
  switch (stage) {
    case 'queued':
      return 0;
    case 'parse':
      return 1;
    case 'classify':
      return 2;
    case 'write':
      return 3;
    case 'validate':
      return 4;
    case 'done':
      return 5;
    case 'failed':
      return 6;
    default:
      return 0;
  }
}

function numeric(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function formatEventTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

function maxCounter(previous: number | undefined, incoming: number | undefined): number {
  const left = typeof previous === 'number' && Number.isFinite(previous) ? previous : 0;
  const right = typeof incoming === 'number' && Number.isFinite(incoming) ? incoming : 0;
  return Math.max(left, right);
}

function mergeCounters(previous: JobCounters, incoming: Partial<JobCounters> | null | undefined): JobCounters {
  return {
    true: maxCounter(previous.true, incoming?.true),
    false: maxCounter(previous.false, incoming?.false),
    unsure: maxCounter(previous.unsure, incoming?.unsure),
    fallback: maxCounter(previous.fallback, incoming?.fallback),
    errors: maxCounter(previous.errors, incoming?.errors),
  };
}

function mergeWarnings(previous: string[], incoming: string[]): string[] {
  if (!incoming || incoming.length === 0) return previous;
  const merged = previous.slice();
  for (const warning of incoming) {
    if (!merged.includes(warning)) merged.push(warning);
  }
  return merged;
}

/** Merge an authoritative job snapshot without letting stale responses move the UI backwards. */
function mergeJob(previous: Job | null, incoming: Job): Job {
  if (!previous || previous.id !== incoming.id) return incoming;
  const stage =
    stageRank(incoming.progress.stage) >= stageRank(previous.progress.stage)
      ? incoming.progress.stage
      : previous.progress.stage;
  const processedRows =
    incoming.progress.processedRows === null && previous.progress.processedRows === null
      ? null
      : Math.max(previous.progress.processedRows ?? 0, incoming.progress.processedRows ?? 0);
  const percent =
    incoming.progress.percent === null
      ? previous.progress.percent
      : previous.progress.percent === null
        ? incoming.progress.percent
        : Math.max(previous.progress.percent, incoming.progress.percent);
  return {
    ...incoming,
    status: isTerminalStatus(previous.status) ? previous.status : incoming.status,
    finishedAt: incoming.finishedAt ?? previous.finishedAt,
    failureReason: incoming.failureReason ?? previous.failureReason,
    resultAvailable: previous.resultAvailable || incoming.resultAvailable,
    warnings: mergeWarnings(previous.warnings, incoming.warnings),
    counters: mergeCounters(previous.counters, incoming.counters),
    progress: {
      stage,
      processedRows,
      totalRows: incoming.progress.totalRows ?? previous.progress.totalRows,
      percent,
    },
  };
}

/** Apply an event's counters/progress/stage/percent without ever inventing a percentage. */
function applyEventToJob(previous: Job | null, event: JobEvent): Job | null {
  if (!previous) return previous;
  const data = isRecord(event.data) ? event.data : {};
  const counts = isRecord(data.counts) ? (data.counts as Partial<JobCounters>) : null;
  const counters = counts ? mergeCounters(previous.counters, counts) : previous.counters;

  const processed = numeric(data.processedRows);
  const processedRows =
    processed === null
      ? previous.progress.processedRows
      : Math.max(previous.progress.processedRows ?? 0, processed);

  const totalRows = numeric(data.totalRows) ?? previous.progress.totalRows;

  let stage = previous.progress.stage;
  const candidateStage = isJobStage(event.step) ? event.step : isJobStage(data.stage) ? data.stage : null;
  if (candidateStage && stageRank(candidateStage) >= stageRank(stage)) stage = candidateStage;

  let percent = previous.progress.percent;
  const explicitPercent = numeric(data.percent);
  if (explicitPercent !== null) {
    percent = Math.max(0, Math.min(100, Math.round(explicitPercent)));
  } else if (totalRows !== null && totalRows > 0 && processedRows !== null) {
    percent = Math.max(0, Math.min(100, Math.floor((processedRows / totalRows) * 100)));
  }

  let status = previous.status;
  let resultAvailable = previous.resultAvailable;
  let failureReason = previous.failureReason;
  if (event.type === 'job.completed') {
    status = 'succeeded';
    resultAvailable = true;
  } else if (event.type === 'job.failed') {
    status = 'failed';
    if (typeof data.failureReason === 'string' && data.failureReason.length > 0) {
      failureReason = data.failureReason;
    }
  }

  return {
    ...previous,
    status,
    resultAvailable,
    failureReason,
    counters,
    progress: { stage, processedRows, totalRows, percent },
  };
}

function addLevel(previous: EventLevel[], level: EventLevel): EventLevel[] {
  if (previous.includes(level)) return previous;
  return EVENT_LEVELS.filter((item) => item === level || previous.includes(item));
}

function addSorted(previous: string[], value: string): string[] {
  if (!value || previous.includes(value)) return previous;
  return previous.concat(value).sort((left, right) => left.localeCompare(right));
}

function statusTone(status: JobStatus): BadgeTone {
  if (status === 'succeeded') return 'green';
  if (status === 'failed' || status === 'cancelled') return 'red';
  if (status === 'running' || status === 'finalizing') return 'lime';
  return 'neutral';
}

function CounterCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | undefined;
  tone: 'green' | 'red' | 'amber' | 'neutral' | 'lime';
}) {
  const tones: Record<typeof tone, string> = {
    green: 'border-emerald-500/20 bg-emerald-50/70 text-emerald-800',
    red: 'border-red-500/20 bg-red-50/70 text-red-800',
    amber: 'border-amber-500/25 bg-amber-50/70 text-amber-800',
    neutral: 'border-black/10 bg-[#fcfcfc] text-black/60',
    lime: 'border-[#9ebc19]/30 bg-[#d7f13b]/20 text-[#76910a]',
  };
  return (
    <div className={cx('rounded-xl border p-3', tones[tone])}>
      <p className="text-[10px] font-bold uppercase tracking-wider opacity-70">{label}</p>
      <p className="mt-0.5 font-display text-xl font-black text-[#202020]">{formatNumber(value ?? 0)}</p>
    </div>
  );
}

export interface ProcessingViewProps {
  jobId: string;
  onSucceeded: (job: Job) => void;
  onBack: () => void;
}

export default function ProcessingView({ jobId, onSucceeded, onBack }: ProcessingViewProps) {
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [protocolVersion, setProtocolVersion] = useState<number | null>(null);
  const [serverSequence, setServerSequence] = useState<number | null>(null);
  const [handshakeStatus, setHandshakeStatus] = useState<JobStatus | null>(null);
  const [gapNotice, setGapNotice] = useState<string | null>(null);
  const [wsError, setWsError] = useState<unknown>(null);
  const [lastHeartbeat, setLastHeartbeat] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [levelFilter, setLevelFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [componentFilter, setComponentFilter] = useState('');
  const [seenLevels, setSeenLevels] = useState<EventLevel[]>([]);
  const [seenTypes, setSeenTypes] = useState<string[]>([]);
  const [seenComponents, setSeenComponents] = useState<string[]>([]);
  const [truncatedView, setTruncatedView] = useState(false);

  const logRef = useRef<HTMLDivElement>(null);
  const onSucceededRef = useRef(onSucceeded);
  const restartSocketRef = useRef<(() => void) | null>(null);
  const refreshNowRef = useRef<(() => void) | null>(null);
  const finishRef = useRef<((terminalJob: Job) => Promise<void>) | null>(null);

  useEffect(() => {
    onSucceededRef.current = onSucceeded;
  }, [onSucceeded]);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pollTimer: number | null = null;
    let refreshing = false;
    let eventPoll: Promise<void> | null = null;
    let socketConnected = false;
    let finishing = false;
    let attempts = 0;
    let cursor = 0;
    let minSequence = 0;
    let terminal = false;
    let advanced = false;
    let receivedEvents = 0;

    setJob(null);
    setEvents([]);
    setLoading(true);
    setLoadError(null);
    setConnection('connecting');
    setReconnectAttempt(0);
    setProtocolVersion(null);
    setServerSequence(null);
    setHandshakeStatus(null);
    setGapNotice(null);
    setWsError(null);
    setLastHeartbeat(null);
    setLevelFilter('');
    setTypeFilter('');
    setComponentFilter('');
    setSeenLevels([]);
    setSeenTypes([]);
    setSeenComponents([]);
    setTruncatedView(false);

    function clearTimers() {
      if (pollTimer !== null) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function closeSocket() {
      socketConnected = false;
      if (!socket) return;
      const closing = socket;
      socket = null;
      closing.onopen = null;
      closing.onmessage = null;
      closing.onerror = null;
      closing.onclose = null;
      try {
        closing.close();
      } catch {
        // The socket may already be closed; nothing else to do.
      }
    }

    function appendEvent(event: JobEvent) {
      const sequence = Number(event.sequenceId);
      if (!Number.isFinite(sequence) || sequence < minSequence || sequence <= cursor) return;
      cursor = sequence;
      receivedEvents += 1;
      if (receivedEvents > MAX_VISIBLE_EVENTS) setTruncatedView(true);
      setEvents((previous) => {
        const next = previous.concat(event);
        return next.length > MAX_VISIBLE_EVENTS ? next.slice(next.length - MAX_VISIBLE_EVENTS) : next;
      });
      setSeenLevels((previous) => addLevel(previous, event.level));
      if (typeof event.type === 'string') setSeenTypes((previous) => addSorted(previous, event.type));
      if (typeof event.component === 'string') setSeenComponents((previous) => addSorted(previous, event.component));
      setJob((previous) => applyEventToJob(previous, event) ?? previous);
    }

    function pollEventHistory(force = false, drain = false): Promise<void> {
      if (disposed || terminal || (!force && socketConnected)) return Promise.resolve();
      if (eventPoll) return eventPoll;
      eventPoll = (async () => {
        do {
          const response = await jobsApi.events(jobId, cursor, 1000);
          if (response.truncated && response.events.length > 0) {
            const firstSequence = response.events[0].sequenceId;
            setGapNotice(`Older events were dropped. Showing history from sequence ${firstSequence}.`);
            setEvents([]);
            minSequence = firstSequence;
            cursor = Math.max(0, firstSequence - 1);
          }
          const previousCursor = cursor;
          response.events.forEach(appendEvent);
          if (!drain || response.events.length === 0 || cursor <= previousCursor || cursor >= response.lastSequenceId) break;
        } while (!disposed && !terminal);
      })()
        .catch((error: unknown) => {
          if (!disposed) setWsError(error);
        })
        .finally(() => {
          eventPoll = null;
        });
      return eventPoll;
    }

    async function finish(terminalJob: Job): Promise<void> {
      if (disposed || terminal || finishing) return;
      finishing = true;
      if (eventPoll) await eventPoll;
      await pollEventHistory(true, true);
      if (disposed) return;
      terminal = true;
      clearTimers();
      closeSocket();
      setConnection('closed');
      if (terminalJob.status === 'succeeded' && !advanced) {
        advanced = true;
        onSucceededRef.current(terminalJob);
      }
    }

    finishRef.current = finish;

    function handleJobUpdate(incoming: Job) {
      if (disposed) return;
      setJob((previous) => mergeJob(previous, incoming));
      setLoading(false);
      setLoadError(null);
      if (isTerminalStatus(incoming.status)) finish(incoming);
    }

    async function refresh() {
      if (disposed || terminal || refreshing) return;
      refreshing = true;
      try {
        const incoming = await jobsApi.get(jobId);
        if (isTerminalStatus(incoming.status)) await pollEventHistory(true, true);
        handleJobUpdate(incoming);
      } catch (error) {
        if (disposed) return;
        setLoadError(error);
        setLoading(false);
        if (isApiError(error) && (error.code === 'NOT_FOUND' || error.code === 'SESSION_REQUIRED')) {
          terminal = true;
          clearTimers();
          closeSocket();
          setConnection('offline');
        }
      } finally {
        refreshing = false;
      }
    }

    refreshNowRef.current = () => {
      void refresh();
    };

    function scheduleReconnect() {
      if (disposed || terminal) return;
      if (attempts >= 3) {
        setConnection('offline');
        return;
      }
      attempts += 1;
      setReconnectAttempt(attempts);
      setConnection('reconnecting');
      const delay = attempts === 1 ? 1000 : attempts === 2 ? 2000 : 4000;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        openSocket();
      }, delay);
    }

    function openSocket() {
      if (disposed || terminal) return;
      let url: string;
      try {
        url = wsUrl(
          '/jobs/' + encodeURIComponent(jobId) + '/stream',
          cursor > 0 ? { lastSequenceId: cursor } : {},
        );
      } catch {
        setConnection('offline');
        return;
      }

      if (connection !== 'open') {
        setConnection(attempts > 0 ? 'reconnecting' : 'connecting');
      }

      let nextSocket: WebSocket;
      try {
        nextSocket = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }
      socket = nextSocket;

      nextSocket.onopen = () => {
        if (disposed || terminal) {
          nextSocket.close();
          return;
        }
        attempts = 0;
        socketConnected = true;
        setReconnectAttempt(0);
        setConnection('open');
        setWsError(null);
      };

      nextSocket.onmessage = (message) => {
        if (disposed || terminal) return;
        if (typeof message.data !== 'string') return;
        const frame = parseWsFrame(message.data);
        if (!frame) return;

        if (frame.kind === 'handshake') {
          socketConnected = true;
          setProtocolVersion(frame.protocolVersion);
          setServerSequence(frame.lastSequenceId);
          setHandshakeStatus(frame.status);
          setConnection('open');
          return;
        }

        if (frame.kind === 'snapshot') {
          setLoading(false);
          if (frame.gap) {
            setGapNotice(
              'The server dropped older events, so the log restarted at sequence ' +
                frame.replayFrom +
                '. Counters and progress come from the snapshot.',
            );
            setEvents([]);
            minSequence = frame.replayFrom;
            cursor = Math.max(0, frame.replayFrom - 1);
          }
          setJob((previous) => mergeJob(previous, frame.job));
          if (isTerminalStatus(frame.job.status)) void finish(frame.job);
          return;
        }

        if (frame.kind === 'heartbeat') {
          setLastHeartbeat(frame.serverTime);
          setConnection('open');
          return;
        }

        const event = frame.event;
        setConnection('open');
        appendEvent(event);
        if (event.type === 'job.completed' || event.type === 'job.failed') {
          void refresh();
        }
      };

      nextSocket.onerror = () => {
        // onclose follows and decides whether to reconnect.
      };

      nextSocket.onclose = (closeEvent) => {
        if (socket === nextSocket) socket = null;
        socketConnected = false;
        if (disposed || terminal) return;
        if (closeEvent.code === 4401 || closeEvent.code === 4403 || closeEvent.code === 4404) {
          const code =
            closeEvent.code === 4401
              ? 'SESSION_REQUIRED'
              : closeEvent.code === 4404
                ? 'NOT_FOUND'
                : 'FORBIDDEN_ORIGIN';
          const message =
            closeEvent.code === 4401
              ? 'The session expired; the API rejected the live stream.'
              : closeEvent.code === 4404
                ? 'This job is not available to the current session.'
                : 'The API rejected the stream origin.';
          setWsError(new ApiError({ code, message, status: 0 }));
          setConnection('offline');
          // Keep the HTTP polling fallback alive: a rejected stream does not mean the job stopped.
          return;
        }
        scheduleReconnect();
      };
    }

    restartSocketRef.current = () => {
      if (disposed || terminal) return;
      attempts = 0;
      setReconnectAttempt(0);
      setWsError(null);
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (socket) {
        const stale = socket;
        socket = null;
        stale.onclose = null;
        stale.onopen = null;
        stale.onmessage = null;
        stale.onerror = null;
        try {
          stale.close();
        } catch {
          // ignore
        }
      }
      setConnection('connecting');
      openSocket();
    };

    void refresh();
    pollTimer = window.setInterval(() => {
      void refresh();
      void pollEventHistory();
    }, 2000);
    void pollEventHistory();
    openSocket();

    return () => {
      disposed = true;
      clearTimers();
      closeSocket();
      restartSocketRef.current = null;
      refreshNowRef.current = null;
      finishRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    if (job && isTerminalStatus(job.status)) finishRef.current?.(job);
  }, [job]);

  const filteredEvents = useMemo(() => {
    return events.filter((event) => {
      if (levelFilter && event.level !== levelFilter) return false;
      if (typeFilter && event.type !== typeFilter) return false;
      if (componentFilter && event.component !== componentFilter) return false;
      return true;
    });
  }, [events, levelFilter, typeFilter, componentFilter]);

  const lastSequence = filteredEvents.length > 0 ? filteredEvents[filteredEvents.length - 1].sequenceId : 0;

  useEffect(() => {
    if (!autoScroll) return;
    const node = logRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [autoScroll, lastSequence, levelFilter, typeFilter, componentFilter]);

  const progress = job?.progress;
  const percent = progress?.percent ?? null;
  const terminal = job ? isTerminalStatus(job.status) : false;
  const counts = job?.counters;
  const displayStatus = job?.status ?? handshakeStatus;

  function handleExport() {
    const payload = {
      jobId,
      exportedAt: new Date().toISOString(),
      filters: {
        level: levelFilter || null,
        type: typeFilter || null,
        component: componentFilter || null,
      },
      eventCount: filteredEvents.length,
      events: filteredEvents,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'job-' + jobId + '-logs.json';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function clearView() {
    setEvents([]);
    setTruncatedView(false);
  }

  const connectionTone: BadgeTone =
    connection === 'open'
      ? 'green'
      : connection === 'offline'
        ? 'red'
        : connection === 'closed'
          ? 'neutral'
          : 'amber';
  const connectionLabel =
    connection === 'open'
      ? 'Live stream'
      : connection === 'reconnecting'
        ? 'Reconnecting ' + reconnectAttempt + '/3…'
        : connection === 'offline'
          ? 'Offline · polling'
          : connection === 'closed'
            ? 'Stream closed'
            : 'Connecting…';

  return (
    <div className="p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-black/[0.08] pb-4">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#76910a]">
            Stage 2 · Processing
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <h3 className="font-display text-base font-bold text-[#202020]">Live run</h3>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {connection === 'offline' && !terminal ? (
            <Button size="sm" variant="secondary" onClick={() => restartSocketRef.current?.()}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Reconnect stream
            </Button>
          ) : null}
          <span className="hidden text-[10px] text-black/35 sm:inline">
            {lastHeartbeat ? 'heartbeat ' + formatClock(lastHeartbeat) : 'awaiting heartbeat'}
          </span>
        </div>
      </div>

      {loadError ? (
        <ErrorNotice
          className="mt-3"
          error={loadError}
          onRetry={() => refreshNowRef.current?.()}
          retryLabel="Reload job"
          onBack={!job ? onBack : undefined}
        />
      ) : null}

      {wsError ? (
        <ErrorNotice
          className="mt-3"
          error={wsError}
          onRetry={() => restartSocketRef.current?.()}
          retryLabel="Retry stream"
          onDismiss={() => setWsError(null)}
          onBack={!job ? onBack : undefined}
        />
      ) : null}

      {!job && !loadError ? (
        <div className="flex min-h-[16rem] items-center justify-center">
          <Spinner label="Loading job state…" />
        </div>
      ) : null}

      {job ? (
        <>
          {job.status === 'failed' ? (
            <div role="alert" className="mt-4 rounded-2xl border border-red-500/25 bg-red-50/80 p-4">
              <div className="flex items-start gap-2.5">
                <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-bold text-red-800">Processing failed</p>
                  <p className="mt-1 text-xs leading-relaxed text-red-900/80">
                    {job.failureReason ?? 'The API did not report a failure reason.'}
                  </p>
                  <p className="mt-1 text-[11px] text-red-900/55">
                    The job is terminal. Adjust the input or mapping, then start a new run.
                  </p>
                  <div className="mt-3">
                    <Button size="sm" variant="secondary" onClick={onBack}>
                      <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to data
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <WarningList warnings={job.warnings} className="mt-4" />

          {/* Jenkins Architecture Workflow Diagram with Glowing Green Aura */}
          <JenkinsPipelineWorkflow
            stage={job?.progress?.stage}
            percent={percent}
            message={events[events.length - 1]?.message}
            className="mt-4"
          />

          <div className="mt-4 rounded-2xl border border-black/[0.08] bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ScrollText className="h-4 w-4 text-[#76910a]" aria-hidden="true" />
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-black/50">Progress</h4>
              </div>
              <span className="font-mono text-[11px] text-black/55">
                {percent !== null ? percent + '%' : 'percent unavailable'}
              </span>
            </div>

            <div
              className="mt-2 h-2 overflow-hidden rounded-full bg-black/10"
              role="progressbar"
              aria-label="Job progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent !== null ? percent : undefined}
              aria-valuetext={
                percent !== null
                  ? percent + '% complete'
                  : 'Percentage unavailable because the total number of rows is unknown'
              }
            >
              <div
                className={cx(
                  'h-full rounded-full bg-[#d7f13b] transition-[width] duration-500',
                  percent === null && 'w-1/4 animate-pulse bg-[#d7f13b]/60',
                )}
                style={percent !== null ? { width: percent + '%' } : undefined}
              />
            </div>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-black/50">
              <span>
                <span className="font-semibold text-[#202020]">{formatNumber(progress?.processedRows ?? 0)}</span>{' '}
                of{' '}
                <span className="font-semibold text-[#202020]">
                  {progress?.totalRows !== null && progress?.totalRows !== undefined
                    ? formatNumber(progress.totalRows)
                    : 'unknown'}
                </span>{' '}
                rows · stage <span className="font-mono text-[#202020]">{progress?.stage ?? '—'}</span>
              </span>
              <span>
                {job.resultAvailable ? 'result available' : 'result not available yet'}
              </span>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <CounterCard label="true" value={counts?.true} tone="green" />
            <CounterCard label="false" value={counts?.false} tone="red" />
            <CounterCard label="unsure" value={counts?.unsure} tone="amber" />
            <CounterCard label="fallback" value={counts?.fallback} tone="neutral" />
            <CounterCard label="errors" value={counts?.errors} tone="red" />
          </div>

          <div className="mt-4 rounded-2xl border border-black/[0.08] bg-[#fcfcfc]">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/[0.08] p-3">
              <div className="flex items-center gap-2">
                <Terminal className="h-4 w-4 text-[#76910a]" aria-hidden="true" />
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-black/50">Event log</h4>
                <span className="text-[10px] text-black/35">
                  {filteredEvents.length} shown / {events.length} in view
                </span>
                {truncatedView ? <Badge tone="amber">newest 1000</Badge> : null}
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <select
                  aria-label="Filter events by level"
                  value={levelFilter}
                  onChange={(event) => setLevelFilter(event.target.value)}
                  className="rounded-lg border border-black/10 bg-white px-2 py-1.5 font-mono text-[10px] text-[#202020] outline-none focus:border-[#9ebc19]/50 focus:ring-2 focus:ring-[#9ebc19]/15"
                >
                  <option value="">all levels</option>
                  {seenLevels.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>

                <select
                  aria-label="Filter events by type"
                  value={typeFilter}
                  onChange={(event) => setTypeFilter(event.target.value)}
                  className="max-w-[10rem] rounded-lg border border-black/10 bg-white px-2 py-1.5 font-mono text-[10px] text-[#202020] outline-none focus:border-[#9ebc19]/50 focus:ring-2 focus:ring-[#9ebc19]/15"
                >
                  <option value="">all types</option>
                  {seenTypes.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>

                <select
                  aria-label="Filter events by component"
                  value={componentFilter}
                  onChange={(event) => setComponentFilter(event.target.value)}
                  className="max-w-[10rem] rounded-lg border border-black/10 bg-white px-2 py-1.5 font-mono text-[10px] text-[#202020] outline-none focus:border-[#9ebc19]/50 focus:ring-2 focus:ring-[#9ebc19]/15"
                >
                  <option value="">all components</option>
                  {seenComponents.map((component) => (
                    <option key={component} value={component}>
                      {component}
                    </option>
                  ))}
                </select>

                <label className="inline-flex items-center gap-1.5 rounded-lg border border-black/10 bg-white px-2 py-1.5 text-[10px] font-semibold text-black/55">
                  <input
                    type="checkbox"
                    checked={autoScroll}
                    onChange={(event) => setAutoScroll(event.target.checked)}
                    className="h-3 w-3 accent-[#9ebc19]"
                  />
                  Auto-scroll
                </label>

                <Button size="sm" onClick={clearView} disabled={events.length === 0}>
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Clear
                </Button>

                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleExport}
                  disabled={filteredEvents.length === 0}
                  title="Download the currently visible events as JSON"
                >
                  <Download className="h-3.5 w-3.5" aria-hidden="true" /> Export .json
                </Button>
              </div>
            </div>

            {gapNotice ? (
              <div
                role="status"
                className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-500/20 bg-amber-50/70 px-3 py-2 text-[11px] text-amber-900"
              >
                <span>{gapNotice}</span>
                <button
                  type="button"
                  onClick={() => setGapNotice(null)}
                  className="text-[10px] font-bold text-amber-800 underline underline-offset-2"
                >
                  Dismiss
                </button>
              </div>
            ) : null}

            <div
              ref={logRef}
              role="log"
              aria-label="Job event log"
              aria-live="off"
              className="h-[340px] overflow-auto bg-white"
            >
              {filteredEvents.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center px-6 text-center">
                  <Radio className="mb-2 h-5 w-5 text-black/20" aria-hidden="true" />
                  <p className="text-xs font-bold text-black/50">
                    {events.length === 0 ? 'Waiting for events…' : 'No events match these filters'}
                  </p>
                  <p className="mt-1 text-[11px] text-black/35">
                    {events.length === 0
                      ? 'The processor emits job, step and progress events as soon as the run starts.'
                      : 'Clear a filter to see more of the stream.'}
                  </p>
                </div>
              ) : (
                <ul>
                  {filteredEvents.map((event) => (
                    <li
                      key={event.sequenceId}
                      className="grid grid-cols-[3rem_4rem_minmax(0,1fr)] gap-2 border-b border-black/[0.04] px-3 py-1.5 font-mono text-[10px] leading-relaxed hover:bg-black/[0.015]"
                    >
                      <span className="text-right text-black/25">{event.sequenceId}</span>
                      <span className={cx('font-bold', LEVEL_CLASS[event.level] ?? 'text-black/50')}>
                        {event.level}
                      </span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-baseline gap-x-2">
                          <span className="text-[#76910a]">{event.type}</span>
                          <span className="text-black/30">{event.component}</span>
                          {event.step ? <span className="text-black/25">[{event.step}]</span> : null}
                          <time className="text-black/30" dateTime={event.timestamp} title={event.timestamp}>
                            {formatEventTimestamp(event.timestamp)}
                          </time>
                        </div>
                        <p className="whitespace-pre-wrap break-words text-black/70">{event.message}</p>
                        {event.data && Object.keys(event.data).length > 0 ? (
                          <details className="mt-1 text-black/45">
                            <summary className="w-fit cursor-pointer select-none hover:text-black/70">
                              Details
                            </summary>
                            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-black/[0.025] p-2 text-[9px] text-black/60">
                              {JSON.stringify(event.data, null, 2)}
                            </pre>
                          </details>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="flex items-center gap-1.5 border-t border-black/[0.06] px-3 py-2 text-[10px] text-black/35">
              {connection === 'offline' ? (
                <WifiOff className="h-3 w-3" aria-hidden="true" />
              ) : (
                <StatusDot tone={connectionTone} pulse={connection === 'open'} />
              )}
              {connectionLabel}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
