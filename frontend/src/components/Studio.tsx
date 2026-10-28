'use client';

import React, { useState } from 'react';
import { Play, Sparkles, CheckCircle2, XCircle, HelpCircle, Code2, Terminal, Plus, Trash2 } from 'lucide-react';
import Mascot from './Mascot';

interface RowData {
  id: string;
  text: string;
  date: string;
  label: 'true' | 'false' | 'unsure';
}

const INITIAL_ROWS: RowData[] = [
  { id: 'p-1', text: 'Holdan started at Hooly on 12 January 2026.', date: '2026-01-12', label: 'true' },
  { id: 'p-2', text: "From today, Hooly Cloud's reliability team answers to Holdan.", date: '2026-01-12', label: 'true' },
  { id: 'p-3', text: 'Before Hooly, Holdan ran incident response at Nimbus Cloud.', date: '2026-01-12', label: 'true' },
  { id: 'p-14', text: 'The programme packed 40 sessions into the schedule.', date: '2026-06-12', label: 'false' },
  { id: 'p-121', text: 'Hooly Android 17 supports 19 models in the beta.', date: '2026-07-02', label: 'unsure' },
];

export default function Studio() {
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);
  const [rows, setRows] = useState<RowData[]>(INITIAL_ROWS);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [showLogs, setShowLogs] = useState(false);

  const handleRowChange = (index: number, field: keyof RowData, value: string) => {
    const updated = [...rows];
    updated[index] = { ...updated[index], [field]: value };
    setRows(updated);
  };

  const handleAddRow = () => {
    const newId = `p-${rows.length + 1}`;
    setRows([...rows, { id: newId, text: 'New observation predicate', date: '2026-01-01', label: 'true' }]);
  };

  const handleDeleteRow = (index: number) => {
    setRows(rows.filter((_, i) => i !== index));
  };

  const handleStartEvaluation = () => {
    setCurrentStep(2);
    setIsEvaluating(true);
    setTimeout(() => {
      setIsEvaluating(false);
      setCurrentStep(3);
    }, 2800);
  };

  return (
    <main className="relative w-screen min-h-screen flex flex-col items-center justify-start pt-[5.25rem] pb-16 z-10 overflow-hidden">
      {/* 3-Step Flow Pills */}
      <nav className="flex items-center gap-3 bg-white border border-black/[0.08] rounded-full px-2 py-1.5 shadow-[0_2px_10px_rgba(0,0,0,0.04)] mb-4 z-20">
        <button
          onClick={() => setCurrentStep(1)}
          className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold transition-colors ${
            currentStep === 1 ? 'bg-[#1d6dd7] text-white' : 'text-[#202020]/70 hover:text-black'
          }`}
        >
          <span>1</span> <span>Data & Schema</span>
        </button>
        <span className="text-black/30 text-xs">➔</span>
        <button
          onClick={() => setCurrentStep(2)}
          className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold transition-colors ${
            currentStep === 2 ? 'bg-[#1d6dd7] text-white' : 'text-[#202020]/70 hover:text-black'
          }`}
        >
          <span>2</span> <span>Mascot Evaluation</span>
        </button>
        <span className="text-black/30 text-xs">➔</span>
        <button
          onClick={() => setCurrentStep(3)}
          className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold transition-colors ${
            currentStep === 3 ? 'bg-[#1d6dd7] text-white' : 'text-[#202020]/70 hover:text-black'
          }`}
        >
          <span>3</span> <span>Certified Results</span>
        </button>
      </nav>

      {/* Studio Viewport */}
      <section className="w-[94vw] max-w-[1280px] min-h-[580px] bg-white border border-black/10 rounded-2xl shadow-[0_12px_40px_rgba(0,0,0,0.06)] flex flex-col overflow-hidden relative z-20 mb-12">
        {/* Studio Header */}
        <div className="h-14 px-6 border-b border-black/[0.08] flex items-center justify-between bg-[#fcfcfc]">
          <h2 className="font-display font-bold text-base text-[#202020]">
            {currentStep === 1 && 'Step 1: Schema Ingestion & Dataset Preview'}
            {currentStep === 2 && 'Step 2: Autonomous Agentic Verification in Progress'}
            {currentStep === 3 && 'Step 3: Machine-Certified Ground Truth Telemetry'}
          </h2>

          <div className="flex gap-2">
            <button
              onClick={() => setShowLogs(!showLogs)}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border border-black/10 text-xs font-semibold hover:bg-black/[0.03] transition-colors"
            >
              <Terminal className="w-3.5 h-3.5" />
              {showLogs ? 'Hide Logs' : 'View Logs'}
            </button>
          </div>
        </div>

        {/* Step 1: Data Table View */}
        {currentStep === 1 && (
          <div className="p-6 flex-1 flex flex-col justify-between">
            <div className="overflow-x-auto border border-black/[0.08] rounded-xl">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-[#f7f7f7] border-b border-black/[0.08] text-black/60 font-semibold uppercase tracking-wider">
                  <tr>
                    <th className="py-2.5 px-4 w-28">Entity ID</th>
                    <th className="py-2.5 px-4">Claim Proposition</th>
                    <th className="py-2.5 px-4 w-36">Timeline Anchor</th>
                    <th className="py-2.5 px-4 w-16 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/[0.06]">
                  {rows.map((row, idx) => (
                    <tr key={row.id} className="hover:bg-black/[0.01]">
                      <td className="py-2 px-4">
                        <input
                          className="w-full bg-transparent font-mono outline-none text-[#202020]"
                          value={row.id}
                          onChange={(e) => handleRowChange(idx, 'id', e.target.value)}
                        />
                      </td>
                      <td className="py-2 px-4">
                        <input
                          className="w-full bg-transparent outline-none text-[#202020]"
                          value={row.text}
                          onChange={(e) => handleRowChange(idx, 'text', e.target.value)}
                        />
                      </td>
                      <td className="py-2 px-4">
                        <input
                          className="w-full bg-transparent font-mono outline-none text-black/70"
                          value={row.date}
                          onChange={(e) => handleRowChange(idx, 'date', e.target.value)}
                        />
                      </td>
                      <td className="py-2 px-4 text-center">
                        <button
                          onClick={() => handleDeleteRow(idx)}
                          className="text-red-500 hover:text-red-700 p-1"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between pt-6 border-t border-black/[0.06] mt-4">
              <button
                onClick={handleAddRow}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-black/10 text-xs font-semibold hover:bg-black/[0.03]"
              >
                <Plus className="w-3.5 h-3.5" /> Add Observation Row
              </button>

              <button
                onClick={handleStartEvaluation}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#1d6dd7] text-white text-xs font-bold uppercase tracking-wider hover:bg-[#2859b5] transition-colors shadow-md shadow-[#1d6dd7]/20"
              >
                <Play className="w-3.5 h-3.5 fill-current" /> Run Mascot Evaluation
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Evaluation Animation View */}
        {currentStep === 2 && (
          <div className="p-8 flex-1 flex flex-col items-center justify-center text-center">
            <div className="w-16 h-16 rounded-full bg-[#e6effa] text-[#1d6dd7] flex items-center justify-center mb-4 animate-spin">
              <Sparkles className="w-8 h-8" />
            </div>
            <h3 className="font-display text-xl font-bold mb-2">Analyzing Knowledge Graph & Temporal Bounds...</h3>
            <p className="text-black/60 text-sm max-w-md">
              NEURON5 engine is evaluating graph consistency across 5 nodes against certified ground-truth contracts.
            </p>
          </div>
        )}

        {/* Step 3: Certified Results View */}
        {currentStep === 3 && (
          <div className="p-6 flex-1 flex flex-col justify-between">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="p-4 bg-[#e6f9f0] border border-[#10b981]/30 rounded-xl flex items-center gap-3">
                <CheckCircle2 className="w-8 h-8 text-[#10b981]" />
                <div>
                  <div className="text-xs uppercase font-bold text-[#10b981]">Consistency Rate</div>
                  <div className="text-2xl font-black font-display text-[#202020]">100%</div>
                </div>
              </div>

              <div className="p-4 bg-[#e6effa] border border-[#1d6dd7]/30 rounded-xl flex items-center gap-3">
                <Code2 className="w-8 h-8 text-[#1d6dd7]" />
                <div>
                  <div className="text-xs uppercase font-bold text-[#1d6dd7]">Evaluated Claims</div>
                  <div className="text-2xl font-black font-display text-[#202020]">{rows.length} rows</div>
                </div>
              </div>

              <div className="p-4 bg-black/[0.03] border border-black/10 rounded-xl flex items-center gap-3">
                <Terminal className="w-8 h-8 text-black/60" />
                <div>
                  <div className="text-xs uppercase font-bold text-black/60">Execution Time</div>
                  <div className="text-2xl font-black font-display text-[#202020]">24ms</div>
                </div>
              </div>
            </div>

            <div className="overflow-x-auto border border-black/[0.08] rounded-xl">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-[#f7f7f7] border-b border-black/[0.08] text-black/60 font-semibold uppercase tracking-wider">
                  <tr>
                    <th className="py-2.5 px-4">Entity</th>
                    <th className="py-2.5 px-4">Proposition</th>
                    <th className="py-2.5 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/[0.06]">
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td className="py-2.5 px-4 font-mono font-bold text-[#1d6dd7]">{row.id}</td>
                      <td className="py-2.5 px-4 text-black/80">{row.text}</td>
                      <td className="py-2.5 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider ${
                            row.label === 'true'
                              ? 'bg-emerald-100 text-emerald-800'
                              : row.label === 'false'
                              ? 'bg-red-100 text-red-800'
                              : 'bg-amber-100 text-amber-800'
                          }`}
                        >
                          {row.label === 'true' && <CheckCircle2 className="w-3 h-3" />}
                          {row.label === 'false' && <XCircle className="w-3 h-3" />}
                          {row.label === 'unsure' && <HelpCircle className="w-3 h-3" />}
                          {row.label}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end pt-4">
              <button
                onClick={() => setCurrentStep(1)}
                className="px-4 py-2 rounded-lg bg-black text-white text-xs font-bold hover:bg-black/80 transition-colors"
              >
                Reset & Edit Schema
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Gorilla Mascot (Positioned at bottom) */}
      <Mascot />
    </main>
  );
}

