'use client';

import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import gsap from 'gsap';
import { CustomEase } from 'gsap/CustomEase';

if (typeof window !== 'undefined') {
  gsap.registerPlugin(CustomEase);
  // Silky-smooth cubic bezier curves:
  // 1. "smoothOut": cubic-bezier(0.16, 1, 0.3, 1) - aerodynamic deceleration
  // 2. "smoothInOut": cubic-bezier(0.65, 0, 0.35, 1) - symmetrical organic S-curve
  // 3. "smoothCushion": cubic-bezier(0.22, 1, 0.36, 1) - soft cushioned landing for container
  try {
    CustomEase.create('smoothOut', '0.16, 1, 0.3, 1');
    CustomEase.create('smoothInOut', '0.65, 0, 0.35, 1');
    CustomEase.create('smoothCushion', '0.22, 1, 0.36, 1');
  } catch (e) {
    // Fallback handled automatically
  }
}

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

  useEffect(() => {
    if (typeof window !== 'undefined') {
      gsap.registerPlugin(CustomEase);
      try {
        CustomEase.create('smoothOut', '0.16, 1, 0.3, 1');
        CustomEase.create('smoothInOut', '0.65, 0, 0.35, 1');
        CustomEase.create('smoothCushion', '0.22, 1, 0.36, 1');
      } catch (_) {}
    }
  }, []);

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

      // Calculate off-screen reach and partial reveal geometry
      const viewportRect = viewportEl.getBoundingClientRect();
      const tableStartX = window.innerWidth - viewportRect.left + 100;
      // Partial reveal position: left ~35% of the card is visible on screen
      const partialTableX = Math.max(window.innerWidth * 0.34, 380);

      const shoulderApproxX = window.innerWidth * 0.5 + 55;
      const targetReachDistance = window.innerWidth + 85 - shoulderApproxX;
      const baseReachLength = 560;
      const reachScale = Math.max(1.18, targetReachDistance / baseReachLength);

      // Initialize table off-screen to the right
      gsap.set(viewportEl, {
        x: tableStartX,
        opacity: 0.95,
        scale: 0.98,
        rotation: 2.5,
      });

      // Initial state: Arm completely hidden below the bottom boundary
      gsap.set(rig, {
        opacity: 0,
        y: 90,
        scale: reachScale,
        transformOrigin: '0 0',
      });
      gsap.set(upperArm, { rotation: 72 });
      gsap.set(forearm, { rotation: 52 });
      gsap.set(hand, { rotation: 10, scale: 1 });

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

      // =============================================================
      // STEP 1: Arm appearing from below (Smooth cubic-bezier)
      // Snappy upward emergence from below the bottom stage
      // =============================================================
      tl.addLabel('step1_appear');
      tl.to(
        rig,
        {
          opacity: 1,
          y: 0,
          duration: 0.18,
          ease: 'smoothOut',
        },
        'step1_appear'
      );

      tl.to(
        upperArm,
        {
          rotation: 12,
          duration: 0.18,
          ease: 'smoothOut',
        },
        'step1_appear'
      );

      tl.to(
        forearm,
        {
          rotation: 35,
          duration: 0.18,
          ease: 'smoothOut',
        },
        'step1_appear'
      );

      if (mascotContainerEl) {
        tl.to(
          mascotContainerEl,
          {
            rotation: 1.5,
            y: -8,
            duration: 0.18,
            ease: 'smoothOut',
          },
          'step1_appear'
        );
      }

      // =============================================================
      // STEP 2: Arm reaching for the table (Smooth cubic-bezier)
      // Straight-arm extension outside the screen, fingers clamp rim
      // =============================================================
      tl.addLabel('step2_reach', 'step1_appear+=0.15');
      tl.to(
        upperArm,
        {
          rotation: -18,
          duration: 0.22,
          ease: 'smoothOut',
        },
        'step2_reach'
      );

      tl.to(
        forearm,
        {
          rotation: 0, // completely straight line with upper arm
          duration: 0.22,
          ease: 'smoothOut',
        },
        'step2_reach'
      );

      tl.to(
        hand,
        {
          rotation: -8,
          duration: 0.22,
          ease: 'smoothOut',
        },
        'step2_reach'
      );

      if (mascotContainerEl) {
        tl.to(
          mascotContainerEl,
          {
            rotation: 3.5,
            x: 22,
            y: 0,
            duration: 0.22,
            ease: 'smoothOut',
          },
          'step2_reach'
        );
      }

      // Fingers snap and hook around the off-screen card border
      tl.to(
        hand,
        {
          rotation: 20,
          scale: 0.94,
          duration: 0.08,
          ease: 'smoothInOut',
        },
        'step2_reach+=0.15'
      );

      // =============================================================
      // STEP 3: Arm coming back with a part of the table (Smooth cubic-bezier)
      // Fluid initial pull brings the edge & left part of table on screen
      // =============================================================
      tl.addLabel('step3_pullPart', 'step2_reach+=0.22');

      // Forearm flexes partially (~48°) and upper arm draws back
      tl.to(
        forearm,
        {
          rotation: -48,
          duration: 0.24,
          ease: 'smoothInOut',
        },
        'step3_pullPart'
      );

      tl.to(
        upperArm,
        {
          rotation: -26,
          duration: 0.24,
          ease: 'smoothInOut',
        },
        'step3_pullPart'
      );

      tl.to(
        hand,
        {
          rotation: -14,
          duration: 0.24,
          ease: 'smoothInOut',
        },
        'step3_pullPart'
      );

      tl.to(
        rig,
        {
          scale: reachScale * 0.88,
          duration: 0.24,
          ease: 'smoothInOut',
        },
        'step3_pullPart'
      );

      // Table slides partially onto the screen
      tl.to(
        viewportEl,
        {
          x: partialTableX,
          opacity: 0.98,
          rotation: 1.4,
          duration: 0.24,
          ease: 'smoothInOut',
        },
        'step3_pullPart'
      );

      if (mascotContainerEl) {
        tl.to(
          mascotContainerEl,
          {
            rotation: -2,
            x: -10,
            duration: 0.24,
            ease: 'smoothInOut',
          },
          'step3_pullPart'
        );
      }

      // =============================================================
      // STEP 4: Arm curling to center the table (Cubic Bezier Smooth!)
      // Organic bicep curl (~120° bend) whips table into center
      // with cushioned cubic-bezier deceleration!
      // =============================================================
      tl.addLabel('step4_fullCurl', 'step3_pullPart+=0.22');

      // Forearm curls fully ~120 degrees from straight (right to left towards shoulder)
      tl.to(
        forearm,
        {
          rotation: -120, // 120-degree bicep curl flexion
          duration: 0.38,
          ease: 'smoothInOut',
        },
        'step4_fullCurl'
      );

      tl.to(
        upperArm,
        {
          rotation: -34,
          duration: 0.38,
          ease: 'smoothInOut',
        },
        'step4_fullCurl'
      );

      tl.to(
        hand,
        {
          rotation: -28,
          duration: 0.38,
          ease: 'smoothInOut',
        },
        'step4_fullCurl'
      );

      tl.to(
        rig,
        {
          scale: 1.0,
          duration: 0.38,
          ease: 'smoothInOut',
        },
        'step4_fullCurl'
      );

      // Mascot counter-balance lean and smooth natural recovery
      if (mascotContainerEl) {
        tl.to(
          mascotContainerEl,
          {
            rotation: -4,
            x: -18,
            duration: 0.2,
            ease: 'smoothInOut',
          },
          'step4_fullCurl'
        );

        tl.to(
          mascotContainerEl,
          {
            rotation: 0,
            x: 0,
            duration: 0.36,
            ease: 'smoothOut',
          },
          'step4_fullCurl+=0.2'
        );
      }

      // Table glides smoothly into center with cushioned cubic-bezier landing
      tl.to(
        viewportEl,
        {
          x: 0,
          opacity: 1,
          scale: 1,
          rotation: 0,
          duration: 0.48,
          ease: 'smoothCushion', // Silky-smooth cubic-bezier deceleration
          boxShadow: '0 12px 40px rgba(0, 0, 0, 0.06)',
        },
        'step4_fullCurl'
      );

      // Settle, release grip and retract arm below
      tl.addLabel('settle', 'step4_fullCurl+=0.44');
      tl.to(
        hand,
        {
          rotation: 0,
          scale: 1,
          duration: 0.16,
          ease: 'smoothOut',
        },
        'settle'
      );

      tl.to(
        forearm,
        {
          rotation: 48,
          duration: 0.24,
          ease: 'smoothInOut',
        },
        'settle+=0.04'
      );

      tl.to(
        upperArm,
        {
          rotation: 68,
          duration: 0.24,
          ease: 'smoothInOut',
        },
        'settle+=0.04'
      );

      tl.to(
        rig,
        {
          opacity: 0,
          y: 70,
          duration: 0.22,
          ease: 'smoothOut',
        },
        'settle+=0.06'
      );
    },
  }));

  return (
    <div ref={rigRef} className="gorilla-skeleton-rig" aria-hidden="true">
      {/* Bone 1: Upper Arm (Shoulder -> Elbow) - Solid Neon Lime, No Gradients/Highlights */}
      <div ref={upperArmRef} className="bone-upper-arm">
        <svg className="bone-svg" viewBox="0 0 320 130" fill="none">
          <defs>
            <filter id="fur-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#000" floodOpacity="0.25" />
            </filter>
          </defs>
          {/* Solid Flat Neon Lime Upper Arm Silhouette */}
          <path
            d="M 30 35 Q 80 26, 140 28 L 150 14 L 160 30 Q 210 34, 255 45 L 268 32 L 272 48 Q 285 58, 280 72 L 296 76 L 278 84 L 290 92 L 270 98 Q 235 110, 185 108 L 175 122 L 165 106 Q 110 106, 60 100 L 48 114 L 40 96 Q 20 88, 20 65 Q 20 45, 30 35 Z"
            fill="#d7f13b"
            filter="url(#fur-shadow)"
          />
        </svg>

        {/* Bone 2: Forearm (Elbow -> Wrist) - Solid Neon Lime, No Gradients/Highlights */}
        <div ref={forearmRef} className="bone-forearm">
          <svg className="bone-svg" viewBox="0 0 300 110" fill="none">
            {/* Solid Flat Neon Lime Forearm Silhouette */}
            <path
              d="M 18 40 Q 70 32, 130 34 L 142 18 L 152 35 Q 205 38, 255 44 L 264 36 L 268 46 L 275 52 L 270 74 L 258 82 Q 210 88, 155 86 L 145 100 L 136 84 Q 80 84, 35 80 L 22 96 L 18 78 L 6 86 L 10 68 Q 12 52, 18 40 Z"
              fill="#d7f13b"
              filter="url(#fur-shadow)"
            />
          </svg>

          {/* Bone 3: Gorilla Hand / Paw (Wrist -> Fingers) - Solid Charcoal & Neon Lime Nails */}
          <div ref={handRef} className="bone-hand">
            <svg className="bone-svg" viewBox="0 0 160 120" fill="none">
              {/* Solid Primate Palm Base */}
              <path
                d="M 15 28 C 40 22, 70 20, 92 25 C 108 30, 115 46, 110 65 C 105 84, 90 94, 62 96 C 36 98, 20 85, 14 65 Z"
                fill="#202020"
                filter="url(#fur-shadow)"
              />
              {/* Solid Palm Creases */}
              <path
                d="M 42 44 Q 62 55, 80 50 M 38 62 Q 58 70, 85 66 M 52 74 Q 68 80, 82 76"
                stroke="#141414"
                strokeWidth="2.5"
                strokeLinecap="round"
                opacity="0.8"
              />

              {/* Gorilla Thumb */}
              <path
                d="M 35 82 C 42 98, 58 104, 72 98 C 78 90, 75 78, 62 72 Z"
                fill="#202020"
              />
              <path
                d="M 66 94 C 71 93, 73 89, 70 85"
                stroke="#d7f13b"
                strokeWidth="3.5"
                strokeLinecap="round"
              />

              {/* Finger 1 (Index) */}
              <path
                d="M 85 26 C 105 17, 130 22, 138 38 C 142 48, 134 56, 118 54 C 104 52, 90 44, 85 26 Z"
                fill="#202020"
              />
              <path
                d="M 134 32 C 138 36, 138 42, 134 45"
                stroke="#d7f13b"
                strokeWidth="3.5"
                strokeLinecap="round"
              />

              {/* Finger 2 (Middle) */}
              <path
                d="M 90 38 C 115 28, 145 33, 154 50 C 158 61, 147 70, 128 66 C 110 62, 96 52, 90 38 Z"
                fill="#202020"
              />
              <path
                d="M 150 44 C 154 48, 154 55, 149 59"
                stroke="#d7f13b"
                strokeWidth="4"
                strokeLinecap="round"
              />

              {/* Finger 3 (Ring) */}
              <path
                d="M 88 54 C 110 46, 138 51, 144 68 C 148 78, 136 86, 120 82 C 104 78, 92 68, 88 54 Z"
                fill="#202020"
              />
              <path
                d="M 140 62 C 144 66, 143 72, 139 76"
                stroke="#d7f13b"
                strokeWidth="3.5"
                strokeLinecap="round"
              />

              {/* Finger 4 (Pinky) */}
              <path
                d="M 80 68 C 100 66, 125 70, 129 85 C 131 93, 120 99, 106 93 C 94 86, 86 78, 80 68 Z"
                fill="#202020"
              />
              <path
                d="M 125 79 C 128 83, 127 88, 123 91"
                stroke="#d7f13b"
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
