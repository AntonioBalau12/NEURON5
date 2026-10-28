import React from 'react';

export default function Header() {
  return (
    <header className="fixed top-0 left-0 w-full h-[4.5rem] px-[4vw] flex items-center justify-between bg-[#fcfcfc]/95 backdrop-blur-md border-b border-black/[0.06] z-50">
      <a href="#" className="inline-flex items-center text-decoration-none font-display text-[1.625rem] font-black tracking-[-0.03em] leading-none select-none">
        <span className="text-[#202020]">NEURON</span>
        <span className="text-[#1d6dd7] ml-[1px]">5</span>
      </a>

      <div className="inline-flex items-center gap-2 bg-[#202020]/[0.04] border border-black/[0.08] text-[#202020] text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">
        <span className="w-2 h-2 rounded-full bg-[#d7f13b] animate-pulse" />
        <span>AI Agent Arena</span>
        <span className="text-black/30 font-normal">|</span>
        <span className="text-[#8fae0d] font-black">QA DNA</span>
      </div>
    </header>
  );
}

