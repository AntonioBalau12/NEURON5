'use client';

import { useEffect, useState } from 'react';
import { FileSpreadsheet, FileUp, Upload } from 'lucide-react';
import {
  datasetsApi,
  type BulkDelimiter,
  type Dataset,
  type PreviewPage,
} from '@/lib/api';
import {
  Badge,
  Button,
  DatasetMeta,
  EmptyState,
  ErrorNotice,
  Pagination,
  Spinner,
  WarningList,
  cx,
  formatBytes,
} from './ui';

const MAX_BYTES = 10 * 1024 * 1024;
const PAGE_SIZE = 10;
const TAB = String.fromCharCode(9);

type DelimiterChoice = 'auto' | ',' | ';' | 'tab';

function toDelimiter(choice: DelimiterChoice): BulkDelimiter | undefined {
  if (choice === 'auto') return undefined;
  if (choice === 'tab') return TAB as BulkDelimiter;
  return choice;
}

export interface BulkUploadProps {
  dataset: Dataset | null;
  sessionReady: boolean;
  onUploaded: (dataset: Dataset) => void;
}

export default function BulkUpload({ dataset, sessionReady, onUploaded }: BulkUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [delimiterChoice, setDelimiterChoice] = useState<DelimiterChoice>('auto');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [preview, setPreview] = useState<PreviewPage | null>(null);
  const [previewOffset, setPreviewOffset] = useState(0);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [previewNonce, setPreviewNonce] = useState(0);

  const datasetId = dataset?.id ?? null;

  useEffect(() => {
    setPreview(null);
    setPreviewError(null);
  }, [datasetId]);

  useEffect(() => {
    if (!datasetId) {
      setPreview(null);
      return;
    }
    let ignore = false;
    setPreviewLoading(true);
    setPreviewError(null);
    datasetsApi
      .preview(datasetId, previewOffset, PAGE_SIZE)
      .then((page) => {
        if (!ignore) setPreview(page);
      })
      .catch((requestError) => {
        if (!ignore) setPreviewError(requestError);
      })
      .finally(() => {
        if (!ignore) setPreviewLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [datasetId, previewOffset, previewNonce]);

  function selectFile(next: File | null) {
    setError(null);
    if (!next) {
      setFile(null);
      return;
    }
    if (!next.name.toLowerCase().endsWith('.csv')) {
      setFile(null);
      setError({
        code: 'INVALID_CSV',
        message: 'Choose a .csv file. The bulk endpoint accepts exactly one CSV upload.',
      });
      return;
    }
    if (next.size > MAX_BYTES) {
      setFile(null);
      setError({
        code: 'DATASET_TOO_LARGE',
        message: 'The file is ' + formatBytes(next.size) + '; the maximum upload size is 10 MB.',
      });
      return;
    }
    setFile(next);
  }

  async function handleUpload() {
    if (!file || uploading || !sessionReady) return;
    setUploading(true);
    setError(null);
    try {
      const saved = await datasetsApi.uploadBulk(file, toDelimiter(delimiterChoice));
      setPreviewOffset(0);
      onUploaded(saved);
    } catch (uploadError) {
      setError(uploadError);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-sm font-bold text-[#202020]">Bulk CSV upload</h3>
          <p className="mt-0.5 text-[11px] leading-relaxed text-black/50">
            One immutable snapshot, UTF-8 with optional BOM. The first row is the header. Nothing is
            edited client-side.
          </p>
        </div>
        <Badge tone="neutral">max 10 MB</Badge>
      </div>

      <div className="mt-3 rounded-xl border border-dashed border-black/15 bg-[#fcfcfc] p-4">
        <div className="flex flex-wrap items-center gap-3">
          <label
            className={cx(
              'inline-flex cursor-pointer items-center gap-2 rounded-xl bg-[#202020] px-3.5 py-2 text-xs font-bold text-white transition-colors hover:bg-black',
              'focus-within:outline-none focus-within:ring-2 focus-within:ring-[#9ebc19]/40 focus-within:ring-offset-2',
              uploading && 'pointer-events-none opacity-60',
            )}
          >
            <FileUp className="h-3.5 w-3.5" aria-hidden="true" />
            {file ? 'Choose another CSV' : 'Choose CSV'}
            <input
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              disabled={uploading}
              onChange={(event) => {
                const next = event.target.files?.[0] ?? null;
                selectFile(next);
                event.target.value = '';
              }}
            />
          </label>

          <div className="min-w-0 flex-1">
            {file ? (
              <div className="flex min-w-0 items-center gap-2">
                <FileSpreadsheet className="h-4 w-4 shrink-0 text-[#76910a]" aria-hidden="true" />
                <span className="truncate font-mono text-[11px] text-[#202020]" title={file.name}>
                  {file.name}
                </span>
                <span className="shrink-0 text-[10px] text-black/40">{formatBytes(file.size)}</span>
              </div>
            ) : (
              <p className="text-[11px] text-black/45">No file selected · .csv only · size checked in the browser</p>
            )}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-[11px] text-black/55">
            <span className="mb-1 block font-semibold uppercase tracking-wider text-black/40">Delimiter</span>
            <select
              value={delimiterChoice}
              onChange={(event) => setDelimiterChoice(event.target.value as DelimiterChoice)}
              disabled={uploading}
              className="min-w-[9rem] rounded-lg border border-black/10 bg-white px-2.5 py-1.5 text-[11px] text-[#202020] outline-none focus:border-[#9ebc19]/50 focus:ring-2 focus:ring-[#9ebc19]/15 disabled:opacity-50"
            >
              <option value="auto">Auto-detect</option>
              <option value=",">Comma (,)</option>
              <option value=";">Semicolon (;)</option>
              <option value="tab">Tab</option>
            </select>
          </label>

          <Button
            variant="primary"
            onClick={handleUpload}
            loading={uploading}
            disabled={!file || !sessionReady}
            title={sessionReady ? 'Upload the selected CSV' : 'Waiting for the API session'}
          >
            <Upload className="h-3.5 w-3.5" aria-hidden="true" /> Upload CSV
          </Button>

          {file && !uploading ? (
            <Button variant="ghost" onClick={() => selectFile(null)}>
              Clear file
            </Button>
          ) : null}
        </div>

        {uploading ? (
          <div className="mt-3" role="progressbar" aria-label="Uploading CSV" aria-valuetext="Uploading">
            <div className="h-1.5 overflow-hidden rounded-full bg-black/10">
              <div className="h-full w-1/2 animate-pulse rounded-full bg-[#d7f13b]" />
            </div>
            <p className="mt-1 text-[10px] text-black/40">Uploading and parsing on the server…</p>
          </div>
        ) : null}

        {!sessionReady && file ? (
          <p className="mt-2 text-[11px] text-amber-700">
            Upload unlocks as soon as the anonymous session is ready.
          </p>
        ) : null}
      </div>

      {error ? (
        <ErrorNotice
          className="mt-3"
          error={error}
          onRetry={file ? handleUpload : undefined}
          retryLabel="Retry upload"
          retryDisabled={uploading || !sessionReady}
          onDismiss={() => setError(null)}
        />
      ) : null}

      {dataset ? (
        <>
          <DatasetMeta dataset={dataset} />
          <WarningList warnings={dataset.warnings} className="mt-3" />
        </>
      ) : null}

      <div className="mt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-black/50">Preview</h4>
            <Badge tone="neutral">read-only</Badge>
            {previewLoading ? <Spinner label="Loading page…" /> : null}
          </div>
          {preview ? (
            <span className="font-mono text-[10px] text-black/35">
              {preview.columns.length} columns · {preview.total} rows
            </span>
          ) : null}
        </div>

        {!dataset ? (
          <EmptyState icon={<FileSpreadsheet className="h-5 w-5" />} title="No bulk dataset yet">
            Upload a CSV to inspect the server-side paginated preview before choosing the text
            column.
          </EmptyState>
        ) : previewError ? (
          <ErrorNotice
            className="mt-2"
            error={previewError}
            onRetry={() => setPreviewNonce((value) => value + 1)}
            retryLabel="Reload preview"
          />
        ) : preview ? (
          <div className="mt-2">
            <div className="overflow-x-auto rounded-xl border border-black/[0.08]">
              <table className="w-full min-w-[640px] border-collapse text-left text-xs">
                <caption className="sr-only">Paginated preview of the uploaded CSV</caption>
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
                        The dataset has no data rows.
                      </td>
                    </tr>
                  ) : null}
                  {preview.rows.map((row, rowIndex) => (
                    <tr key={preview.offset + rowIndex} className="align-top hover:bg-black/[0.015]">
                      <td className="px-3 py-2 font-mono text-[10px] text-black/35">
                        {preview.offset + rowIndex + 1}
                      </td>
                      {preview.columns.map((column, columnIndex) => (
                        <td key={column} className="max-w-[30rem] px-3 py-2 text-black/75">
                          <span className="line-clamp-3 break-words">{row[columnIndex] ?? ''}</span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2">
              <Pagination
                offset={preview.offset}
                limit={preview.limit}
                total={preview.total}
                onPage={(nextOffset) => setPreviewOffset(nextOffset)}
                disabled={previewLoading}
              />
            </div>
          </div>
        ) : (
          <div className="mt-2">
            <Spinner label="Loading preview…" />
          </div>
        )}
      </div>
    </div>
  );
}
