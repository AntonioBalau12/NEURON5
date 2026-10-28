'use client';

import React, { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ArrowRight, Check, X } from 'lucide-react';
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
  const [isOpen, setIsOpen] = useState(false);
  const [stage, setStage] = useState<Stage>(1);
  const [session, setSession] = useState<SessionState>({ status: 'loading' });
  const [sessionNonce, setSessionNonce] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [resultReady, setResultReady] = useState(false);
  const [resetKey, setResetKey] = useState(0);
  const [isPulling, setIsPulling] = useState(false);

  const ctaRef = useRef<HTMLDivElement>(null);
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

  function handleOpenStudio() {
    if (isPulling) return;
    if (!viewportRef.current || !armRigRef.current) return;
    setIsPulling(true);
    (window as any).__isPullAnimationActive = true;

    // Smoothly fade & scale out the CTA hero block
    if (ctaRef.current) {
      ctaRef.current.style.pointerEvents = 'none';
      gsap.to(ctaRef.current, {
        opacity: 0,
        y: -24,
        scale: 0.95,
        duration: 0.25,
        ease: 'power2.inOut',
      });
    }

    // Trigger pull animation: table enters from off-screen right
    armRigRef.current.triggerPull(
      viewportRef.current,
      mascotRef.current?.container ?? null,
      mascotRef.current?.canvas ?? null,
      () => {
        setIsPulling(false);
        (window as any).__isPullAnimationActive = false;
        setIsOpen(true);
      }
    );
  }

  function handleCloseStudio() {
    if (isPulling || !viewportRef.current) return;
    setIsPulling(true);
    (window as any).__isPullAnimationActive = true;
    gsap.to(viewportRef.current, {
      x: typeof window !== 'undefined' ? window.innerWidth + 200 : 1200,
      y: 0,
      opacity: 0,
      scale: 1,
      rotation: 0,
      duration: 0.45,
      ease: 'power2.in',
      onComplete: () => {
        setIsPulling(false);
        (window as any).__isPullAnimationActive = false;
        setIsOpen(false);
        if (viewportRef.current) {
          viewportRef.current.style.visibility = 'hidden';
        }
        requestAnimationFrame(() => {
          if (ctaRef.current) {
            ctaRef.current.style.pointerEvents = 'auto';
            gsap.fromTo(
              ctaRef.current,
              { opacity: 0, y: 25, scale: 0.95 },
              { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: 'back.out(1.2)' }
            );
          }
        });
      },
    });
  }

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

      {/* ------------------------------------------------------------- */}
      {/* HERO CALL TO ACTION (Initial State before opening Studio)      */}
      {/* ------------------------------------------------------------- */}
      {!isOpen && (
        <div
          ref={ctaRef}
          className="absolute top-28 sm:top-32 md:top-36 left-1/2 -translate-x-1/2 flex flex-col items-center text-center w-full max-w-2xl px-6 z-50 select-none animate-in fade-in duration-500 pointer-events-auto"
        >
          {/* Punchy Heading with DESIGN.md color tokens */}
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-black font-display tracking-tight text-[#202020] leading-[1.08] mb-4">
            Deterministic Engine for <br />
            <span className="text-[#1d6dd7]">Temporal Intelligence</span>
          </h1>

          {/* Intro description with DESIGN.md --black-0-7 */}
          <p className="text-sm sm:text-base text-[#202020]/70 max-w-lg mb-8 leading-relaxed font-medium">
            Verify temporal claim constraints, test multi-agent proposition truth values, and generate certified datasets in real time.
          </p>

          {/* Big, Attractive CTA Button with Liquid Fill */}
          <button
            id="btn-launch-pipeline"
            onClick={handleOpenStudio}
            disabled={isPulling}
            className="button-primary group !px-8 !py-3.5 !text-sm md:!text-base !rounded-full shadow-[0_8px_24px_rgba(29,109,215,0.28)] hover:shadow-[0_12px_32px_rgba(29,109,215,0.45)] hover:scale-[1.02] active:scale-[0.98] transition-all cursor-pointer relative z-50 pointer-events-auto"
          >
            <span className="btn_fill" />
            <span className="button-text inline-flex items-center gap-3 text-[#fcfcfc]">
              <span className="font-bold tracking-wide">Launch Processing Arena</span>
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </span>
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* STEPPER NAVIGATION PILLS (Active when Studio is Open)         */}
      {/* ------------------------------------------------------------- */}
      <div className="h-11 mb-3 flex items-center justify-center z-40">
        {isOpen && (
          <div className="flex items-center gap-2 animate-in fade-in duration-300">
            <nav
              aria-label="Progressive Workflow"
              className="flex items-center gap-2 md:gap-3 bg-white border border-black/[0.08] rounded-full px-2 py-1.5 shadow-[0_2px_10px_rgba(0,0,0,0.04)]"
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
                          ? 'bg-[#1d6dd7] text-[#fcfcfc] shadow-sm'
                          : state === 'done'
                            ? 'text-[#1d6dd7] hover:bg-[#e6effa]'
                            : 'text-[#202020]/70 hover:text-[#202020] hover:bg-black/[0.03]') +
                        (enabled ? ' cursor-pointer' : ' cursor-not-allowed opacity-50')
                      }
                    >
                      <span
                        aria-hidden="true"
                        className={
                          'inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] ' +
                          (state === 'current'
                            ? 'bg-white/20 text-[#fcfcfc]'
                            : state === 'done'
                              ? 'bg-[#e6effa] text-[#1d6dd7]'
                              : 'bg-black/[0.04] text-[#202020]/50')
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

            <button
              onClick={handleCloseStudio}
              title="Minimize Studio"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/80 border border-black/[0.08] text-[11px] font-bold text-[#202020]/70 hover:text-[#202020] hover:bg-white shadow-[0_2px_8px_rgba(0,0,0,0.03)] transition-all cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Minimize</span>
            </button>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------- */}
      {/* STUDIO VIEWPORT CARD CONTAINER (Pulled by Mascot Rig)         */}
      {/* ------------------------------------------------------------- */}
      <div
        ref={viewportRef}
        style={{
          transform: 'translate3d(120vw, 0, 0)',
          opacity: 0,
          visibility: 'hidden',
          pointerEvents: isOpen ? 'auto' : 'none',
        }}
        className="w-[min(980px,94vw)] h-[calc(100vh-270px)] max-h-[500px] bg-white border border-black/[0.08] rounded-3xl shadow-[0_6px_24px_rgba(0,0,0,0.06)] flex flex-col overflow-hidden relative z-10 will-change-transform"
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
