import React from 'react';
import Mascot from './Mascot';

export default function Hero() {
  return (
    <section id="hero-stage" className="relative w-screen h-screen flex flex-col items-center justify-center z-10 px-6 overflow-visible">
      {/* Centered Hero Content */}
      <div className="text-center flex flex-col items-center justify-center -translate-y-[8vh] z-20 select-none">
        <h1 className="font-display text-[clamp(2.25rem,5.5vw,4.35rem)] font-black leading-[1.1] tracking-[-0.025em] uppercase text-[#202020] max-w-[90vw]">
          <span className="block">AI AGENT ARENA</span>
          <span className="block">POWERED BY NEURON5</span>
        </h1>
        <p className="mt-6 font-body text-lg font-medium text-black/70 tracking-[-0.01em]">
          Coming soon.
        </p>
      </div>

      {/* Gorilla Mascot (Anchored at the bottom edge) */}
      <Mascot />
    </section>
  );
}

