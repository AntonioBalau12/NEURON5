'use client';

import { useRef, useState } from 'react';
import { Play } from 'lucide-react';
import { isApiError, isRecord, jobsApi, makeIdempotencyKey, type Dataset } from '@/lib/api';
import { Button, ErrorNotice } from './ui';

export interface ManualRunProps {
  dataset: Dataset;
  onJobStarted: (jobId: string) => void;
}

/** Minimal "ready to run" bar for a saved manual dataset. */
export default function ManualRun({ dataset, onJobStarted }: ManualRunProps) {
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const keyRef = useRef<string | null>(null);

  async function start() {
    if (processing) return;
    setProcessing(true);
    setError(null);
    setActiveJobId(null);
    const retrying = error !== null && keyRef.current !== null;
    const key = retrying && keyRef.current ? keyRef.current : makeIdempotencyKey();
    keyRef.current = key;
    try {
      const response = await jobsApi.create(dataset.id, key);
      onJobStarted(response.job.id);
    } catch (caught) {
      setError(caught);
      if (isApiError(caught)) {
        if (caught.code === 'IDEMPOTENCY_CONFLICT') keyRef.current = null;
        if (caught.code === 'JOB_ALREADY_RUNNING' && isRecord(caught.details)) {
          const candidate = caught.details.activeJobId;
          if (typeof candidate === 'string' && candidate.length > 0) setActiveJobId(candidate);
        }
      }
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div className="mt-4 border-t border-black/[0.08] pt-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-black/50">Draft saved.</p>
        <Button variant="primary" onClick={start} loading={processing}>
          <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" /> Process
        </Button>
      </div>
      {error ? (
        <ErrorNotice
          className="mt-3"
          error={error}
          onRetry={start}
          retryLabel="Retry"
          retryDisabled={processing}
          onDismiss={() => setError(null)}
          action={
            activeJobId ? (
              <Button
                size="sm"
                variant="accent"
                onClick={() => {
                  setError(null);
                  onJobStarted(activeJobId);
                }}
              >
                Open running job
              </Button>
            ) : undefined
          }
        />
      ) : null}
    </div>
  );
}
