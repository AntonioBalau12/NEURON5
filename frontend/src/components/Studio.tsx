'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Check } from 'lucide-react';
import Mascot, { MascotHandle } from './Mascot';
import GorillaArmRig, { GorillaArmRigHandle } from './GorillaArmRig';
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
  const [isPulling, setIsPulling] = useState(false);

  const viewportRef = useRef<HTMLDivElement>(null);
  const armRigRef = useRef<GorillaArmRigHandle>(null);
  const mascotRef = useRef<MascotHandle>(null);

  // Constant Function: Triggers the gorilla arm bicep curl table drag animation
  const triggerPullAnimation = (onComplete?: () => void) => {
    if (isPulling) return;
    if (armRigRef.current && viewportRef.current) {
      setIsPulling(true);
      (window as any).__isPullAnimationActive = true;
      armRigRef.current.triggerPull(
        viewportRef.current,
        mascotRef.current?.container ?? null,
        mascotRef.current?.canvas ?? null,
        () => {
          setIsPulling(false);
          (window as any).__isPullAnimationActive = false;
          if (onComplete) onComplete();
        }
      );
    }
  };

  useEffect(() => {
    if (typeof window !== 'undefined') {
      (window as any).triggerPullAnimation = triggerPullAnimation;
    }
    return () => {
      if (typeof window !== 'undefined') {
        delete (window as any).triggerPullAnimation;
      }
    };
  }, [isPulling]);

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
    <section id="hero-stage" className="relative w-screen h-screen overflow-hidden flex flex-col items-center justify-start pt-20 z-10">
      {/* Background Dot Grid */}
      <div className="absolute inset-0 bg-[radial-gradient(#000000_1px,transparent_1px)] [background-size:24px_24px] opacity-[0.07] pointer-events-none" />

      {/* Stepper Navigation Pills */}
      <nav
        aria-label="Progressive Workflow"
        className="flex items-center gap-2 md:gap-3 bg-white border border-black/[0.08] rounded-full px-2 py-1.5 shadow-[0_2px_10px_rgba(0,0,0,0.04)] mb-3 z-20"
      >
        {STEPS.map((step, index) => {
          const state = stage === step.number ? 'current' : stage > step.number ? 'done' : 'upcoming';
          const enabled = canOpen(step.number);
          return (
            <React.Fragment key={step.number}>
              <button
                type="button"
                onClick={() => goToStage(step.number)}
                disabled={!enabled}
                aria-current={state === 'current' ? 'step' : undefined}
                aria-disabled={!enabled}
                className={
                  'inline-flex items-center gap-2 rounded-full px-3.5 py-1 text-xs font-bold transition-all ' +
                  (state === 'current'
                    ? 'bg-[#1d6dd7] text-white shadow-sm'
                    : state === 'done'
                      ? 'text-[#1d6dd7] hover:bg-[#e6effa]'
                      : 'text-[#202020]/70 hover:text-black hover:bg-black/[0.03]') +
                  (enabled ? ' cursor-pointer' : ' cursor-not-allowed opacity-50')
                }
              >
                <span
                  aria-hidden="true"
                  className={
                    'inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] ' +
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
                <span className="text-black/30 text-xs">➔</span>
              ) : null}
            </React.Fragment>
          );
        })}
      </nav>

      {/* Studio Viewport Card Container */}
      <div
        ref={viewportRef}
        className="w-[min(980px,94vw)] h-[calc(100vh-270px)] max-h-[500px] bg-white border border-black/[0.08] rounded-3xl shadow-[0_6px_24px_rgba(0,0,0,0.06)] flex flex-col overflow-hidden relative z-30 will-change-transform"
      >
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
      </div>

      {/* Gorilla Skeletal Arm Rig & Anchored Mascot Stage */}
      <GorillaArmRig ref={armRigRef} />
      <Mascot ref={mascotRef} />
    </section>
  );
}
