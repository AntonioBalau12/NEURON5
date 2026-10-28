'use client';

import React from 'react';
import { cx } from './ui';

export interface JenkinsPipelineWorkflowProps {
  stage?: string; // 'queued' | 'parse' | 'classify' | 'write' | 'validate' | 'done' | 'failed';
  percent?: number | null;
  message?: string;
  className?: string;
}

export default function JenkinsPipelineWorkflow({
  stage = 'classify',
  percent = null,
  message,
  className,
}: JenkinsPipelineWorkflowProps) {
  const normalizedStage = (stage || '').toLowerCase();

  const isInputActive = normalizedStage === 'queued';
  const isInputDone = ['parse', 'classify', 'write', 'validate', 'done'].includes(normalizedStage);

  const isParseActive = normalizedStage === 'parse';
  const isParseDone = ['classify', 'write', 'validate', 'done'].includes(normalizedStage);

  const isFeaturesActive = normalizedStage === 'classify';
  const isFeaturesDone = ['write', 'validate', 'done'].includes(normalizedStage);

  const isValidateActive = ['write', 'validate'].includes(normalizedStage);
  const isValidateDone = normalizedStage === 'done';

  const isOutputActive = normalizedStage === 'done';
  const isOutputDone = normalizedStage === 'done';

  // Pulsing Green Glow for active stage (requested by user: "glow verde la fiecare stage")
  const activeGreenGlowStyle = {
    boxShadow: '0 0 0 2px #10b981, 0 0 20px rgba(16, 185, 129, 0.75)',
  };

  // Dynamic single-line live action text
  const liveActionText = isOutputDone
    ? 'Certified CSV output published successfully.'
    : message
      ? message
      : isValidateActive
        ? 'Stage 4: Validating table invariants & publishing atomic dataset...'
        : isFeaturesActive
          ? 'Stage 2 & 3: Extracting features & evaluating LightGBM inference...'
          : isParseActive
            ? 'Stage 1: Parsing ISO timestamps & normalizing unicode headers...'
            : isInputActive
              ? 'Input: Ingesting dataset claims stream...'
              : 'Processing dataset claims...';

  return (
    <div className={cx('w-full py-2 select-none overflow-hidden pr-2', className)}>
      
      {/* ------------------------------------------------------------- */}
      {/* TOP ROW: CATCH/FINALLY WIRE CONNECTING TO AUDIT-METRICS.JSON  */}
      {/* ------------------------------------------------------------- */}
      <div className="w-full flex items-center justify-between pl-[85px] pr-[38px] mb-1.5">
        <div className="flex items-center gap-2 flex-1 mr-3">
          <span className="rounded bg-[#16181f] border border-zinc-700 px-1.5 py-0.5 text-[8.5px] font-bold text-slate-300 whitespace-nowrap shadow-sm">
            catch/finally
          </span>
          <div className="h-[1.5px] flex-1 bg-zinc-700/80" />
        </div>

        {/* audit-metrics.json card */}
        <div
          className={cx(
            'rounded-lg border px-2.5 py-1 text-left transition-all bg-[#16181f] shrink-0 shadow-sm flex items-center gap-2',
            isValidateDone
              ? 'border-emerald-500 bg-[#06281e] text-emerald-400'
              : 'border-zinc-700 text-slate-300'
          )}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={isValidateDone ? '#10b981' : '#94a3b8'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          <div>
            <div className="text-[10px] font-bold text-white leading-tight">audit-metrics.json</div>
            <div className="text-[8.5px] text-slate-400 leading-tight">Telemetry Log</div>
          </div>
        </div>

        {/* Continuous telemetry connector wire curving smoothly down to Output CSV */}
        <div className="w-9 h-4 flex items-end">
          <svg width="36" height="16" viewBox="0 0 36 16" fill="none">
            <path
              d="M 0 2 L 20 2 A 12 12 0 0 1 32 14 L 32 16"
              stroke={isValidateDone || isOutputDone ? '#10b981' : '#52525b'}
              strokeWidth="2.5"
              strokeLinecap="round"
            />
          </svg>
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* MAIN DIAGRAM WORKFLOW ROW (100% Horizontally Aligned Axis)    */}
      {/* ------------------------------------------------------------- */}
      <div className="w-full flex items-start justify-between gap-1 overflow-hidden">

        {/* 1. LEFT: INPUT SOURCE & INGEST */}
        <div className="flex flex-col items-center w-[78px] shrink-0">
          <div className="flex flex-col items-center gap-0.5">
            <div
              className={cx(
                'w-9 h-9 rounded-full flex items-center justify-center border-2 transition-all shadow-md',
                isInputActive
                  ? 'bg-emerald-500 border-emerald-400 text-white animate-pulse'
                  : isInputDone
                    ? 'bg-[#06281e] border-emerald-500 text-emerald-400'
                    : 'bg-[#18181b] border-zinc-700 text-slate-300'
              )}
              style={isInputActive ? activeGreenGlowStyle : undefined}
              title="Input Stream"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
            </div>
            <span className="font-display text-[10.5px] font-extrabold text-[#202020] text-center leading-tight">
              Input Source
            </span>
            <span className="text-[9px] font-semibold text-slate-500 text-center leading-none">
              Claims Stream
            </span>
          </div>

          {/* Curved Inlet Pipe */}
          <div className="mt-1 flex items-center justify-center">
            <svg width="32" height="18" viewBox="0 0 32 18" fill="none">
              <path
                d="M 6 3 L 16 3 A 8 8 0 0 1 24 11 L 24 18"
                stroke={isInputActive || isInputDone ? '#10b981' : '#52525b'}
                strokeWidth="4"
                strokeLinecap="round"
              />
              <rect x="2" y="1" width="5" height="4" rx="1" fill="#27272a" />
              <rect x="22" y="14" width="4" height="4" rx="1" fill="#27272a" />
            </svg>
          </div>

          {/* Start Pill */}
          <div
            className={cx(
              'rounded-full px-2.5 py-0.5 text-[9px] font-black tracking-wider transition-all border w-full text-center mt-0.5',
              isInputActive
                ? 'border-emerald-400 bg-emerald-950/80 text-emerald-300'
                : isInputDone
                  ? 'border-emerald-500/80 bg-[#06281e] text-emerald-400'
                  : 'border-zinc-700 bg-[#16181f] text-slate-300'
            )}
            style={isInputActive ? activeGreenGlowStyle : undefined}
          >
            Start
          </div>

          <div className="my-0.5 text-slate-500 leading-none">
            <svg width="6" height="5" viewBox="0 0 6 5">
              <path d="M 3 0 L 3 3 M 1 2 L 3 4 L 5 2" stroke={isInputDone ? '#10b981' : '#64748b'} strokeWidth="1.4" fill="none" />
            </svg>
          </div>

          {/* Map Schema */}
          <div
            className={cx(
              'rounded-md px-1 py-1 text-center w-full border transition-all shadow-sm',
              isInputActive
                ? 'border-emerald-400 bg-emerald-950/80 text-white'
                : isInputDone
                  ? 'border-emerald-500/70 bg-[#06281e] text-slate-100'
                  : 'border-zinc-700 bg-[#16181f] text-slate-200'
            )}
            style={isInputActive ? activeGreenGlowStyle : undefined}
          >
            <div className="text-[9.5px] font-bold text-white leading-tight">Map Schema</div>
            <div className="text-[8px] text-slate-400 leading-tight">id · text · date</div>
          </div>
        </div>

        {/* Arrow Start -> Stage 1 */}
        <div className="mt-8 flex items-center justify-center text-slate-500 shrink-0">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <path d="M 0 5 L 8 5 M 5 2 L 8 5 L 5 8" stroke={isInputDone ? '#10b981' : '#52525b'} strokeWidth="1.8" fill="none" />
          </svg>
        </div>

        {/* 2. STAGE 1: Parse & Clean (Glowing Green Aura when Active) */}
        <div className="flex flex-col items-center w-[112px] shrink-0">
          <span className="text-[9px] font-extrabold uppercase tracking-wider text-slate-600 mb-1">Stage 1</span>
          <div
            className={cx(
              'rounded-lg border px-2 py-1.5 text-center w-full transition-all shadow-sm h-[44px] flex flex-col justify-center',
              isParseActive
                ? 'border-emerald-400 bg-[#06281e] animate-pulse'
                : isParseDone
                  ? 'border-emerald-500/70 bg-[#041d16]'
                  : 'border-zinc-700 bg-[#16181f]'
            )}
            style={isParseActive ? activeGreenGlowStyle : undefined}
          >
            <div className="font-display text-[10.5px] font-bold text-white leading-tight">Parse & Clean</div>
            <div className="text-[9px] text-slate-400 leading-tight mt-0.5">Header & Unicode</div>
          </div>

          <div className="w-0.5 h-2 bg-zinc-700" />

          <div
            className={cx(
              'rounded-lg border px-2 py-1.5 text-center w-full transition-all shadow-sm',
              isParseActive
                ? 'border-emerald-400 bg-[#06281e]'
                : isParseDone
                  ? 'border-emerald-500/70 bg-[#041d16]'
                  : 'border-zinc-700 bg-[#16181f]'
            )}
          >
            <div className="text-[10px] font-bold text-white leading-tight">ISO Date Parser</div>
            <div className="text-[9px] text-slate-300 leading-tight mt-0.5 whitespace-nowrap">Validate YYYY-MM-DD</div>
          </div>
        </div>

        {/* Arrow 1 -> 2 */}
        <div className="mt-8 flex items-center justify-center text-slate-500 shrink-0">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <path d="M 0 5 L 8 5 M 5 2 L 8 5 L 5 8" stroke={isParseDone ? '#10b981' : '#52525b'} strokeWidth="1.8" fill="none" />
          </svg>
        </div>

        {/* 3. STAGE 2: Feature Engine (Glowing Green Aura when Active) */}
        <div className="flex flex-col items-center w-[152px] shrink-0">
          <span className="text-[9px] font-extrabold uppercase tracking-wider text-slate-600 mb-1">Stage 2</span>
          <div
            className={cx(
              'rounded-lg border px-2 py-1.5 text-center w-full transition-all shadow-sm h-[44px] flex flex-col justify-center',
              isFeaturesActive
                ? 'border-emerald-400 bg-[#06281e] animate-pulse'
                : isFeaturesDone
                  ? 'border-emerald-500/70 bg-[#041d16]'
                  : 'border-zinc-700 bg-[#16181f]'
            )}
            style={isFeaturesActive ? activeGreenGlowStyle : undefined}
          >
            <div className="font-display text-[10.5px] font-bold text-white leading-tight">Feature Engine</div>
            <div className="text-[9px] text-slate-400 leading-tight mt-0.5">Signal Extraction</div>
          </div>

          {/* Parallel Bracket & Stack */}
          <div className="mt-1 flex items-stretch gap-1 w-full">
            <div className="flex items-center justify-center border-l-2 border-t-2 border-b-2 border-zinc-600 rounded-l px-0.5 py-1">
              <span className="text-[7.5px] font-black uppercase text-slate-400 tracking-widest [writing-mode:vertical-lr] rotate-180">
                Par
              </span>
            </div>
            <div className="flex flex-col gap-1 flex-1 min-w-0">
              <div
                className={cx(
                  'rounded-md border px-2 py-1 text-left transition-all',
                  isFeaturesActive
                    ? 'border-emerald-400 bg-[#06281e]'
                    : isFeaturesDone
                      ? 'border-emerald-500/70 bg-[#041d16]'
                      : 'border-zinc-700 bg-[#16181f]'
                )}
              >
                <div className="text-[9.5px] font-bold text-white leading-tight whitespace-nowrap">TF-IDF N-Grams</div>
                <div className="text-[8.5px] text-slate-400 leading-tight">Word & Char (1,2)</div>
              </div>
              <div
                className={cx(
                  'rounded-md border px-2 py-1 text-left transition-all',
                  isFeaturesActive
                    ? 'border-emerald-400 bg-[#06281e]'
                    : isFeaturesDone
                      ? 'border-emerald-500/70 bg-[#041d16]'
                      : 'border-zinc-700 bg-[#16181f]'
                )}
              >
                <div className="text-[9.5px] font-bold text-white leading-tight whitespace-nowrap">Lexicon Entities</div>
                <div className="text-[8.5px] text-slate-400 leading-tight">Entities & Relations</div>
              </div>
              <div
                className={cx(
                  'rounded-md border px-2 py-1 text-left transition-all',
                  isFeaturesActive
                    ? 'border-emerald-400 bg-[#06281e]'
                    : isFeaturesDone
                      ? 'border-emerald-500/70 bg-[#041d16]'
                      : 'border-zinc-700 bg-[#16181f]'
                )}
              >
                <div className="text-[9.5px] font-bold text-white leading-tight whitespace-nowrap">Temporal Deltas</div>
                <div className="text-[8.5px] text-slate-400 leading-tight">Date Sin/Cos Cycles</div>
              </div>
            </div>
          </div>
        </div>

        {/* Arrow 2 -> 3 */}
        <div className="mt-8 flex items-center justify-center text-slate-500 shrink-0">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <path d="M 0 5 L 8 5 M 5 2 L 8 5 L 5 8" stroke={isFeaturesDone ? '#10b981' : '#52525b'} strokeWidth="1.8" fill="none" />
          </svg>
        </div>

        {/* 4. STAGE 3: Model Inference (Glowing Green Aura when Active) */}
        <div className="flex flex-col items-center w-[225px] shrink-0">
          <span className="text-[9px] font-extrabold uppercase tracking-wider text-slate-600 mb-1">Stage 3</span>
          <div
            className={cx(
              'rounded-lg border px-2 py-1.5 text-center w-full transition-all shadow-sm h-[44px] flex flex-col justify-center',
              isFeaturesActive
                ? 'border-emerald-400 bg-[#06281e] animate-pulse'
                : isFeaturesDone
                  ? 'border-emerald-500/70 bg-[#041d16]'
                  : 'border-zinc-700 bg-[#16181f]'
            )}
            style={isFeaturesActive ? activeGreenGlowStyle : undefined}
          >
            <div className="font-display text-[10.5px] font-bold text-white leading-tight">Model Inference</div>
            <div className="text-[9px] text-slate-400 leading-tight mt-0.5">LightGBM Engine</div>
          </div>

          {/* Parallel Evaluators & Ruling Doc */}
          <div className="mt-1 flex items-stretch gap-1 w-full">
            <div className="flex items-center justify-center border-l-2 border-t-2 border-b-2 border-zinc-600 rounded-l px-0.5 py-1">
              <span className="text-[7.5px] font-black uppercase text-slate-400 tracking-widest [writing-mode:vertical-lr] rotate-180">
                Par
              </span>
            </div>
            
            {/* Sub-cards */}
            <div className="flex flex-col gap-1 w-[128px] shrink-0">
              <div
                className={cx(
                  'rounded-md border px-2.5 py-1 text-left transition-all',
                  isFeaturesActive
                    ? 'border-emerald-400 bg-[#06281e]'
                    : isFeaturesDone
                      ? 'border-emerald-500/70 bg-[#041d16]'
                      : 'border-zinc-700 bg-[#16181f]'
                )}
              >
                <div className="text-[9.5px] font-bold text-white leading-tight whitespace-nowrap">LightGBM 3-Class</div>
                <div className="text-[8px] text-slate-300 leading-tight">Probabilities</div>
              </div>
              <div
                className={cx(
                  'rounded-md border px-2.5 py-1 text-left transition-all',
                  isFeaturesActive
                    ? 'border-emerald-400 bg-[#06281e]'
                    : isFeaturesDone
                      ? 'border-emerald-500/70 bg-[#041d16]'
                      : 'border-zinc-700 bg-[#16181f]'
                )}
              >
                <div className="text-[9.5px] font-bold text-white leading-tight whitespace-nowrap">Threshold Margin</div>
                <div className="text-[8px] text-slate-300 leading-tight">Margin (τ=0.50)</div>
              </div>
            </div>

            {/* Centered connector arrow into Ruling Sheet */}
            <div className="flex items-center justify-center text-slate-500 shrink-0 px-0.5">
              <svg width="6" height="8" viewBox="0 0 6 8">
                <path d="M 0 4 L 5 4 M 2 1 L 5 4 L 2 7" stroke={isFeaturesDone ? '#10b981' : '#64748b'} strokeWidth="1.6" fill="none" />
              </svg>
            </div>

            {/* Ruling Doc */}
            <div
              className={cx(
                'rounded-md border px-2 py-1.5 text-center flex-1 transition-all bg-[#16181f] shadow-sm flex flex-col justify-center items-center',
                isFeaturesDone
                  ? 'border-emerald-500 bg-[#06281e] text-emerald-400'
                  : 'border-zinc-700 text-slate-300'
              )}
            >
              <div className="text-[9px] font-extrabold text-white leading-tight whitespace-nowrap">Ruling Sheet</div>
              <div className="text-[8.5px] font-bold text-emerald-400 leading-tight mt-1 whitespace-nowrap">T / F / U</div>
            </div>
          </div>
        </div>

        {/* Arrow 3 -> 4 */}
        <div className="mt-8 flex items-center justify-center text-slate-500 shrink-0">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <path d="M 0 5 L 8 5 M 5 2 L 8 5 L 5 8" stroke={isFeaturesDone ? '#10b981' : '#52525b'} strokeWidth="1.8" fill="none" />
          </svg>
        </div>

        {/* 5. STAGE 4: Table Validate (Glowing Green Aura when Active) */}
        <div className="flex flex-col items-center w-[112px] shrink-0">
          <span className="text-[9px] font-extrabold uppercase tracking-wider text-slate-600 mb-1">Stage 4</span>
          <div
            className={cx(
              'rounded-lg border px-2 py-1.5 text-center w-full transition-all shadow-sm h-[44px] flex flex-col justify-center',
              isValidateActive
                ? 'border-emerald-400 bg-[#06281e] animate-pulse'
                : isValidateDone
                  ? 'border-emerald-500/70 bg-[#041d16]'
                  : 'border-zinc-700 bg-[#16181f]'
            )}
            style={isValidateActive ? activeGreenGlowStyle : undefined}
          >
            <div className="font-display text-[10.5px] font-bold text-white leading-tight">Table Validate</div>
            <div className="text-[9px] text-slate-400 leading-tight mt-0.5">Atomic Publish</div>
          </div>

          <div className="w-0.5 h-2 bg-zinc-700" />

          <div
            className={cx(
              'rounded-lg border px-2 py-1.5 text-center w-full transition-all shadow-sm',
              isValidateActive
                ? 'border-emerald-400 bg-[#06281e]'
                : isValidateDone
                  ? 'border-emerald-500/70 bg-[#041d16]'
                  : 'border-zinc-700 bg-[#16181f]'
            )}
          >
            <div className="text-[10px] font-bold text-white leading-tight">Invariants Check</div>
            <div className="text-[9px] text-slate-300 leading-tight mt-0.5 whitespace-nowrap">Row Matching</div>
          </div>
        </div>

        {/* Arrow 4 -> WF End */}
        <div className="mt-8 flex items-center justify-center text-slate-500 shrink-0">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <path d="M 0 5 L 8 5 M 5 2 L 8 5 L 5 8" stroke={isValidateDone ? '#10b981' : '#52525b'} strokeWidth="1.8" fill="none" />
          </svg>
        </div>

        {/* 6. WORKFLOW END PILL */}
        <div className="mt-7 flex flex-col items-center shrink-0">
          <div
            className={cx(
              'rounded-full px-2.5 py-1 text-[9px] font-black tracking-wider transition-all border whitespace-nowrap shadow-sm',
              isValidateDone
                ? 'border-emerald-500 bg-[#06281e] text-emerald-300'
                : 'border-zinc-700 bg-[#16181f] text-slate-300'
            )}
            style={isValidateDone ? activeGreenGlowStyle : undefined}
          >
            WF End
          </div>
        </div>

        {/* Arrow WF End -> Output CSV */}
        <div className="mt-8 flex items-center justify-center text-slate-500 shrink-0">
          <svg width="10" height="10" viewBox="0 0 10 10">
            <path d="M 0 5 L 8 5 M 5 2 L 8 5 L 5 8" stroke={isOutputDone ? '#10b981' : '#52525b'} strokeWidth="1.8" fill="none" />
          </svg>
        </div>

        {/* 7. RIGHT: CERTIFIED OUTPUT CSV (Glowing Green Aura when Complete) */}
        <div className="flex flex-col items-center w-[78px] shrink-0 mt-3.5">
          <div
            className={cx(
              'w-9 h-9 rounded-full flex items-center justify-center border-2 transition-all shadow-md',
              isOutputActive
                ? 'bg-emerald-500 border-emerald-400 text-white animate-pulse'
                : isOutputDone
                  ? 'bg-emerald-600 border-emerald-400 text-white'
                  : 'bg-[#18181b] border-zinc-700 text-slate-300'
            )}
            style={isOutputActive || isOutputDone ? activeGreenGlowStyle : undefined}
            title="Certified Output"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
          </div>
          <span className="font-display text-[10.5px] font-extrabold text-[#202020] text-center leading-tight whitespace-nowrap mt-1">
            Output CSV
          </span>
          <span className="text-[9px] font-mono font-semibold text-slate-500 text-center leading-none">
            result.csv
          </span>
        </div>

      </div>

      {/* ------------------------------------------------------------- */}
      {/* SINGLE-LINE LIVE ACTION & PERCENTAGE CONSOLE BAR              */}
      {/* ------------------------------------------------------------- */}
      <div className="flex items-center justify-between rounded-xl bg-[#141518] px-3.5 py-2 border border-zinc-800 text-white shadow-sm mt-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            {isOutputDone ? (
              <span className="inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
            ) : (
              <>
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
              </>
            )}
          </span>
          <span className="text-[10.5px] font-extrabold uppercase tracking-wider text-emerald-400 shrink-0">
            {isOutputDone ? 'COMPLETED' : 'RUNNING'}
          </span>
          <span className="text-zinc-600">|</span>
          <span className="text-[11px] font-medium text-slate-200 truncate">
            {liveActionText}
          </span>
        </div>
        <div className="flex items-center gap-2 pl-3 shrink-0">
          <span className="font-mono text-xs font-black text-emerald-400">
            {percent !== null ? `${percent}%` : isOutputDone ? '100%' : '...'}
          </span>
        </div>
      </div>
    </div>
  );
}
