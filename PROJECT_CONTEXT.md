# PROJECT_CONTEXT.md — AI Agent Arena (NEURON5)

> **Historical design reference**: This document describes the original static prototypes and migration plan. Those prototypes, root assets and the unused SplitType dependency were removed during repository cleanup. The running application is in `frontend/`, with assets in `frontend/public/` and the API in `backend/`. Use `README.md` and `backend/README.md` for current startup instructions; the examples and file inventory below are historical.

---

## 1. Project Overview & Hackathon Objectives

* **Hackathon**: nexxtai hackathon.
* **Challenge Track**: **"AI Agent Arena"** by QA DNA (https://www.qadna.co/).
* **Team & Brand**: **NEURON5**.
* **Visual Identity**: Recreate QA DNA's signature aesthetic:
  * High-precision developer infrastructure aesthetic.
  * Deep matte carbon surfaces (`#202020`) with electric royal blue (`#1d6dd7`) and cyber neon lime (`#d7f13b`).
  * Kinetic scroll triggers and interactive Rive vector animations.

---

## 2. Selected Tech Stack

* **Core Framework**: **Next.js 15+ (App Router)** with **TypeScript**
* **Styling**: **Tailwind CSS** (configured with QA DNA design tokens)
* **Vector Animation & Mascot**: **`@rive-app/react-canvas`**
* **Smooth Scrolling**: **`lenis`**
* **Scroll Triggers & Kinetic Reveals**: **`gsap`** + **`ScrollTrigger`** + **`split-type`** (or **`framer-motion`**)
* **Icons**: **`lucide-react`**
* **Font Delivery**: `next/font/local` using local `Creato Display` and `Figtree` files

---

## 3. Brand & Visual Guidelines

### A. Top Header
* **Position**: Fixed top-left corner (`padding: 2.25rem 4vw`).
* **Logo Text**: **`NEURON5`**
  * `NEURON` rendered in QA DNA black (`#202020`).
  * `5` rendered in QA DNA electric blue (`#1d6dd7`).
  * **Typography**: `Creato Display` / `Figtree` 900 (Black weight), uppercase, letter-spacing `-0.03em`.
  * **Interaction**: Completely static/stationary — **NO** `translateY` or `transform` on hover.
  * **Navbar items**: The central pill menu and top-right "Get Started" button are omitted for the teaser/initial phase.

### B. Centered Hero Section
* **Main Title**:
  ```
  AI AGENT ARENA
  POWERED BY NEURON5
  ```
  * Uppercase, centered, line-height `1.1`, letter-spacing `-0.025em`, color `#202020`.
  * Fluid responsive size: `font-size: clamp(2.25rem, 5.5vw, 4.35rem)`.
* **Subtitle**: `Coming soon.`
  * Color: `rgba(0, 0, 0, 0.7)` (`--black-0-7`), `font-size: 1.125rem`, weight `500`.

### C. Background Canvas
* Base color: `#fcfcfc` (`--white-100`).
* Texture: Subtle dot grid overlay repeating tile (`dot-grid.svg`) at `55%` opacity.

---

## 4. The Interactive Mascot (QA DNA Gorilla)

### Asset Details
* **Source**: Extracted from QA DNA's CDN (`6911b9a00594909c6e57113c_gorilla_cut-long.riv`).
* **Local File**: `gorilla.riv` (9,973 bytes).
* **Base64 Offline Buffer**: `mascot-asset.js` (enables zero-CORS, offline execution).
* **Rive Artboard**: `'Cut Long'`
* **Rive State Machine**: `'State Machine 1'`

### State Machine Inputs & Behaviors
* **Idle State**: Peeks over the bottom edge of the viewport with sunglasses resting over his eyes.
* **Proximity / Hover State**:
  * Triggers: `Near head Hover`, `Face Hover`, `Near Head In`.
  * The mascot lifts his sunglasses up onto his forehead (`Glasses OFF`).
  * Reveals large cartoon white eyes with star/sparkle pupils.
* **Eye Cursor Tracking**:
  * Inputs / Layers: `L_pupil Follow`, `R_pupil Follow`.
  * The pupils smoothly follow the cursor coordinate across the screen.
* **Mouse Leave**:
  * Triggers: `Near Head Out`, `Face Hover Out`.
  * Sunglasses smoothly slide back down over his eyes (`Glasses ON`).

---

## 5. Master Design Tokens

### Color Palette
```css
:root {
  --white-100: #fcfcfc;                 /* Primary canvas / light text */
  --white-0-6: rgba(255, 255, 255, 0.6); /* Secondary translucent light text */
  --white-0-5: rgba(255, 255, 255, 0.05);/* Subtle card border / divider */
  --black-100: #202020;                 /* Core dark surface, card fill, primary button */
  --black-0-7: rgba(0, 0, 0, 0.7);      /* Primary body text on light backgrounds */
  --black-0-1: rgba(0, 0, 0, 0.1);      /* Card borders / subtle drop shadow */
  --neutral-100: #ebebeb;               /* Light grey container / borders */
  --neutral-200: #141414;               /* Deep obsidian dark background */
  --primary-100: #1d6dd7;               /* Electric Royal Blue (brand signature) */
  --primary-200: #2859b5;               /* Deep Sapphire Blue (card hover fill) */
  --primary-300: #2d4078;               /* Midnight navy */
  --primary-400: #263867;               /* Deep slate navy */
  --primary-0-6: rgba(40, 89, 181, 0.6);/* Translucent sapphire ring */
  --accent: #d7f13b;                    /* High-voltage neon lime / chartreuse */
}
```

### Corner Radius Hierarchy
* **Pill (`999px`)**: Floating nav container, sliding active tabs.
* **Section Envelopes (`40px`)**: Inset dark sections (`.scroll-dark-color`).
* **Cards & Hero Wrappers (`20px`)**: Feature cards, CI cards, blog cards.
* **Components (`12px`)**: Buttons, dropdown menus, inputs, badges.

### Shadows & Elevation
* **Pill Nav**: `0 4px 28px rgba(0, 0, 0, 0.13)`
* **Card Elevation**: `0 2px 12px rgba(0, 0, 0, 0.06)`
* **Hover Glow / Auto-Pulse**: `0 8px 20px rgba(0, 0, 0, 0.20)`
* **Focus Ring**: `0 0 0 2px rgba(40, 89, 181, 0.30)`

---

## 6. Component & Animation Recipes

### 1. Sliding Fill Button (Bottom-to-Top)
```html
<button class="button-primary">
  <span class="btn_fill"></span>
  <span class="button-text">Explore Arena</span>
</button>
```
```css
.button-primary {
  position: relative;
  overflow: hidden;
  background-color: #202020;
  color: #fff;
  border-radius: 12px;
  padding: 0.5rem 1.5rem;
  border: none;
  cursor: pointer;
}
.button-primary .button-text {
  position: relative;
  z-index: 2;
}
.button-primary .btn_fill {
  position: absolute;
  inset: auto 0% 0%;
  width: 100%;
  height: 0%;
  background-color: #2859b5;
  transition: height 300ms ease;
  z-index: 1;
}
.button-primary:hover .btn_fill {
  height: 100%;
}
```

### 2. Kinetic Text Scrub (GSAP + SplitType)
```javascript
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import SplitType from 'split-type';

gsap.registerPlugin(ScrollTrigger);

const split = new SplitType('.reveal-type', { types: 'chars, words' });
gsap.set(split.chars, { opacity: 0.2 });
gsap.to(split.chars, {
  scrollTrigger: {
    trigger: '.reveal-type',
    start: 'top 80%',
    end: 'top 20%',
    scrub: true,
  },
  opacity: 1,
  stagger: 0.1,
});
```

### 3. Infinite Logo Marquee with Linear Gradient Mask
```css
.logo-marquee-wrapper {
  overflow: hidden;
  mask-image: linear-gradient(90deg, transparent 0, #000 8rem, #000 calc(100% - 8rem), transparent 100%);
  -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 8rem, #000 calc(100% - 8rem), transparent 100%);
}
.logo-list {
  display: flex;
  gap: 3rem;
  animation: logo-marquee 45s linear infinite;
}
.logo-marquee-wrapper:hover .logo-list {
  animation-play-state: paused;
}
@keyframes logo-marquee {
  from { transform: translateX(0); }
  to   { transform: translateX(-100%); }
}
```

---

## 7. Local Files Available in Workspace

```
e:\programare\AI-Agent-Arena-NEURON5\
├── DESIGN.md               # Full design system specification
├── PROJECT_CONTEXT.md      # This context continuity document
├── gorilla.riv             # Native 9.9KB Rive binary mascot file
├── mascot-asset.js         # Base64 fallback for instant Rive loading
├── dot-grid.svg            # Background dot pattern SVG
├── rive.min.js             # Local Rive Canvas runtime
├── qadna-tokens.css        # CSS variables & utility styles
├── index.html              # Complete functioning prototype landing page
├── server.js               # Zero-dependency local Node preview server
├── package.json            # Project manifest (npm start -> node server.js)
└── fonts/                  # Extracted brand fonts
    ├── CreatoDisplay-Black.otf
    ├── CreatoDisplay-Bold.otf
    ├── CreatoDisplay-Medium.otf
    ├── CreatoDisplay-Regular.otf
    └── Figtree-Variable.ttf
```

---

## 8. Next.js Migration Checklist

When ready to scaffold the Next.js App Router codebase:
1. Initialize Next.js:
   ```bash
   npx create-next-app@latest ./ --typescript --tailwind --app --src-dir --eslint
   ```
2. Install animation dependencies:
   ```bash
   npm install @rive-app/react-canvas lenis gsap split-type lucide-react
   ```
3. Copy local assets into `/public`:
   * Move `gorilla.riv` and `dot-grid.svg` into `public/`.
   * Move `fonts/` into `src/app/fonts/` and configure with `next/font/local`.
4. Configure `tailwind.config.ts` using the colors, radii, and shadows specified in Section 5 above.
5. Create `<Mascot />` component using `@rive-app/react-canvas` with `artboard: 'Cut Long'` and `stateMachines: 'State Machine 1'`.
