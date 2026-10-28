'use client';

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Download,
  FileText,
  RotateCcw,
  Table2,
} from 'lucide-react';
import {
  JOB_STATUS_LABEL,
  resultsApi,
  type Paginated,
  type PreviewPage,
  type ResultRowError,
  type ResultSummary,
} from '@/lib/api';
import {
  Badge,
  Button,
  EmptyState,
  ErrorNotice,
  Pagination,
  Spinner,
  WarningList,
  cx,
  formatDuration,
  formatNumber,
  type BadgeTone,
} from './ui';

const RESULT_PAGE_SIZE = 20;
const ERROR_PAGE_SIZE = 10;

function summaryTone(status: ResultSummary['status'] | undefined): BadgeTone {
  if (status === 'succeeded') return 'green';
  if (status === 'failed' || status === 'cancelled') return 'red';
  return 'lime';
}

function SummaryCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-black/10 bg-white p-4">
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-black/45">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-display text-2xl font-black leading-tight text-[#202020]">{value}</div>
      {hint ? <p className="mt-0.5 text-[10px] text-black/40">{hint}</p> : null}
    </div>
  );
}

function CountCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | undefined;
  tone: 'green' | 'red' | 'amber' | 'neutral';
}) {
  const tones = {
    green: 'border-emerald-500/20 bg-emerald-50/70',
    red: 'border-red-500/20 bg-red-50/70',
    amber: 'border-amber-500/25 bg-amber-50/70',
    neutral: 'border-black/10 bg-[#fcfcfc]',
  } as const;
  return (
    <div className={cx('rounded-xl border p-3', tones[tone])}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-black/45">{label}</p>
      <p className="mt-0.5 font-display text-xl font-black text-[#202020]">{formatNumber(value ?? 0)}</p>
    </div>
  );
}

export interface ResultsViewProps {
  jobId: string;
  onNewRun: () => void;
}

export default function ResultsView({ jobId, onNewRun }: ResultsViewProps) {
  const [summary, setSummary] = useState<ResultSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState<unknown>(null);
  const [summaryNonce, setSummaryNonce] = useState(0);

  const [preview, setPreview] = useState<PreviewPage | null>(null);
  const [previewOffset, setPreviewOffset] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [previewNonce, setPreviewNonce] = useState(0);

  const [errorsPage, setErrorsPage] = useState<Paginated<ResultRowError> | null>(null);
  const [errorsOffset, setErrorsOffset] = useState(0);
  const [errorsLoading, setErrorsLoading] = useState(false);
  const [errorsError, setErrorsError] = useState<unknown>(null);
  const [errorsNonce, setErrorsNonce] = useState(0);

  useEffect(() => {
    let ignore = false;
    setSummaryLoading(true);
    setSummaryError(null);
    resultsApi
      .summary(jobId)
      .then((value) => {
        if (!ignore) setSummary(value);
      })
      .catch((error) => {
        if (!ignore) setSummaryError(error);
      })
      .finally(() => {
        if (!ignore) setSummaryLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [jobId, summaryNonce]);

  useEffect(() => {
    let ignore = false;
    setPreviewLoading(true);
    setPreviewError(null);
    resultsApi
      .preview(jobId, previewOffset, RESULT_PAGE_SIZE)
      .then((value) => {
        if (!ignore) setPreview(value);
      })
      .catch((error) => {
        if (!ignore) setPreviewError(error);
      })
      .finally(() => {
        if (!ignore) setPreviewLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [jobId, previewOffset, previewNonce]);

  useEffect(() => {
    let ignore = false;
    setErrorsLoading(true);
    setErrorsError(null);
    resultsApi
      .errors(jobId, errorsOffset, ERROR_PAGE_SIZE)
      .then((value) => {
        if (!ignore) setErrorsPage(value);
      })
      .catch((error) => {
        if (!ignore) setErrorsError(error);
      })
      .finally(() => {
        if (!ignore) setErrorsLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [jobId, errorsOffset, errorsNonce]);

  const canDownload = summary !== null && summary.status === 'succeeded' && summary.output != null;
  const warnings = summary?.warnings ?? [];
  const counts = summary?.counts;

  return (
    <div className="p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-black/[0.08] pb-4">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#76910a]">
            Stage 3 · Results
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            <h3 className="font-display text-base font-bold text-[#202020]">Result summary</h3>
            {summary ? (
              <Badge tone={summaryTone(summary.status)}>{JOB_STATUS_LABEL[summary.status]}</Badge>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {canDownload ? (
            <a
              href={resultsApi.csvUrl(jobId)} download={`result-${jobId}.csv`}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-transparent bg-[#d7f13b] px-3.5 py-2 text-xs font-bold tracking-wide text-[#202020] shadow-sm shadow-[#d7f13b]/30 transition-colors hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#9ebc19]/40 focus-visible:ring-offset-1"
              title="Download the validated output CSV; the session cookie travels with this navigation"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" /> Download CSV
            </a>
          ) : (
            <Button variant="accent" disabled title="The validated output CSV is not available">
              <Download className="h-3.5 w-3.5" aria-hidden="true" /> Download CSV
            </Button>
          )}
          <Button variant="dark" onClick={onNewRun}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> New run
          </Button>
        </div>
      </div>

      {summaryError ? (
        <ErrorNotice
          className="mt-3"
          error={summaryError}
          onRetry={() => setSummaryNonce((value) => value + 1)}
          retryLabel="Reload summary"
        />
      ) : null}

      {summaryLoading && !summary ? (
        <div className="flex min-h-[10rem] items-center justify-center">
          <Spinner label="Loading result summary…" />
        </div>
      ) : null}

      {summary ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard
              icon={<CheckCircle2 className="h-3 w-3" aria-hidden="true" />}
              label="Status"
              value={JOB_STATUS_LABEL[summary.status]}
              hint={summary.failureReason ?? undefined}
            />
            <SummaryCard
              icon={<Clock className="h-3 w-3" aria-hidden="true" />}
              label="Duration"
              value={formatDuration(summary.durationSeconds)}
            />
            <SummaryCard
              icon={<Table2 className="h-3 w-3" aria-hidden="true" />}
              label="Total rows"
              value={formatNumber(summary.totalRows)}
            />
            <SummaryCard
              icon={<AlertTriangle className="h-3 w-3" aria-hidden="true" />}
              label="Row errors"
              value={formatNumber(summary.errorsCount)}
            />
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2">
            <CountCard label="true" value={counts?.true} tone="green" />
            <CountCard label="false" value={counts?.false} tone="red" />
            <CountCard label="unsure" value={counts?.unsure} tone="amber" />
          </div>

          {summary.failureReason ? (
            <div className="mt-3 rounded-xl border border-red-500/25 bg-red-50/80 p-3 text-xs text-red-900">
              <span className="font-bold">Failure reason: </span>
              <span>{summary.failureReason}</span>
            </div>
          ) : null}

          <WarningList warnings={warnings} className="mt-3" />

          <div className="mt-4 rounded-2xl border border-black/[0.08] bg-[#fcfcfc]">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/[0.08] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <FileText className="h-4 w-4 text-[#76910a]" aria-hidden="true" />
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-black/50">
                  Output preview
                </h4>
                <Badge tone="neutral">read-only</Badge>
                {previewLoading ? <Spinner label="Loading page…" /> : null}
              </div>
              {preview ? (
                <span className="font-mono text-[10px] text-black/35">
                  {preview.columns.length} columns · {formatNumber(preview.total)} rows
                </span>
              ) : null}
            </div>

            {previewError ? (
              <div className="p-3">
                <ErrorNotice
                  error={previewError}
                  onRetry={() => setPreviewNonce((value) => value + 1)}
                  retryLabel="Reload preview"
                />
              </div>
            ) : null}

            {preview ? (
              <>
                <div className="overflow-x-auto bg-white">
                  <table className="w-full min-w-[720px] border-collapse text-left text-xs">
                    <caption className="sr-only">Paginated preview of the output CSV, read-only</caption>
                    <thead className="bg-[#f7f7f7] text-[10px] uppercase tracking-wider text-black/50">
                      <tr>
                        <th scope="col" className="w-12 border-b border-black/[0.08] px-3 py-2 font-semibold">
                          #
                        </th>
                        {preview.columns.map((column) => (
                          <th
                            key={column}
                            scope="col"
                            className="border-b border-black/[0.08] px-3 py-2 font-semibold"
                          >
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-black/[0.06]">
                      {preview.rows.length === 0 ? (
                        <tr>
                          <td
                            colSpan={preview.columns.length + 1}
                            className="px-4 py-8 text-center text-[11px] text-black/45"
                          >
                            The output has no rows.
                          </td>
                        </tr>
                      ) : null}
                      {preview.rows.map((row, rowIndex) => (
                        <tr key={preview.offset + rowIndex} className="align-top hover:bg-black/[0.015]">
                          <td className="px-3 py-2 font-mono text-[10px] text-black/35">
                            {preview.offset + rowIndex + 1}
                          </td>
                          {preview.columns.map((column, columnIndex) => (
                            <td key={column} className="max-w-[28rem] px-3 py-2 text-black/75">
                              <span className="line-clamp-3 break-words">{row[columnIndex] ?? ''}</span>
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="border-t border-black/[0.06] p-3">
                  <Pagination
                    offset={preview.offset}
                    limit={preview.limit}
                    total={preview.total}
                    onPage={(nextOffset) => setPreviewOffset(nextOffset)}
                    disabled={previewLoading}
                  />
                </div>
              </>
            ) : !previewError ? (
              <div className="p-6">
                <Spinner label="Loading output preview…" />
              </div>
            ) : null}
          </div>

          <div
            className={
              'mt-4 rounded-2xl border border-black/[0.08] bg-[#fcfcfc]' +
              (summary.errorsCount === 0 ? ' hidden' : '')
            }
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/[0.08] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600" aria-hidden="true" />
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-black/50">
                  Row errors
                </h4>
                <Badge tone={summary.errorsCount > 0 ? 'amber' : 'green'}>
                  {summary.errorsCount > 0 ? summary.errorsCount + ' total' : 'none'}
                </Badge>
                {errorsLoading ? <Spinner label="Loading page…" /> : null}
              </div>
            </div>

            {errorsError ? (
              <div className="p-3">
                <ErrorNotice
                  error={errorsError}
                  onRetry={() => setErrorsNonce((value) => value + 1)}
                  retryLabel="Reload errors"
                />
              </div>
            ) : null}

            {errorsPage ? (
              <>
                {errorsPage.items.length === 0 ? (
                  <div className="p-4">
                    <EmptyState
                      icon={<CheckCircle2 className="h-5 w-5 text-emerald-500" />}
                      title="No row errors"
                    >
                      Every row produced a structured label. Row-level errors would appear here with
                      their rowId, line number and code.
                    </EmptyState>
                  </div>
                ) : (
                  <div className="overflow-x-auto bg-white">
                    <table className="w-full min-w-[720px] border-collapse text-left text-xs">
                      <caption className="sr-only">Paginated list of row-level technical errors</caption>
                      <thead className="bg-[#f7f7f7] text-[10px] uppercase tracking-wider text-black/50">
                        <tr>
                          <th scope="col" className="border-b border-black/[0.08] px-3 py-2 font-semibold">
                            rowId
                          </th>
                          <th scope="col" className="w-20 border-b border-black/[0.08] px-3 py-2 font-semibold">
                            line
                          </th>
                          <th scope="col" className="w-28 border-b border-black/[0.08] px-3 py-2 font-semibold">
                            column
                          </th>
                          <th scope="col" className="w-36 border-b border-black/[0.08] px-3 py-2 font-semibold">
                            code
                          </th>
                          <th scope="col" className="border-b border-black/[0.08] px-3 py-2 font-semibold">
                            message
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-black/[0.06]">
                        {errorsPage.items.map((rowError, index) => (
                          <tr
                            key={errorsPage.offset + index}
                            className="align-top hover:bg-black/[0.015]"
                          >
                            <td className="px-3 py-2 font-mono text-[10px] text-[#76910a]">
                              {rowError.rowId}
                            </td>
                            <td className="px-3 py-2 font-mono text-[10px] text-black/55">
                              {rowError.lineNumber ?? '—'}
                            </td>
                            <td className="px-3 py-2 font-mono text-[10px] text-black/55">
                              {rowError.column ?? '—'}
                            </td>
                            <td className="px-3 py-2 font-mono text-[10px] font-bold text-red-700">
                              {rowError.code}
                            </td>
                            <td className="max-w-[28rem] px-3 py-2 text-black/70">
                              <span className="break-words">{rowError.message}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="border-t border-black/[0.06] p-3">
                  <Pagination
                    offset={errorsPage.offset}
                    limit={errorsPage.limit}
                    total={errorsPage.total}
                    onPage={(nextOffset) => setErrorsOffset(nextOffset)}
                    disabled={errorsLoading}
                    noun="errors"
                  />
                </div>
              </>
            ) : !errorsError ? (
              <div className="p-6">
                <Spinner label="Loading row errors…" />
              </div>
            ) : null}
          </div>

        </>
      ) : null}
    </div>
  );
}