'use client';

import React, { forwardRef, useImperativeHandle, useRef } from 'react';
import gsap from 'gsap';

export interface GorillaArmRigHandle {
  triggerPull: (
    viewportEl: HTMLElement | null,
    mascotContainerEl: HTMLElement | null,
    canvasEl: HTMLCanvasElement | null,
    onComplete?: () => void
  ) => void;
  isPulling: () => boolean;
}

const GorillaArmRig = forwardRef<GorillaArmRigHandle, {}>((_props, ref) => {
  const rigRef = useRef<HTMLDivElement>(null);
  const upperArmRef = useRef<HTMLDivElement>(null);
  const forearmRef = useRef<HTMLDivElement>(null);
  const handRef = useRef<HTMLDivElement>(null);
  const isPullingRef = useRef<boolean>(false);

  useImperativeHandle(ref, () => ({
    isPulling: () => isPullingRef.current,
    triggerPull: (
      viewportEl: HTMLElement | null,
      mascotContainerEl: HTMLElement | null,
      canvasEl: HTMLCanvasElement | null,
      onComplete?: () => void
    ) => {
      if (
        isPullingRef.current ||
        !viewportEl ||
        !rigRef.current ||
        !upperArmRef.current ||
        !forearmRef.current ||
        !handRef.current
      ) {
        return;
      }

      isPullingRef.current = true;

      // 1. Direct Mascot gaze towards incoming table off-screen (stage right)
      if (canvasEl) {
        canvasEl.dispatchEvent(
          new PointerEvent('pointermove', {
            clientX: window.innerWidth * 0.95,
            clientY: window.innerHeight * 0.45,
            bubbles: true,
          })
        );
      }

      const rig = rigRef.current;
      const upperArm = upperArmRef.current;
      const forearm = forearmRef.current;
      const hand = handRef.current;

      gsap.killTweensOf([viewportEl, rig, upperArm, forearm, hand, mascotContainerEl]);

      // Calculate off-screen reach
      const viewportRect = viewportEl.getBoundingClientRect();
      const tableStartX = window.innerWidth - viewportRect.left + 90;

      const shoulderApproxX = window.innerWidth * 0.5 + 50;
      const targetReachDistance = window.innerWidth + 80 - shoulderApproxX;
      const baseReachLength = 560;
      const reachScale = Math.max(1.15, targetReachDistance / baseReachLength);

      // Initialize table off-screen
      gsap.set(viewportEl, {
        x: tableStartX,
        opacity: 0.92,
        scale: 0.98,
        rotation: 2.2,
      });

      // Initialize arm rig for straight reach
      gsap.set(rig, {
        opacity: 0,
        scale: reachScale,
        transformOrigin: '0 0',
      });
      gsap.set(upperArm, { rotation: 45 });
      gsap.set(forearm, { rotation: 30 });
      gsap.set(hand, { rotation: -10, scale: 1 });

      const tl = gsap.timeline({
        onComplete: () => {
          isPullingRef.current = false;
          if (canvasEl) {
            canvasEl.dispatchEvent(
              new PointerEvent('pointermove', {
                clientX: window.innerWidth * 0.5,
                clientY: window.innerHeight * 0.3,
                bubbles: true,
              })
            );
          }
          if (onComplete) onComplete();
        },
      });

      // -------------------------------------------------------------
      // Phase 1: Straight Arm Reach (Reaching outside screen)
      // -------------------------------------------------------------
      tl.to(rig, { opacity: 1, duration: 0.15, ease: 'power1.out' }, 0);
      tl.to(upperArm, { rotation: -18, duration: 0.48, ease: 'power2.out' }, 0);
      tl.to(forearm, { rotation: 0, duration: 0.48, ease: 'power2.out' }, 0); // straight line
      tl.to(hand, { rotation: -6, duration: 0.48, ease: 'power2.out' }, 0);

      if (mascotContainerEl) {
        tl.to(mascotContainerEl, { rotation: 2.2, x: 16, duration: 0.48, ease: 'power2.out' }, 0);
      }

      // -------------------------------------------------------------
      // Phase 2: Grab Card Rim (Off-screen)
      // -------------------------------------------------------------
      tl.to(hand, { rotation: 18, scale: 0.95, duration: 0.14, ease: 'power1.in' }, '+=0.03');

      // -------------------------------------------------------------
      // Phase 3: The Bicep Curl & Drag (Forearm curls ~120° bend)
      // -------------------------------------------------------------
      tl.addLabel('bicepCurl', '+=0.04');

      // Forearm flexes ~120° counter-clockwise (bicep curl from right to left)
      tl.to(forearm, { rotation: -120, duration: 1.25, ease: 'power2.inOut' }, 'bicepCurl');
      tl.to(upperArm, { rotation: -32, duration: 1.25, ease: 'power2.inOut' }, 'bicepCurl');
      tl.to(hand, { rotation: -28, duration: 1.25, ease: 'power2.inOut' }, 'bicepCurl');
      tl.to(rig, { scale: 1.0, duration: 1.25, ease: 'power2.inOut' }, 'bicepCurl');
      tl.to(viewportEl, { x: 0, opacity: 1, scale: 1, rotation: 0, duration: 1.25, ease: 'power2.inOut' }, 'bicepCurl');

      if (mascotContainerEl) {
        tl.to(mascotContainerEl, { rotation: -4.5, x: -22, duration: 0.65, ease: 'power2.in' }, 'bicepCurl');
        tl.to(mascotContainerEl, { rotation: 0, x: 0, duration: 0.6, ease: 'elastic.out(1.15, 0.4)' }, 'bicepCurl+=0.65');
      }

      // -------------------------------------------------------------
      // Phase 4: Settle, Release & Arm Retraction
      // -------------------------------------------------------------
      tl.addLabel('settle', 'bicepCurl+=1.25');
      tl.to(viewportEl, { x: -6, duration: 0.08, ease: 'power1.in' }, 'settle');
      tl.to(
        viewportEl,
        {
          x: 0,
          duration: 0.35,
          ease: 'elastic.out(1.2, 0.45)',
          boxShadow: '0 0 32px rgba(29, 109, 215, 0.45), 0 8px 30px rgba(0, 0, 0, 0.08)',
          onComplete: () => {
            gsap.to(viewportEl, {
              boxShadow: '0 12px 40px rgba(0, 0, 0, 0.06)',
              duration: 0.6,
            });
          },
        },
        'settle+=0.08'
      );

      tl.to(hand, { rotation: 0, scale: 1, duration: 0.2, ease: 'power2.out' }, 'settle');
      tl.to(forearm, { rotation: 40, duration: 0.42, ease: 'power2.in' }, 'settle+=0.06');
      tl.to(upperArm, { rotation: 55, duration: 0.42, ease: 'power2.in' }, 'settle+=0.06');
      tl.to(rig, { opacity: 0, duration: 0.35, ease: 'power2.in' }, 'settle+=0.12');
    },
  }));

  return (
    <div ref={rigRef} className="gorilla-skeleton-rig" aria-hidden="true">
      {/* Bone 1: Upper Arm (Shoulder -> Elbow) */}
      <div ref={upperArmRef} className="bone-upper-arm">
        <svg className="bone-svg" viewBox="0 0 320 130" fill="none">
          <defs>
            <linearGradient id="arm-fur-grad" x1="0%" y1="100%" x2="0%" y2="0%">
              <stop offset="0%" stopColor="#0e2a52" />
              <stop offset="45%" stopColor="#1d6dd7" />
              <stop offset="100%" stopColor="#4d97f5" />
            </linearGradient>
            <filter id="fur-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="3" dy="6" stdDeviation="6" floodColor="#000" floodOpacity="0.35" />
            </filter>
          </defs>
          {/* Hairy Primate Upper Arm Silhouette */}
          <path
            d="M 30 35 Q 80 26, 140 28 L 150 14 L 160 30 Q 210 34, 255 45 L 268 32 L 272 48 Q 285 58, 280 72 L 296 76 L 278 84 L 290 92 L 270 98 Q 235 110, 185 108 L 175 122 L 165 106 Q 110 106, 60 100 L 48 114 L 40 96 Q 20 88, 20 65 Q 20 45, 30 35 Z"
            fill="url(#arm-fur-grad)"
            filter="url(#fur-shadow)"
          />
          {/* Upper arm dorsal highlight */}
          <path
            d="M 40 45 Q 120 36, 190 40 Q 235 45, 270 54"
            stroke="#82b7fc"
            strokeWidth="5"
            strokeLinecap="round"
            opacity="0.4"
          />
          {/* Primate Fur Hatching */}
          <path
            d="M 100 55 L 118 63 M 150 58 L 170 67 M 205 65 L 225 75 M 85 80 L 102 88 M 165 82 L 185 91"
            stroke="#0d284f"
            strokeWidth="3"
            strokeLinecap="round"
            opacity="0.45"
          />
        </svg>

        {/* Bone 2: Forearm (Elbow -> Wrist) */}
        <div ref={forearmRef} className="bone-forearm">
          <svg className="bone-svg" viewBox="0 0 300 110" fill="none">
            {/* Hairy Gorilla Forearm */}
            <path
              d="M 18 40 Q 70 32, 130 34 L 142 18 L 152 35 Q 205 38, 255 44 L 264 36 L 268 46 L 275 52 L 270 74 L 258 82 Q 210 88, 155 86 L 145 100 L 136 84 Q 80 84, 35 80 L 22 96 L 18 78 L 6 86 L 10 68 Q 12 52, 18 40 Z"
              fill="url(#arm-fur-grad)"
              filter="url(#fur-shadow)"
            />
            {/* Forearm top highlight */}
            <path
              d="M 30 46 Q 110 40, 180 44 Q 225 48, 258 52"
              stroke="#82b7fc"
              strokeWidth="4.5"
              strokeLinecap="round"
              opacity="0.4"
            />
            {/* Forearm fur texture */}
            <path
              d="M 65 58 L 88 65 M 120 60 L 145 68 M 185 62 L 210 71 M 95 74 L 118 80 M 155 72 L 178 79"
              stroke="#0d284f"
              strokeWidth="3"
              strokeLinecap="round"
              opacity="0.4"
            />
            {/* Jagged Fur Wrist Collar */}
            <path
              d="M 255 46 L 268 53 L 253 60 L 268 67 L 253 74 L 266 81"
              stroke="#0d284f"
              strokeWidth="3.5"
              strokeLinecap="round"
            />
          </svg>

          {/* Bone 3: Gorilla Hand / Paw (Wrist -> Fingers) */}
          <div ref={handRef} className="bone-hand">
            <svg className="bone-svg" viewBox="0 0 160 120" fill="none">
              <defs>
                <linearGradient id="gorilla-skin-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#2c3340" />
                  <stop offset="50%" stopColor="#1f242e" />
                  <stop offset="100%" stopColor="#12151b" />
                </linearGradient>
                <linearGradient id="nail-grad" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#475263" />
                  <stop offset="100%" stopColor="#0b0d11" />
                </linearGradient>
              </defs>
              {/* Broad Gorilla Palm Base */}
              <path
                d="M 15 28 C 40 22, 70 20, 92 25 C 108 30, 115 46, 110 65 C 105 84, 90 94, 62 96 C 36 98, 20 85, 14 65 Z"
                fill="url(#gorilla-skin-grad)"
                filter="url(#fur-shadow)"
              />
              {/* Primate Palm Creases */}
              <path
                d="M 42 44 Q 62 55, 80 50 M 38 62 Q 58 70, 85 66 M 52 74 Q 68 80, 82 76"
                stroke="#0d1015"
                strokeWidth="2.5"
                strokeLinecap="round"
                opacity="0.65"
              />

              {/* Gorilla Thumb */}
              <path
                d="M 35 82 C 42 98, 58 104, 72 98 C 78 90, 75 78, 62 72 Z"
                fill="url(#gorilla-skin-grad)"
              />
              <path
                d="M 66 94 C 71 93, 73 89, 70 85"
                stroke="url(#nail-grad)"
                strokeWidth="3.5"
                strokeLinecap="round"
              />

              {/* Finger 1 (Index) */}
              <path
                d="M 85 26 C 105 17, 130 22, 138 38 C 142 48, 134 56, 118 54 C 104 52, 90 44, 85 26 Z"
                fill="url(#gorilla-skin-grad)"
              />
              <path
                d="M 134 32 C 138 36, 138 42, 134 45"
                stroke="url(#nail-grad)"
                strokeWidth="3.5"
                strokeLinecap="round"
              />

              {/* Finger 2 (Middle) */}
              <path
                d="M 90 38 C 115 28, 145 33, 154 50 C 158 61, 147 70, 128 66 C 110 62, 96 52, 90 38 Z"
                fill="url(#gorilla-skin-grad)"
              />
              <path
                d="M 150 44 C 154 48, 154 55, 149 59"
                stroke="url(#nail-grad)"
                strokeWidth="4"
                strokeLinecap="round"
              />

              {/* Finger 3 (Ring) */}
              <path
                d="M 88 54 C 110 46, 138 51, 144 68 C 148 78, 136 86, 120 82 C 104 78, 92 68, 88 54 Z"
                fill="url(#gorilla-skin-grad)"
              />
              <path
                d="M 140 62 C 144 66, 143 72, 139 76"
                stroke="url(#nail-grad)"
                strokeWidth="3.5"
                strokeLinecap="round"
              />

              {/* Finger 4 (Pinky) */}
              <path
                d="M 80 68 C 100 66, 125 70, 129 85 C 131 93, 120 99, 106 93 C 94 86, 86 78, 80 68 Z"
                fill="url(#gorilla-skin-grad)"
              />
              <path
                d="M 125 79 C 128 83, 127 88, 123 91"
                stroke="url(#nail-grad)"
                strokeWidth="3.5"
                strokeLinecap="round"
              />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
});

GorillaArmRig.displayName = 'GorillaArmRig';

export default GorillaArmRig;
