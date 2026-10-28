'use client';

import { useEffect, useState } from 'react';
import { Check, ChevronRight } from 'lucide-react';
import Mascot from './Mascot';
import DataStage from './arena/DataStage';
import ProcessingView from './arena/ProcessingView';
import ResultsView from './arena/ResultsView';
import { ensureSession, type Job, type SessionInfo } from '@/lib/api';

type Stage = 1 | 2 | 3;

interface SessionState {
  status: 'loading' | 'ready' | 'error';
  info?: SessionInfo;
  error?: unknown;
}

const STEPS: Array<{ number: Stage; label: string }> = [
  { number: 1, label: 'Data' },
  { number: 2, label: 'Processing' },
  { number: 3, label: 'Results' },
];

export default function Studio() {
  const [stage, setStage] = useState<Stage>(1);
  const [session, setSession] = useState<SessionState>({ status: 'loading' });
  const [sessionNonce, setSessionNonce] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [resultReady, setResultReady] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setSession({ status: 'loading' });
    ensureSession()
      .then((info) => {
        if (alive) setSession({ status: 'ready', info });
      })
      .catch((error) => {
        if (alive) setSession({ status: 'error', error });
      });
    return () => {
      alive = false;
    };
  }, [sessionNonce]);

  const sessionReady = session.status === 'ready';

  function handleJobStarted(id: string) {
    setJobId(id);
    setResultReady(false);
    setStage(2);
  }

  function handleJobSucceeded(job: Job) {
    setJobId(job.id);
    if (!resultReady) {
      setResultReady(true);
      setStage(3);
    }
  }

  function handleNewRun() {
    setStage(1);
    setJobId(null);
    setResultReady(false);
    setResetKey((value) => value + 1);
  }

  function canOpen(target: Stage): boolean {
    if (target === 1) return true;
    if (target === 2) return jobId !== null;
    return jobId !== null && resultReady;
  }

  function goToStage(target: Stage) {
    if (canOpen(target)) setStage(target);
  }

  return (
    <main className="relative z-10 flex min-h-0 w-full flex-1 flex-col items-center overflow-hidden pt-2">
      <ol
        aria-label="Run stages"
        className="relative z-20 mb-2 flex shrink-0 flex-wrap items-center justify-center gap-2 rounded-full border border-black/[0.08] bg-white px-2 py-1.5 shadow-[0_2px_10px_rgba(0,0,0,0.04)]"
      >
        {STEPS.map((step, index) => {
          const state = stage === step.number ? 'current' : stage > step.number ? 'done' : 'upcoming';
          const enabled = canOpen(step.number);
          return (
            <li key={step.number} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => goToStage(step.number)}
                disabled={!enabled}
                aria-current={state === 'current' ? 'step' : undefined}
                aria-disabled={!enabled}
                className={
                  'inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold transition-colors ' +
                  (state === 'current'
                    ? 'bg-[#1d6dd7] text-white'
                    : state === 'done'
                      ? 'text-[#1d6dd7] hover:bg-[#e6effa]'
                      : 'text-[#202020]/45') +
                  (enabled ? ' cursor-pointer' : ' cursor-not-allowed opacity-60')
                }
              >
                <span
                  aria-hidden="true"
                  className={
                    'inline-flex h-4 w-4 items-center justify-center rounded-full text-[9px] ' +
                    (state === 'current'
                      ? 'bg-white/20 text-white'
                      : state === 'done'
                        ? 'bg-[#e6effa] text-[#1d6dd7]'
                        : 'bg-black/[0.04] text-black/40')
                  }
                >
                  {state === 'done' ? <Check className="h-2.5 w-2.5" /> : step.number}
                </span>
                <span>{step.label}</span>
              </button>
              {index < STEPS.length - 1 ? (
                <ChevronRight className="h-3.5 w-3.5 text-black/20" aria-hidden="true" />
              ) : null}
            </li>
          );
        })}
      </ol>

      <section className="relative z-20 flex min-h-0 w-[94vw] max-w-[1280px] flex-1 flex-col overflow-hidden rounded-2xl border border-black/10 bg-white shadow-[0_12px_40px_rgba(0,0,0,0.06)]">
        <div hidden={stage !== 1} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <DataStage
            key={resetKey}
            active={stage === 1}
            sessionReady={sessionReady}
            sessionError={session.status === 'error' ? session.error : null}
            onRetrySession={() => setSessionNonce((value) => value + 1)}
            onJobStarted={handleJobStarted}
          />
        </div>

        {jobId ? (
          <div hidden={stage !== 2} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <ProcessingView
              key={jobId}
              jobId={jobId}
              onSucceeded={handleJobSucceeded}
              onBack={() => setStage(1)}
            />
          </div>
        ) : null}

        {stage === 3 && jobId ? (
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <ResultsView key={'results-' + jobId} jobId={jobId} onNewRun={handleNewRun} />
          </div>
        ) : null}
      </section>

      <div
        className="relative w-full shrink-0 overflow-hidden"
        style={{ height: 'clamp(150px, 24vh, 280px)' }}
      >
        <Mascot />
      </div>
    </main>
  );
}
