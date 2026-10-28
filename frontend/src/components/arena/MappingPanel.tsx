'use client';

import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Play, SlidersHorizontal } from 'lucide-react';
import {
  datasetsApi,
  isApiError,
  isRecord,
  jobsApi,
  makeIdempotencyKey,
  type Dataset,
  type DatasetMappingInput,
} from '@/lib/api';
import { Badge, Button, ErrorNotice, SuccessNote, cx } from './ui';

const TEXT_CANDIDATES = ['text', 'sentence', 'proposition', 'claim', 'content'];
const DATE_CANDIDATES = ['date', 'timestamp', 'day'];
const ID_CANDIDATES = ['id'];

function guessColumn(columns: string[], candidates: string[]): string | null {
  const lowered = columns.map((column) => column.toLowerCase());
  for (const candidate of candidates) {
    const index = lowered.indexOf(candidate);
    if (index >= 0) return columns[index];
  }
  return null;
}

function initialMapping(dataset: Dataset): DatasetMappingInput {
  const mapping = dataset.mapping;
  return {
    textColumn:
      mapping?.textColumn ?? guessColumn(dataset.columns, TEXT_CANDIDATES) ?? dataset.columns[0] ?? '',
    dateColumn: mapping?.dateColumn ?? guessColumn(dataset.columns, DATE_CANDIDATES),
    idColumn: mapping?.idColumn ?? guessColumn(dataset.columns, ID_CANDIDATES),
    resultColumn: mapping?.resultColumn ?? 'label',
  };
}

export interface MappingPanelProps {
  dataset: Dataset;
  sessionReady: boolean;
  onDatasetUpdated: (dataset: Dataset) => void;
  onJobStarted: (jobId: string) => void;
}

export default function MappingPanel({
  dataset,
  sessionReady,
  onDatasetUpdated,
  onJobStarted,
}: MappingPanelProps) {
  const initial = initialMapping(dataset);
  const [textColumn, setTextColumn] = useState(initial.textColumn);
  const [dateColumn, setDateColumn] = useState(initial.dateColumn ?? '');
  const [idColumn, setIdColumn] = useState(initial.idColumn ?? '');
  const [resultColumn, setResultColumn] = useState(initial.resultColumn);

  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<unknown>(null);
  const [processError, setProcessError] = useState<unknown>(null);
  const [processing, setProcessing] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const processKeyRef = useRef<string | null>(null);
  const processingRef = useRef(false);
  const mappingSignature = dataset.mapping
    ? JSON.stringify(dataset.mapping)
    : 'no-mapping';

  useEffect(() => {
    const next = initialMapping(dataset);
    setTextColumn(next.textColumn);
    setDateColumn(next.dateColumn ?? '');
    setIdColumn(next.idColumn ?? '');
    setResultColumn(next.resultColumn);
    setConfirmError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset.id, mappingSignature]);

  useEffect(() => {
    processKeyRef.current = null;
    setProcessError(null);
    setActiveJobId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset.id]);

  const confirmed = dataset.mapping?.confirmed === true;
  const trimmedResult = resultColumn.trim();
  const resultValid = trimmedResult.length > 0 && trimmedResult.length <= 64;
  const missingText = textColumn.length === 0;
  const mappingDirty =
    !dataset.mapping ||
    dataset.mapping.textColumn !== textColumn ||
    (dataset.mapping.dateColumn ?? '') !== dateColumn ||
    (dataset.mapping.idColumn ?? '') !== idColumn ||
    dataset.mapping.resultColumn !== trimmedResult;
  const canConfirm = !confirming && !missingText && resultValid && (!confirmed || mappingDirty);
  const canProcess = confirmed && sessionReady && !mappingDirty;

  async function handleConfirm() {
    if (confirming || !canConfirm) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const body: DatasetMappingInput = {
        textColumn,
        dateColumn: dateColumn || null,
        idColumn: idColumn || null,
        resultColumn: trimmedResult,
      };
      const updated = await datasetsApi.updateMapping(dataset.id, body);
      onDatasetUpdated(updated);
    } catch (error) {
      setConfirmError(error);
    } finally {
      setConfirming(false);
    }
  }

  async function handleProcess() {
    if (processingRef.current || !canProcess) return;
    processingRef.current = true;
    setProcessing(true);
    setProcessError(null);
    setActiveJobId(null);
    const retryingSameAttempt = processError !== null && processKeyRef.current !== null;
    const key =
      retryingSameAttempt && processKeyRef.current ? processKeyRef.current : makeIdempotencyKey();
    processKeyRef.current = key;
    try {
      const response = await jobsApi.create(dataset.id, key);
      onJobStarted(response.job.id);
    } catch (error) {
      setProcessError(error);
      if (isApiError(error)) {
        if (error.code === 'IDEMPOTENCY_CONFLICT') processKeyRef.current = null;
        if (error.code === 'JOB_ALREADY_RUNNING' && isRecord(error.details)) {
          const candidate = error.details.activeJobId;
          if (typeof candidate === 'string' && candidate.length > 0) setActiveJobId(candidate);
        }
      }
    } finally {
      processingRef.current = false;
      setProcessing(false);
    }
  }

  return (
    <div className="mt-5 rounded-2xl border border-black/10 bg-white p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-xl bg-[#e6effa] text-[#1d6dd7]">
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h3 className="font-display text-sm font-bold text-[#202020]">Column mapping</h3>
            <p className="mt-0.5 max-w-xl text-[11px] leading-relaxed text-black/50">
              The text column is required. The result column is overwritten when it already exists,
              otherwise it is appended to the output CSV. Mapping freezes once a job is created.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {dataset.mapping?.autoDetected ? <Badge tone="blue">auto-detected</Badge> : null}
          {confirmed ? (
            <Badge tone="green">confirmed</Badge>
          ) : (
            <Badge tone="amber">required before processing</Badge>
          )}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div>
          <label
            htmlFor="mapping-text-column"
            className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-black/45"
          >
            Text column <span className="text-red-500">*</span>
          </label>
          <select
            id="mapping-text-column"
            value={textColumn}
            onChange={(event) => setTextColumn(event.target.value)}
            aria-required="true"
            className={cx(
              'w-full rounded-lg border bg-white px-2.5 py-2 font-mono text-[11px] text-[#202020] outline-none focus:ring-2 focus:ring-[#1d6dd7]/15',
              missingText ? 'border-red-400' : 'border-black/10 focus:border-[#1d6dd7]/50',
            )}
          >
            <option value="">Select a column…</option>
            {dataset.columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label
            htmlFor="mapping-date-column"
            className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-black/45"
          >
            Date column <span className="font-normal normal-case text-black/30">(optional)</span>
          </label>
          <select
            id="mapping-date-column"
            value={dateColumn}
            onChange={(event) => setDateColumn(event.target.value)}
            className="w-full rounded-lg border border-black/10 bg-white px-2.5 py-2 font-mono text-[11px] text-[#202020] outline-none focus:border-[#1d6dd7]/50 focus:ring-2 focus:ring-[#1d6dd7]/15"
          >
            <option value="">— none —</option>
            {dataset.columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[10px] text-black/35">yyyy-mm-dd; invalid dates become row errors.</p>
        </div>

        <div>
          <label
            htmlFor="mapping-id-column"
            className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-black/45"
          >
            Id column <span className="font-normal normal-case text-black/30">(optional)</span>
          </label>
          <select
            id="mapping-id-column"
            value={idColumn}
            onChange={(event) => setIdColumn(event.target.value)}
            className="w-full rounded-lg border border-black/10 bg-white px-2.5 py-2 font-mono text-[11px] text-[#202020] outline-none focus:border-[#1d6dd7]/50 focus:ring-2 focus:ring-[#1d6dd7]/15"
          >
            <option value="">— none (r-&lt;index&gt;) —</option>
            {dataset.columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[10px] text-black/35">Stable row ids when supplied.</p>
        </div>

        <div>
          <label
            htmlFor="mapping-result-column"
            className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-black/45"
          >
            Result column <span className="text-red-500">*</span>
          </label>
          <input
            id="mapping-result-column"
            value={resultColumn}
            onChange={(event) => setResultColumn(event.target.value)}
            maxLength={64}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={!resultValid}
            className={cx(
              'w-full rounded-lg border bg-white px-2.5 py-2 font-mono text-[11px] text-[#202020] outline-none focus:ring-2 focus:ring-[#1d6dd7]/15',
              resultValid ? 'border-black/10 focus:border-[#1d6dd7]/50' : 'border-red-400',
            )}
          />
          <p className="mt-1 text-[10px] text-black/35">
            {!resultValid
              ? 'A result column name is required (max 64 characters).'
              : 'Existing name is overwritten; a new name is appended.'}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[10px] text-black/40">
          {mappingDirty
            ? 'Mapping changes are not saved until you confirm.'
            : 'Mapping matches the saved dataset.'}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {confirmed && !mappingDirty ? (
            <SuccessNote>
              <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> Mapping confirmed
            </SuccessNote>
          ) : null}
          <Button
            size="sm"
            variant="dark"
            onClick={handleConfirm}
            loading={confirming}
            disabled={!canConfirm || !sessionReady}
            title={sessionReady ? 'Save and confirm the mapping' : 'Waiting for the API session'}
          >
            {confirmed && mappingDirty ? 'Update mapping' : 'Confirm mapping'}
          </Button>
        </div>
      </div>

      {confirmError ? (
        <ErrorNotice
          className="mt-3"
          error={confirmError}
          onRetry={handleConfirm}
          retryLabel="Retry confirm"
          retryDisabled={confirming || !sessionReady}
          onDismiss={() => setConfirmError(null)}
        />
      ) : null}

      {processError ? (
        <ErrorNotice
          className="mt-3"
          error={processError}
          onRetry={handleProcess}
          retryLabel="Retry processing"
          retryDisabled={processing || !canProcess}
          onDismiss={() => setProcessError(null)}
          action={
            activeJobId ? (
              <Button
                size="sm"
                variant="accent"
                onClick={() => {
                  setProcessError(null);
                  setActiveJobId(null);
                  onJobStarted(activeJobId);
                }}
              >
                Open running job
              </Button>
            ) : undefined
          }
        />
      ) : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-black/[0.08] pt-4">
        <div>
          <p className="text-xs font-bold text-[#202020]">Start processing</p>
          <p className="mt-0.5 max-w-xl text-[11px] leading-relaxed text-black/50">
            Sends the confirmed mapping to the processor. Each attempt gets an Idempotency-Key, so a
            double click cannot create two jobs; retrying a failed attempt reuses the same key.
          </p>
          <p className="mt-1 break-all font-mono text-[10px] text-black/35">
            dataset {dataset.id}
            {dataset.rowCount !== null ? ' · ' + dataset.rowCount + ' rows' : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {confirmed ? <Badge tone="green">ready</Badge> : <Badge tone="amber">mapping required</Badge>}
          <Button
            variant="primary"
            onClick={handleProcess}
            loading={processing}
            disabled={!canProcess}
            title={
              !confirmed
                ? 'Confirm the mapping first'
                : mappingDirty
                  ? 'Confirm the updated mapping first'
                  : 'Create the job and open the live log'
            }
          >
            <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
            {processing ? 'Starting…' : processError ? 'Retry processing' : 'Process dataset'}
          </Button>
        </div>
      </div>
    </div>
  );
}
