'use client';

import { useState } from 'react';
import { Table2, UploadCloud } from 'lucide-react';
import type { Dataset } from '@/lib/api';
import ManualEditor from './ManualEditor';
import ManualRun from './ManualRun';
import BulkUpload from './BulkUpload';
import MappingPanel from './MappingPanel';
import { ErrorNotice, Spinner, cx } from './ui';

type Mode = 'manual' | 'bulk';

export interface DataStageProps {
  active: boolean;
  sessionReady: boolean;
  sessionError: unknown;
  onRetrySession: () => void;
  onJobStarted: (jobId: string) => void;
}

export default function DataStage({
  active,
  sessionReady,
  sessionError,
  onRetrySession,
  onJobStarted,
}: DataStageProps) {
  const [mode, setMode] = useState<Mode>('manual');
  const [manualDataset, setManualDataset] = useState<Dataset | null>(null);
  const [bulkDataset, setBulkDataset] = useState<Dataset | null>(null);

  function handleDatasetUpdated(updated: Dataset) {
    if (updated.mode === 'manual') setManualDataset(updated);
    else setBulkDataset(updated);
  }

  return (
    <div className="p-4 md:p-6">
      <div
        role="tablist"
        aria-label="Input mode"
        className="inline-flex items-center gap-1 rounded-full border border-black/10 bg-black/[0.03] p-1"
      >
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'manual'}
          onClick={() => setMode('manual')}
          className={cx(
            'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-bold transition-colors',
            mode === 'manual' ? 'bg-[#d7f13b] text-[#202020] shadow-sm shadow-[#d7f13b]/30' : 'text-black/55 hover:text-[#202020]',
          )}
        >
          <Table2 className="h-3.5 w-3.5" aria-hidden="true" /> Manual
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'bulk'}
          onClick={() => setMode('bulk')}
          className={cx(
            'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-bold transition-colors',
            mode === 'bulk' ? 'bg-[#d7f13b] text-[#202020] shadow-sm shadow-[#d7f13b]/30' : 'text-black/55 hover:text-[#202020]',
          )}
        >
          <UploadCloud className="h-3.5 w-3.5" aria-hidden="true" /> Bulk
        </button>
      </div>

      {!sessionReady && !sessionError ? (<Spinner label="Connecting…" />) : null}

      {sessionError ? (
        <ErrorNotice
          className="mt-3"
          error={sessionError}
          onRetry={onRetrySession}
          retryLabel="Retry"
        />
      ) : null}

      <div className="mt-4">
        <div role="tabpanel" hidden={mode !== 'manual'}>
          <ManualEditor
            dataset={manualDataset}
            active={active && mode === 'manual'}
            sessionReady={sessionReady}
            onSaved={setManualDataset}
          />
          {manualDataset ? <ManualRun dataset={manualDataset} onJobStarted={onJobStarted} /> : null}
        </div>

        <div role="tabpanel" hidden={mode !== 'bulk'}>
          <BulkUpload dataset={bulkDataset} sessionReady={sessionReady} onUploaded={setBulkDataset} />
          {bulkDataset ? (
            <MappingPanel
              dataset={bulkDataset}
              sessionReady={sessionReady}
              onDatasetUpdated={handleDatasetUpdated}
              onJobStarted={onJobStarted}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
