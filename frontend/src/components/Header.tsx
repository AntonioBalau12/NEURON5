import React from 'react';

export default function Header() {
  return (
    <header className="fixed top-0 left-0 w-full h-[4.5rem] px-[4vw] flex items-center justify-start bg-transparent z-50 pointer-events-none">
      <a
        href="#"
        className="inline-flex items-center text-decoration-none font-display text-[1.875rem] font-black tracking-[-0.03em] leading-none select-none pointer-events-auto cursor-default"
        aria-label="NEURON5"
      >
        <span className="text-[#202020]">NEURON</span>
        <span className="text-[#8fae0d] ml-[1px]">5</span>
      </a>
    </header>
  );
}
