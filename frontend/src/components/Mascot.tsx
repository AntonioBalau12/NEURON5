'use client';

import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';

export interface MascotHandle {
  canvas: HTMLCanvasElement | null;
  container: HTMLDivElement | null;
}

const Mascot = forwardRef<MascotHandle, {}>((_props, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    get canvas() {
      return canvasRef.current;
    },
    get container() {
      return containerRef.current;
    },
  }));

  useEffect(() => {
    let riveInstance: any = null;

    const loadRive = async () => {
      try {
        const rive = await import('@rive-app/canvas');
        if (!canvasRef.current) return;

        riveInstance = new rive.Rive({
          src: '/gorilla.riv',
          canvas: canvasRef.current,
          artboard: 'Cut Long',
          stateMachines: 'State Machine 1',
          autoplay: true,
          automaticallyHandleEvents: true,
          layout: new rive.Layout({
            fit: rive.Fit.Contain,
            alignment: rive.Alignment.BottomCenter,
          }),
          onLoad: () => {
            riveInstance.resizeDrawingSurfaceToCanvas();
          },
        });

        const handleResize = () => {
          if (riveInstance) riveInstance.resizeDrawingSurfaceToCanvas();
        };

        const handlePointer = (e: MouseEvent) => {
          if (canvasRef.current) {
            canvasRef.current.dispatchEvent(
              new PointerEvent('pointermove', {
                clientX: e.clientX,
                clientY: e.clientY,
                bubbles: true,
              })
            );
          }
        };

        window.addEventListener('resize', handleResize);
        window.addEventListener('mousemove', handlePointer, { passive: true });

        // QA DNA Gorilla Parallax Smoothstep Sink on Scroll
        const heroSection = document.getElementById('hero-stage');
        const gorillaEl = containerRef.current;
        let ticking = false;

        const updateGorillaSink = () => {
          ticking = false;
          if (!heroSection || !gorillaEl) return;
          if ((window as any).__isPullAnimationActive) return;
          const heroH = heroSection.offsetHeight;
          const scrollY = window.pageYOffset || document.documentElement.scrollTop;
          const startSink = heroH * 0.15;
          const endSink = heroH * 0.85;
          let progress = (scrollY - startSink) / (endSink - startSink);
          progress = Math.max(0, Math.min(1, progress));
          progress = progress * progress * (3 - 2 * progress);
          gorillaEl.style.transform = `translate(-50%, ${(progress * 105).toFixed(2)}%)`;
        };

        window.addEventListener('scroll', () => {
          if (!ticking) {
            ticking = true;
            requestAnimationFrame(updateGorillaSink);
          }
        }, { passive: true });

        updateGorillaSink();

        return () => {
          window.removeEventListener('resize', handleResize);
          window.removeEventListener('mousemove', handlePointer);
          window.removeEventListener('scroll', updateGorillaSink);
          if (riveInstance) riveInstance.cleanup();
        };
      } catch (err) {
        console.warn('Rive runtime initialization fallback:', err);
      }
    };

    const cleanupPromise = loadRive();
    return () => {
      cleanupPromise.then((cleanup) => cleanup && cleanup());
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[min(480px,90vw)] md:w-[min(600px,56vw)] lg:w-[min(680px,50vw)] max-h-[48vh] md:max-h-[55vh] flex justify-center items-end z-30 pointer-events-auto will-change-transform"
    >
      <div className="w-full aspect-square relative -mb-[15.5%] md:-mb-[13.5%] cursor-default pointer-events-auto">
        <canvas
          ref={canvasRef}
          className="w-full h-full block pointer-events-auto"
        />
      </div>
    </div>
  );
});

Mascot.displayName = 'Mascot';

export default Mascot;
