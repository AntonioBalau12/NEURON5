'use client';

import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Database, Loader2, X } from 'lucide-react';
import { ApiError, type Dataset } from '@/lib/api';

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

/* ------------------------------------------------------------------ button */

type ButtonVariant = 'primary' | 'secondary' | 'accent' | 'ghost' | 'danger' | 'dark';
type ButtonSize = 'sm' | 'md';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-[#d7f13b] text-[#202020] hover:bg-[#9ebc19] border border-transparent shadow-sm shadow-[#d7f13b]/30',
  secondary:
    'bg-white text-[#202020] border border-black/10 hover:bg-black/[0.03] disabled:hover:bg-white',
  accent:
    'bg-[#d7f13b] text-[#202020] border border-[#c8e22f] hover:brightness-95 shadow-sm shadow-[#d7f13b]/30',
  ghost: 'bg-transparent text-[#76910a] border border-transparent hover:bg-[#d7f13b]/15',
  danger: 'bg-white text-red-600 border border-red-200 hover:bg-red-50',
  dark: 'bg-[#202020] text-white border border-transparent hover:bg-black',
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-[11px] rounded-lg gap-1.5',
  md: 'px-3.5 py-2 text-xs rounded-xl gap-2',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        'inline-flex items-center justify-center font-bold tracking-wide transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#9ebc19]/50 focus-visible:ring-offset-1',
        'disabled:cursor-not-allowed disabled:opacity-50',
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ badges */

export type BadgeTone = 'neutral' | 'blue' | 'green' | 'red' | 'amber' | 'lime';

const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: 'bg-black/[0.04] text-black/60 border-black/10',
  blue: 'bg-[#d7f13b]/20 text-[#76910a] border-[#9ebc19]/30',
  green: 'bg-emerald-50 text-emerald-700 border-emerald-500/25',
  red: 'bg-red-50 text-red-700 border-red-500/25',
  amber: 'bg-amber-50 text-amber-700 border-amber-500/25',
  lime: 'bg-[#d7f13b]/25 text-[#4d5600] border-[#c8e22f]/60',
};

export function Badge({
  tone = 'neutral',
  children,
  className,
  mono = false,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  mono?: boolean;
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider',
        mono && 'font-mono normal-case tracking-normal',
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusDot({ tone = 'neutral', pulse = false }: { tone?: BadgeTone; pulse?: boolean }) {
  const color: Record<BadgeTone, string> = {
    neutral: 'bg-black/30',
    blue: 'bg-[#9ebc19]',
    green: 'bg-emerald-500',
    red: 'bg-red-500',
    amber: 'bg-amber-500',
    lime: 'bg-[#b7cf1f]',
  };
  return (
    <span
      aria-hidden="true"
      className={cx('inline-block h-1.5 w-1.5 rounded-full', color[tone], pulse && 'animate-pulse')}
    />
  );
}

/* ------------------------------------------------------------------ errors */

export interface ErrorInfo {
  code: string;
  message: string;
  requestId?: string;
  details?: unknown;
}

/** Turns anything thrown by the UI into the contract error fields. */
export function errorInfo(error: unknown): ErrorInfo {
  if (error instanceof ApiError) {
    return {
      code: error.code,
      message: error.message,
      requestId: error.requestId,
      details: error.details,
    };
  }
  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>;
    if (typeof record.code === 'string' && typeof record.message === 'string') {
      return {
        code: record.code,
        message: record.message,
        requestId: typeof record.requestId === 'string' ? record.requestId : undefined,
        details: record.details,
      };
    }
  }
  if (error instanceof Error) {
    return { code: 'UNEXPECTED_ERROR', message: error.message };
  }
  return { code: 'UNEXPECTED_ERROR', message: 'Something went wrong. Please try again.' };
}

function safeDetails(details: unknown): string | null {
  if (details === undefined || details === null) return null;
  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return String(details);
  }
}

export function ErrorNotice({
  error,
  onRetry,
  retryLabel = 'Retry',
  retryDisabled = false,
  onDismiss,
  onBack,
  action,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  retryLabel?: string;
  retryDisabled?: boolean;
  onDismiss?: () => void;
  onBack?: () => void;
  action?: ReactNode;
  className?: string;
}) {
  const info = errorInfo(error);
  const details = safeDetails(info.details);
  return (
    <div
      role="alert"
      className={cx(
        'rounded-xl border border-red-500/25 bg-red-50/80 p-3.5 text-[#202020]',
        className,
      )}
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-mono text-[11px] font-bold text-red-700">{info.code}</span>
            {info.requestId ? (
              <span className="font-mono text-[10px] text-black/45">requestId: {info.requestId}</span>
            ) : null}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-black/75">{info.message}</p>
          {details ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-[11px] font-semibold text-red-700/80">
                Details
              </summary>
              <pre className="mt-1 max-h-32 overflow-auto rounded-lg border border-red-500/15 bg-white/70 p-2 font-mono text-[10px] leading-relaxed">
                {details}
              </pre>
            </details>
          ) : null}
          {onRetry || onDismiss || onBack || action ? (
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              {onRetry ? (
                <Button size="sm" onClick={onRetry} disabled={retryDisabled}>
                  {retryLabel}
                </Button>
              ) : null}
              {action}
              {onBack ? (
                <Button size="sm" variant="ghost" onClick={onBack}>
                  Back to data
                </Button>
              ) : null}
              {onDismiss ? (
                <Button size="sm" variant="ghost" onClick={onDismiss} aria-label="Dismiss error">
                  <X className="h-3 w-3" aria-hidden="true" /> Dismiss
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- warnings */

const WARNING_TEXT: Record<string, string> = {
  AMBIGUOUS_DELIMITER:
    'The delimiter was ambiguous in the first non-empty line; comma was assumed. Re-upload with an explicit delimiter if the preview looks wrong.',
  BOM_PRESENT: 'The file started with a UTF-8 BOM; the BOM was stripped before parsing.',
  EMPTY_FILE: 'The uploaded file contains no data rows.',
  HEADER_WITHOUT_TEXT_COLUMN:
    'No obvious text column was detected in the header. Pick the text column manually before processing.',
  TIMED_OUT_FALLBACK:
    'Processing reached its deadline; the remaining rows were written with the "unsure" fallback.',
};

export function warningText(code: string): string {
  return WARNING_TEXT[code] ?? 'The server reported a warning with an unknown code.';
}

export function WarningList({
  warnings,
  title = 'Warnings',
  className,
}: {
  warnings: string[];
  title?: string;
  className?: string;
}) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <div
      role="status"
      className={cx('rounded-xl border border-amber-500/30 bg-amber-50/80 p-3 text-amber-950', className)}
    >
      <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-amber-800">
        <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
        {title}
      </div>
      <ul className="mt-1.5 space-y-1 text-xs leading-relaxed">
        {warnings.map((warning, index) => (
          <li key={`${warning}-${index}`} className="flex gap-1.5">
            <span aria-hidden="true" className="text-amber-600">
              •
            </span>
            <span>
              <span className="font-mono text-[10px] font-bold">{warning}</span>
              <span className="text-amber-900/70"> — {warningText(warning)}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ helpers */

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatClock(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—';
  if (seconds < 1) return `${Math.max(0, Math.round(seconds * 1000))} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat().format(value);
}

export function displayDelimiter(delimiter: string): string {
  if (delimiter === '	') return 'tab';
  if (delimiter === ',') return 'comma';
  if (delimiter === ';') return 'semicolon';
  return delimiter || '—';
}

/* --------------------------------------------------------------------- meta */

export function DatasetMeta({ dataset }: { dataset: Dataset }) {
  const items: Array<{ label: string; value: ReactNode; mono?: boolean }> = [
    { label: 'dataset id', value: dataset.id, mono: true },
    { label: 'mode', value: dataset.mode, mono: true },
    { label: 'rows', value: dataset.rowCount === null ? 'unknown' : formatNumber(dataset.rowCount) },
    { label: 'size', value: formatBytes(dataset.byteSize) },
    { label: 'encoding', value: dataset.encoding, mono: true },
    { label: 'delimiter', value: displayDelimiter(dataset.delimiter) },
    { label: 'header', value: dataset.hasHeader ? 'yes' : 'no' },
    { label: 'columns', value: dataset.columns.join(' · '), mono: true },
    { label: 'created', value: formatDateTime(dataset.createdAt) },
  ];

  return (
    <div className="mt-4 rounded-xl border border-black/[0.08] bg-[#fcfcfc] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[#202020]">
          <Database className="h-3.5 w-3.5 text-[#76910a]" aria-hidden="true" />
          Saved dataset
        </div>
        <Badge tone={dataset.mode === 'manual' ? 'lime' : 'neutral'}>{dataset.mode}</Badge>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] md:grid-cols-4">
        {items.map((item) => (
          <div key={item.label} className="min-w-0">
            <dt className="font-semibold uppercase tracking-wider text-black/40">{item.label}</dt>
            <dd
              className={cx(
                'mt-0.5 break-words text-[#202020]',
                item.mono && 'font-mono text-[10px] leading-relaxed',
              )}
              title={typeof item.value === 'string' ? item.value : undefined}
            >
              {item.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/* -------------------------------------------------------------- pagination */

export function Pagination({
  offset,
  limit,
  total,
  onPage,
  disabled = false,
  noun = 'rows',
}: {
  offset: number;
  limit: number;
  total: number;
  onPage: (nextOffset: number) => void;
  disabled?: boolean;
  noun?: string;
}) {
  const from = total === 0 ? 0 : Math.min(offset + 1, total);
  const to = Math.min(offset + limit, total);
  const canPrev = offset > 0 && !disabled;
  const canNext = offset + limit < total && !disabled;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-[11px] text-black/50">
        {noun} <span className="font-semibold text-black/70">{formatNumber(from)}–{formatNumber(to)}</span> of{' '}
        <span className="font-semibold text-black/70">{formatNumber(total)}</span>
      </p>
      <div className="flex items-center gap-1.5">
        <Button size="sm" onClick={() => onPage(Math.max(0, offset - limit))} disabled={!canPrev}>
          Previous
        </Button>
        <Button size="sm" onClick={() => onPage(offset + limit)} disabled={!canNext}>
          Next
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------- misc */

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-black/50" role="status">
      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      {label ?? 'Loading…'}
    </span>
  );
}

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-black/15 bg-[#fcfcfc] px-4 py-8 text-center">
      {icon ? <div className="mb-2 text-black/25">{icon}</div> : null}
      <p className="text-xs font-bold text-black/60">{title}</p>
      {children ? <div className="mt-1 max-w-md text-[11px] leading-relaxed text-black/45">{children}</div> : null}
    </div>
  );
}

export function SuccessNote({ children }: { children: ReactNode }) {
  return (
    <p
      role="status"
      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-800"
    >
      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
      {children}
    </p>
  );
}
