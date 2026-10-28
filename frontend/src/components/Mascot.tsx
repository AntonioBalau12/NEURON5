'use client';

import React, { useEffect, useRef } from 'react';

export default function Mascot() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

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

        return () => {
          window.removeEventListener('resize', handleResize);
          window.removeEventListener('mousemove', handlePointer);
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
      className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[min(340px,80vw)] md:w-[min(440px,45vw)] max-h-[38vh] md:max-h-[42vh] flex justify-center items-end z-10 pointer-events-auto"
    >
      <div className="w-full aspect-square relative -mb-[15.5%] md:-mb-[13.5%] cursor-default">
        <canvas ref={canvasRef} className="w-full h-full block" />
      </div>
    </div>
  );
}

