'use client';

import React, { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import SplitType from 'split-type';

export default function MarketingSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    gsap.registerPlugin(ScrollTrigger);

    if (headingRef.current) {
      const split = new SplitType(headingRef.current, { types: 'chars,words' });

      // Initial state: 20% opacity
      gsap.set(split.chars, { opacity: 0.2 });

      // Scrub highlight character-by-character on scroll
      const anim = gsap.to(split.chars, {
        scrollTrigger: {
          trigger: headingRef.current,
          start: 'top 80%',
          end: 'top 25%',
          scrub: true,
          markers: false,
        },
        opacity: 1,
        stagger: 0.08,
        ease: 'power1.out',
      });

      return () => {
        anim.scrollTrigger?.kill();
        anim.kill();
        split.revert();
      };
    }
  }, []);

  return (
    <section
      ref={sectionRef}
      id="introduction"
      className="relative z-20 flex flex-col justify-center items-center overflow-visible bg-[#2859b5] text-[#fcfcfc] rounded-[20px] md:rounded-[40px] my-16 mx-4 md:mx-[5vw] py-20 md:py-28 px-6 shadow-[0_20px_60px_rgba(40,89,181,0.18)]"
    >
      <div className="w-full max-w-[80rem] mx-auto flex flex-col items-center justify-center">
        <div className="w-full max-w-[68rem] text-center" style={{ textWrap: 'balance' }}>
          <h2
            ref={headingRef}
            className="font-display text-[2rem] md:text-[3.75rem] font-bold leading-[1.25] tracking-[-0.02em] text-[#fcfcfc] m-0 inline-block select-none"
          >
            Marketing
          </h2>
        </div>
      </div>
    </section>
  );
}

