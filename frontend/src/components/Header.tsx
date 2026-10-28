import React from 'react';

export default function Header() {
  return (
    <header className="relative z-30 flex h-[4.5rem] w-full shrink-0 items-center justify-between border-b border-black/[0.06] bg-[#fcfcfc]/95 px-[4vw] backdrop-blur-md">
      <a href="#" className="inline-flex items-center text-decoration-none font-display text-[1.625rem] font-black tracking-[-0.03em] leading-none select-none">
        <span className="text-[#202020]">NEURON</span>
        <span className="text-[#1d6dd7] ml-[1px]">5</span>
      </a>

      <div className="inline-flex items-center gap-1.5 bg-[#e6effa] text-[#1d6dd7] text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">
        <span className="w-2 h-2 rounded-full bg-[#1d6dd7] animate-pulse" />
        AI Agent Arena
      </div>
    </header>
  );
}
