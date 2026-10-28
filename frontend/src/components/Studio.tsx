'use client';

import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Terminal,
  Plus,
  Trash2,
  Download,
  RotateCcw,
  Layers,
  Database,
  BarChart3,
  ExternalLink
} from 'lucide-react';
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
  const [activeChipIdx, setActiveChipIdx] = useState<number>(0);
  const [showLogs, setShowLogs] = useState(false);

  const chips = [
    '⚡ Schema: 4 columns verified',
    '📅 ISO Date Normalized: 2026-01-12',
    '🔗 Graph Entity: Holdan ➔ Hooly',
    '🛡️ Temporal Constraint: Passed',
    '🎯 Decision: Certified True (Confidence 0.99)'
  ];

  useEffect(() => {
    if (currentStep === 2) {
      setActiveChipIdx(0);
      const interval = setInterval(() => {
        setActiveChipIdx((prev) => {
          if (prev < chips.length - 1) {
            return prev + 1;
          }
          return prev;
        });
      }, 500);

      const timer = setTimeout(() => {
        setCurrentStep(3);
      }, 2900);

      return () => {
        clearInterval(interval);
        clearTimeout(timer);
      };
    }
  }, [currentStep]);

  const handleRowChange = (index: number, field: keyof RowData, value: string) => {
    const updated = [...rows];
    updated[index] = { ...updated[index], [field]: value };
    setRows(updated);
  };

  const handleAddRow = () => {
    const newId = `p-${rows.length + 1}`;
    setRows([...rows, { id: newId, text: 'New temporal proposition node', date: '2026-01-01', label: 'true' }]);
  };

  const handleDeleteRow = (index: number) => {
    setRows(rows.filter((_, i) => i !== index));
  };

  return (
    <section id="hero-stage" className="relative w-screen h-screen overflow-hidden flex flex-col items-center justify-start pt-20 z-10">
      {/* Stepper Navigation Pills */}
      <nav className="flex items-center gap-2 md:gap-3 bg-white border border-black/[0.08] rounded-full px-2 py-1.5 shadow-[0_2px_10px_rgba(0,0,0,0.04)] mb-3 z-20" aria-label="Progressive Workflow">
        <button
          onClick={() => setCurrentStep(1)}
          className={`inline-flex items-center gap-2 px-3.5 py-1 rounded-full text-xs font-bold transition-all ${
            currentStep === 1 ? 'bg-[#1d6dd7] text-white shadow-sm' : 'text-[#202020]/70 hover:text-black hover:bg-black/[0.03]'
          }`}
        >
          <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[10px]">1</span>
          <span>Data & Schema</span>
        </button>
        <span className="text-black/30 text-xs">➔</span>
        <button
          onClick={() => setCurrentStep(2)}
          className={`inline-flex items-center gap-2 px-3.5 py-1 rounded-full text-xs font-bold transition-all ${
            currentStep === 2 ? 'bg-[#1d6dd7] text-white shadow-sm' : 'text-[#202020]/70 hover:text-black hover:bg-black/[0.03]'
          }`}
        >
          <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[10px]">2</span>
          <span>Mascot Evaluation</span>
        </button>
        <span className="text-black/30 text-xs">➔</span>
        <button
          onClick={() => setCurrentStep(3)}
          className={`inline-flex items-center gap-2 px-3.5 py-1 rounded-full text-xs font-bold transition-all ${
            currentStep === 3 ? 'bg-[#1d6dd7] text-white shadow-sm' : 'text-[#202020]/70 hover:text-black hover:bg-black/[0.03]'
          }`}
        >
          <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[10px]">3</span>
          <span>Certified Results</span>
        </button>
      </nav>

      {/* Main Studio Viewport Box */}
      <div className="w-[min(980px,94vw)] h-[calc(100vh-270px)] max-h-[500px] bg-white border border-black/[0.08] rounded-3xl shadow-[0_6px_24px_rgba(0,0,0,0.06)] flex flex-col overflow-hidden relative z-20">
        
        {/* Studio Header */}
        <div className="h-12 px-6 border-b border-black/[0.08] flex items-center justify-between bg-[#fcfcfc]">
          <h2 className="font-display font-bold text-sm text-[#202020] flex items-center gap-2">
            {currentStep === 1 && (
              <>
                <Database className="w-4 h-4 text-[#1d6dd7]" />
                <span>Step 1: Schema Ingestion & Dataset Preview</span>
              </>
            )}
            {currentStep === 2 && (
              <>
                <Sparkles className="w-4 h-4 text-[#1d6dd7] animate-spin" />
                <span>Step 2: Mascot In-Review & Inference Simulation</span>
              </>
            )}
            {currentStep === 3 && (
              <>
                <BarChart3 className="w-4 h-4 text-[#10b981]" />
                <span>Step 3: Verification & Analytics Console</span>
              </>
            )}
          </h2>

          <button
            onClick={() => setShowLogs(!showLogs)}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border border-black/10 text-xs font-semibold hover:bg-black/[0.03] transition-colors"
          >
            <Terminal className="w-3.5 h-3.5 text-black/60" />
            {showLogs ? 'Hide Logs' : 'View Deep Logs'}
          </button>
        </div>

        {/* STEP 1: Schema Ingestion */}
        {currentStep === 1 && (
          <div className="p-5 flex-1 flex flex-col justify-between overflow-hidden">
            <div className="flex items-center gap-2 mb-2 bg-[#f8fafc] px-3 py-2 rounded-xl border border-black/[0.04]">
              <span className="text-[11px] font-bold uppercase tracking-wider text-black/60 flex items-center gap-1">
                <Layers className="w-3.5 h-3.5 text-[#1d6dd7]" />
                Input Schema:
              </span>
              <span className="font-mono text-xs text-black/80 font-medium">id (string) | text (string) | date (ISO YYYY-MM-DD)</span>
            </div>

            <div className="overflow-y-auto border border-black/[0.08] rounded-xl flex-1 max-h-[260px]">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-[#f7f7f7] sticky top-0 border-b border-black/[0.08] text-black/60 font-semibold uppercase tracking-wider text-[11px]">
                  <tr>
                    <th className="py-2 px-3 w-28">Entity ID</th>
                    <th className="py-2 px-3">Claim Proposition</th>
                    <th className="py-2 px-3 w-36">Timeline Anchor</th>
                    <th className="py-2 px-3 w-14 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/[0.06]">
                  {rows.map((row, idx) => (
                    <tr key={row.id} className="hover:bg-black/[0.01]">
                      <td className="py-1.5 px-3">
                        <input
                          className="w-full bg-transparent font-mono outline-none text-[#202020]"
                          value={row.id}
                          onChange={(e) => handleRowChange(idx, 'id', e.target.value)}
                        />
                      </td>
                      <td className="py-1.5 px-3">
                        <input
                          className="w-full bg-transparent outline-none text-[#202020]"
                          value={row.text}
                          onChange={(e) => handleRowChange(idx, 'text', e.target.value)}
                        />
                      </td>
                      <td className="py-1.5 px-3">
                        <input
                          className="w-full bg-transparent font-mono outline-none text-black/70"
                          value={row.date}
                          onChange={(e) => handleRowChange(idx, 'date', e.target.value)}
                        />
                      </td>
                      <td className="py-1.5 px-3 text-center">
                        <button
                          onClick={() => handleDeleteRow(idx)}
                          className="text-red-500 hover:text-red-700 p-1"
                          title="Remove Row"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-black/[0.06] mt-2">
              <button
                onClick={handleAddRow}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-black/10 text-xs font-semibold hover:bg-black/[0.03]"
              >
                <Plus className="w-3.5 h-3.5" /> Add Row
              </button>

              <button
                onClick={() => setCurrentStep(2)}
                className="button-primary"
              >
                <span className="btn_fill"></span>
                <span className="button-text">
                  Proceed to Mascot Evaluation ➔
                </span>
              </button>
            </div>
          </div>
        )}

        {/* STEP 2: Mascot Inference / Clipboard */}
        {currentStep === 2 && (
          <div className="p-6 flex-1 flex flex-col items-center justify-center text-center relative">
            <div className="w-[min(540px,92%)] bg-white border-2 border-[#1d6dd7] rounded-2xl p-4 shadow-[0_10px_30px_rgba(29,109,215,0.12)] mb-4 animate-bounce">
              <div className="text-[11px] font-bold text-[#1d6dd7] uppercase tracking-wider mb-1 flex items-center justify-center gap-1.5">
                <Sparkles className="w-3 h-3" />
                Mascot Inspection Clipboard
              </div>
              <div className="font-mono text-xs bg-[#f8fafc] p-2.5 rounded-lg text-black/80 border border-black/[0.04] mb-2 text-left">
                {rows[0]?.text || 'Evaluating schema vector...'}
              </div>
              <div className="text-xs text-black/60">
                Status: <strong className="text-[#1d6dd7]">Mascot is parsing row vectors & temporal constraints...</strong>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 justify-center max-w-[620px]">
              {chips.map((chip, idx) => (
                <div
                  key={idx}
                  className={`text-xs px-3 py-1 rounded-full border transition-all duration-300 ${
                    idx <= activeChipIdx
                      ? 'bg-[#e6effa] border-[#1d6dd7]/40 text-[#1d6dd7] scale-100 opacity-100 font-semibold'
                      : 'bg-black/[0.02] border-black/[0.05] text-black/30 scale-95 opacity-50'
                  }`}
                >
                  {chip}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* STEP 3: Results & Analytics Console */}
        {currentStep === 3 && (
          <div className="p-5 flex-1 flex flex-col justify-between overflow-hidden">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <div className="p-3 bg-[#f8fafc] border border-black/[0.08] rounded-xl text-center">
                <div className="text-xl font-black font-display text-[#10b981]">100%</div>
                <div className="text-[10px] font-bold uppercase text-black/60 mt-0.5">Confidence Rate</div>
              </div>

              <div className="p-3 bg-[#f8fafc] border border-black/[0.08] rounded-xl text-center">
                <div className="text-xl font-black font-display text-[#1d6dd7]">{rows.length} Rows</div>
                <div className="text-[10px] font-bold uppercase text-black/60 mt-0.5">Verified Assertions</div>
              </div>

              <div className="p-3 bg-[#f8fafc] border border-black/[0.08] rounded-xl text-center">
                <div className="text-xl font-black font-display text-[#202020]">0</div>
                <div className="text-[10px] font-bold uppercase text-black/60 mt-0.5">Hallucinations</div>
              </div>

              <div className="p-3 bg-[#f8fafc] border border-black/[0.08] rounded-xl text-center">
                <div className="text-xl font-black font-display text-[#202020]">24ms</div>
                <div className="text-[10px] font-bold uppercase text-black/60 mt-0.5">Latency</div>
              </div>
            </div>

            <div className="overflow-y-auto border border-black/[0.08] rounded-xl flex-1 max-h-[190px]">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-[#f7f7f7] sticky top-0 border-b border-black/[0.08] text-black/60 font-semibold uppercase tracking-wider text-[11px]">
                  <tr>
                    <th className="py-2 px-3 w-28">Proposition ID</th>
                    <th className="py-2 px-3">Validated Claim</th>
                    <th className="py-2 px-3 w-28 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/[0.06]">
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td className="py-1.5 px-3 font-mono font-bold text-[#1d6dd7]">{row.id}</td>
                      <td className="py-1.5 px-3 text-black/80">{row.text}</td>
                      <td className="py-1.5 px-3 text-center">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
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

            <div className="flex items-center justify-between pt-3 border-t border-black/[0.06] mt-2">
              <button
                onClick={() => setCurrentStep(1)}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-black/10 text-xs font-semibold hover:bg-black/[0.03]"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Reset & Re-run
              </button>

              <button
                onClick={() => alert('output.csv exported successfully conforming to strict machine contract.')}
                className="button-primary"
              >
                <span className="btn_fill"></span>
                <span className="button-text">
                  <Download className="w-3.5 h-3.5" /> Export Certified output.csv
                </span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Logs Drawer Modal */}
      {showLogs && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-[min(640px,94vw)] max-h-[460px] bg-[#141414] text-[#fcfcfc] rounded-2xl shadow-2xl flex flex-col border border-white/10 overflow-hidden">
            <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/30">
              <h3 className="font-display text-sm font-bold flex items-center gap-2">
                <Terminal className="w-4 h-4 text-[#1d6dd7]" />
                Live Arena Trace Telemetry
              </h3>
              <button
                onClick={() => setShowLogs(false)}
                className="text-white/60 hover:text-white text-lg font-bold px-2 py-0.5 rounded"
              >
                &times;
              </button>
            </div>
            <div className="p-4 font-mono text-xs overflow-y-auto space-y-2 text-[#94a3b8]">
              <div>[11:04:10.100] [BOOT] NEURON5 Engine v1.0.0 initializing...</div>
              <div>[11:04:10.125] [ENV] Runtime sandbox verified: Linux/amd64, User 10001, Network=None.</div>
              <div>[11:04:10.200] [GRAPH] 62 lexicon nodes loaded, 321 attribute edges compiled.</div>
              <div>[11:04:10.450] [INFERENCE] Temporal reasoner: 5 predicate bounds validated.</div>
              <div className="text-emerald-400">[11:04:10.510] [CERTIFIED] Confidence threshold 0.95 met. Output verified.</div>
            </div>
          </div>
        </div>
      )}

      {/* Anchored Gorilla Mascot (Peeking from bottom of the 100vh hero stage) */}
      <Mascot />
    </section>
  );
}
