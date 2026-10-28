# QA DNA Design System Specification & Hackathon Implementation Guide

> Extracted and reverse-engineered directly from **https://www.qadna.co/**.  
> Includes design tokens, fluid typography, component rules, CSS keyframes, GSAP ScrollTriggers, 3D card tilt physics, and Lenis smooth-scroll setup.

---

## 1. Visual Theme & Atmosphere

* **Aesthetic Philosophy**: High-precision, cybernetic developer infrastructure. Deep matte charcoal/black surfaces paired with electric royal blues and high-voltage neon lime accents.
* **Density & Contrast**: Spacious layout (80rem / 1280px container max-width) with aggressive micro-contrast—dim translucent text (`#fffc`, `#ffffff0d`) exploding into brilliant `#fcfcfc` on hover.
* **Geometry**: Strict tiered rounding hierarchy:
  * **Pill-shaped (999px)**: Floating nav container, floating tab indicators.
  * **Generous (40px)**: Inset section envelopes (`.scroll-dark-color`).
  * **Card Standard (20px)**: Grid cards, interactive feature wrappers.
  * **Component Standard (12px)**: Buttons, dropdown menus, input elements, badges.

---

## 2. Master Color Tokens

### Core Color Palette
| Token Variable | Hex / CSS Value | Semantic Role |
| :--- | :--- | :--- |
| `--white-100` | `#fcfcfc` | Primary canvas background & high-contrast light text |
| `--white-0-6` | `rgba(255, 255, 255, 0.6)` / `#fffc` | Secondary muted text on dark backgrounds |
| `--white-0-5` | `rgba(255, 255, 255, 0.05)` / `#ffffff0d` | Subtle glass border / divider lines on dark containers |
| `--black-100` | `#202020` | Core dark surface, card background, primary button fill |
| `--black-0-7` | `rgba(0, 0, 0, 0.7)` / `#000000b3` | Primary body text on light backgrounds |
| `--black-0-1` | `rgba(0, 0, 0, 0.1)` / `#0000001a` | Subtle container borders & shadows on light surfaces |
| `--neutral-100` | `#ebebeb` | Soft light grey borders and secondary backgrounds |
| `--neutral-200` | `#141414` | Deep obsidian canvas for inverted / contrast blocks |
| `--primary-100` | `#1d6dd7` | Electric royal blue (brand signature, active state, glow) |
| `--primary-200` | `#2859b5` | Deep sapphire blue (secondary brand, card hover state) |
| `--primary-300` | `#2d4078` | Deep midnight navy |
| `--primary-400` | `#263867` | Dark slate navy (button gradient secondary) |
| `--primary-0-6` | `rgba(40, 89, 181, 0.6)` / `#2859b599` | Translucent sapphire for focus rings & pills |
| `--accent` | `#d7f13b` | Electric chartreuse / neon lime (high-conversion CTAs & tags) |

### Surface & Elevation Rules
* **Floating Navbar**: `background: #fcfcfc; border-radius: 999px; box-shadow: 0 4px 28px rgba(0, 0, 0, 0.13); padding: 5px;`
* **Feature Cards**: `background: #202020; border-radius: 20px; color: #fcfcfc; padding: 2rem;`
* **Interactive Tile Ring**: `box-shadow: 0 0 0 2px rgba(40, 89, 181, 0.3);`
* **Background Texture**: Subtle dot grid overlay:
  ```css
  .dot-grid {
    position: absolute;
    inset: 0;
    background-image: url('https://cdn.prod.website-files.com/68f7633d849b39cf0b7cdb85/68f7633f849b39cf0b7cdc31_dot-grid-02.svg');
    opacity: 0.5;
    pointer-events: none;
    z-index: 0;
  }
  ```

---

## 3. Typography Hierarchy

### Font Families
* **Display / Brand Font**: `Creato Display` (weights: 100, 300, 400, 500, 700, 900)
* **Body / Interface Font**: `Figtree Variablefont Wght` (weights: 300 to 900) or `Host Grotesk` / `DM Sans`

### Type Scale (Fluid Viewport Sizing)
* **Hero H1 (`.heading_h1`)**:
  * CSS: `font-size: clamp(2.5rem, 14vw - 1.875rem, 6rem); font-weight: 700; line-height: 100%; letter-spacing: -0.02em;`
* **Section H2 (`.heading_h2`)**:
  * CSS: `font-size: clamp(2rem, 8vw - 0.5rem, 4rem); font-weight: 700; line-height: 110%;`
* **Kinetic Scrub Headline (`.heading_h2.reveal-type`)**:
  * CSS: `font-size: clamp(1.75rem, 6vw - 0.25rem, 3rem); font-weight: 700; line-height: 120%;`
* **Sub-Section H3 (`.heading_h3`)**:
  * CSS: `font-size: clamp(1.75rem, 7vw - 0.4375rem, 3.5rem); font-weight: 700; line-height: 120%;`
* **Card H4 (`.heading_h4`)**:
  * CSS: `font-size: clamp(1.5rem, 6vw - 0.375rem, 3rem); font-weight: 700; line-height: 120%;`
* **Component H5 (`.heading_h5`)**:
  * CSS: `font-size: clamp(1rem, 6vw - 0.875rem, 2.5rem); font-weight: 700;`
* **Label / Tag H6 (`.heading_h6`)**:
  * CSS: `font-size: clamp(1rem, 0.36vw + 0.93rem, 1.25rem); font-weight: 700;`
* **Giant KPI Stat (`.count-heading`)**:
  * CSS: `font-size: 4.5rem; font-weight: 900; color: var(--primary-200); line-height: 1;`
* **Body Copy**:
  * `body`: `font-size: 1rem (16px); line-height: 160%; color: var(--black-100);`
  * `.paragraph-lg`: `font-size: 1.125rem (18px); line-height: 150%;`
  * `.paragraph-sm`: `font-size: 0.875rem (14px); line-height: 140%;`
  * `.paragraph-xs`: `font-size: 0.75rem (12px);`

---

## 4. Component Rules & Code Patterns

### 1. Sliding Fill Buttons (Bottom-to-Top Reveal)
Buttons maintain a sharp 12px radius with a dark core (`#202020`). When hovered, an inner background layer rises from `0%` to `100%` height beneath the label.

```html
<!-- HTML Structure -->
<button class="button-primary">
  <span class="btn_fill-bg"></span>
  <span class="button-text">Book a Demo</span>
</button>
```

```css
/* CSS Implementation */
.button-primary {
  position: relative;
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 1.5rem;
  background-color: var(--black-100);
  color: #ffffff;
  border-radius: var(--border-12px);
  font-size: 14px;
  font-weight: 500;
  border: none;
  cursor: pointer;
}

.button-primary .button-text {
  position: relative;
  z-index: 2;
  transition: color 0.3s ease;
}

.button-primary .btn_fill-bg {
  position: absolute;
  inset: auto 0% 0%;
  width: 100%;
  height: 0%;
  background-color: var(--primary-200);
  transition: height 300ms ease;
  z-index: 1;
}

.button-primary:hover .btn_fill-bg {
  height: 100%;
}

/* Accent Variant */
.button-accent {
  background-color: var(--accent);
  color: var(--neutral-200);
  font-weight: 700;
}
```

---

### 2. Floating Pill Navigation with Magnet Indicator
The navbar sits fixed atop the viewport with a floating centered pill menu (`border-radius: 999px`). A sliding pill element transitions beneath the hovered item.

```html
<nav class="navbar">
  <div class="navbar-menu pill-nav">
    <div id="nav-pill-indicator" class="nav-sliding-pill"></div>
    <a href="#services" class="pill-nav-link w--current">Services</a>
    <a href="#about" class="pill-nav-link">About</a>
    <a href="#pricing" class="pill-nav-link">Pricing</a>
  </div>
</nav>
```

```css
.navbar {
  position: fixed;
  top: 0;
  width: 100%;
  min-height: 4.5rem;
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.navbar-menu.pill-nav {
  position: relative;
  background-color: #fcfcfc;
  border-radius: 999px;
  padding: 5px;
  display: flex;
  align-items: center;
  box-shadow: 0 4px 28px rgba(0, 0, 0, 0.13);
}

.pill-nav-link {
  position: relative;
  z-index: 1;
  padding: 0.75rem 1.25rem;
  color: #202020;
  text-decoration: none;
  font-size: 0.9375rem;
  font-weight: 500;
  border-radius: 999px;
  transition: color 0.2s ease;
}

.pill-nav-link.pill-link-active {
  color: #fcfcfc !important;
}

.nav-sliding-pill {
  position: absolute;
  top: 50%;
  left: 0;
  height: calc(100% - 10px);
  background-color: var(--primary-100);
  border-radius: 999px;
  pointer-events: none;
  opacity: 0;
  transform: translateY(-50%);
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1),
              width 0.2s cubic-bezier(0.4, 0, 0.2, 1),
              opacity 0.15s ease;
  z-index: 0;
}
```

---

### 3. Infinite Logo Marquee with Gradient Mask
```html
<div class="logo-component">
  <div class="logo-list">
    <!-- Repeated SVGs / Partner Logos -->
  </div>
</div>
```

```css
.logo-component {
  width: 100%;
  overflow: hidden;
  -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 8rem, #000 calc(100% - 8rem), transparent 100%);
          mask-image: linear-gradient(90deg, transparent 0, #000 8rem, #000 calc(100% - 8rem), transparent 100%);
}

.logo-list {
  display: flex;
  gap: 3rem;
  animation: qadna-logo-marquee 45s linear infinite;
  will-change: transform;
}

.logo-component:hover .logo-list {
  animation-play-state: paused;
}

@keyframes qadna-logo-marquee {
  from { transform: translateX(0); }
  to   { transform: translateX(-100%); }
}

@media (max-width: 479px) {
  .logo-component {
    -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 2.5rem, #000 calc(100% - 2.5rem), transparent 100%);
            mask-image: linear-gradient(90deg, transparent 0, #000 2.5rem, #000 calc(100% - 2.5rem), transparent 100%);
  }
}
```

---

## 5. Animation & ScrollTrigger Mechanics

### 1. GSAP + SplitType Kinetic Text Reveal on Scroll
Each character starts at opacity 0.2 and progressively illuminates to 1.0 as the user scrolls through the section.

```javascript
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import SplitType from 'split-type';

gsap.registerPlugin(ScrollTrigger);

export function initTextScrub() {
  const elements = document.querySelectorAll('.reveal-type');
  
  elements.forEach((element) => {
    const text = new SplitType(element, { types: 'chars, words' });
    
    gsap.set(text.chars, { opacity: 0.2 });
    
    gsap.to(text.chars, {
      scrollTrigger: {
        trigger: element,
        start: 'top 80%',
        end: 'top 20%',
        scrub: true,
      },
      opacity: 1,
      stagger: 0.1,
    });
  });
}
```

---

### 2. Anti-Jitter 3D Card Tilt Engine
This script solves the classic problem of 3D cards trembling or creeping because `getBoundingClientRect` reads transformed coordinates. It pre-caches untransformed bounding boxes.

```javascript
export function initAntiJitter3DTilt() {
  const SELECTOR = '.industries-card_wrapper, .abt-card_wrapper';
  const MAX_DEG = 15;
  const PERSPECTIVE = 1000;

  const cards = Array.from(document.querySelectorAll(SELECTOR));
  if (!cards.length) return;
  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;

  let boxes = [];
  let active = null;
  let cursor = null;
  let raf = 0;

  function measure() {
    const transforms = [];
    const transitions = [];
    cards.forEach((c, i) => {
      transforms[i] = c.style.transform;
      transitions[i] = c.style.transition;
      c.style.transition = 'none';
      c.style.transform = 'none';
    });
    void document.body.offsetWidth;
    boxes = cards.map((c) => {
      const r = c.getBoundingClientRect();
      return { l: r.left + window.scrollX, t: r.top + window.scrollY, w: r.width, h: r.height };
    });
    cards.forEach((c, i) => {
      c.style.transform = transforms[i];
      c.style.transition = transitions[i];
    });
  }

  function reset(card) {
    card.style.transform = `perspective(${PERSPECTIVE}px) rotateX(0deg) rotateY(0deg)`;
  }

  function clamp(v) { return Math.max(-1, Math.min(1, v)); }

  function frame() {
    raf = 0;
    if (!cursor) return;
    const { x, y } = cursor;
    let hit = -1;

    for (let i = 0; i < boxes.length; i++) {
      const b = boxes[i];
      if (x >= b.l && x <= b.l + b.w && y >= b.t && y <= b.t + b.h) {
        hit = i;
        break;
      }
    }

    if (hit === -1) {
      if (active !== null) { reset(cards[active]); active = null; }
      return;
    }

    if (active !== null && active !== hit) reset(cards[active]);
    active = hit;
    const b = boxes[hit];
    const cx = clamp((x - b.l - b.w / 2) / (b.w / 2));
    const cy = clamp((y - b.t - b.h / 2) / (b.h / 2));

    cards[hit].style.transform =
      `perspective(${PERSPECTIVE}px) rotateX(${(cy * -MAX_DEG).toFixed(2)}deg) rotateY(${(cx * MAX_DEG).toFixed(2)}deg)`;
  }

  measure();
  window.addEventListener('mousemove', (e) => {
    cursor = { x: e.pageX, y: e.pageY };
    if (!raf) raf = requestAnimationFrame(frame);
  }, { passive: true });

  window.addEventListener('resize', measure);
}
```

---

### 3. Hero Character Parallax Smoothstep Sink
The hero character element (`.hero-gorilla`) sinks downward as you scroll down the hero section using Hermite smoothstep curve interpolation:

```javascript
export function initHeroParallax() {
  const hero = document.getElementById('hero');
  const asset = document.querySelector('.hero-gorilla');
  if (!hero || !asset) return;

  asset.style.willChange = 'transform';
  let h = hero.offsetHeight;

  function update() {
    const start = h * 0.15;
    const end = h * 0.85;
    let p = (window.pageYOffset - start) / (end - start);
    p = p < 0 ? 0 : p > 1 ? 1 : p;
    // Cubic Hermite smoothstep: p * p * (3 - 2 * p)
    p = p * p * (3 - 2 * p);
    asset.style.transform = `translateY(${(p * 105).toFixed(2)}%)`;
  }

  window.addEventListener('scroll', () => requestAnimationFrame(update), { passive: true });
}
```

---

### 4. Dynamic CSS Variable Navbar Morphing on Dark Sections
When desktop users scroll over a `.scroll-dark-color` section, GSAP smoothly interpolates CSS custom properties on the navbar:

```javascript
export function initNavbarScrollMorph() {
  const navbar = document.querySelector('.navbar');
  const darkSections = document.querySelectorAll('.scroll-dark-color');
  if (!navbar || !darkSections.length || window.innerWidth <= 991) return;

  darkSections.forEach(section => {
    ScrollTrigger.create({
      trigger: section,
      start: 'top top',
      end: 'bottom top',
      onEnter: () => {
        gsap.to(navbar, {
          '--logo-blue-100': '#fcfcfc',
          '--logo-blue-200': '#d0d2d3',
          '--primary-200': '#fcfcfc',
          '--black-100': '#fcfcfc',
          '--white-0-6': 'rgba(40, 89, 181, 0.6)',
          duration: 0.3
        });
      },
      onLeave: () => {
        gsap.to(navbar, {
          clearProps: '--logo-blue-100,--logo-blue-200,--primary-200,--black-100,--white-0-6',
          duration: 0.3
        });
      },
      onEnterBack: () => {
        gsap.to(navbar, {
          '--logo-blue-100': '#fcfcfc',
          '--logo-blue-200': '#d0d2d3',
          '--primary-200': '#fcfcfc',
          '--black-100': '#fcfcfc',
          '--white-0-6': 'rgba(40, 89, 181, 0.6)',
          duration: 0.3
        });
      },
      onLeaveBack: () => {
        gsap.to(navbar, {
          clearProps: '--logo-blue-100,--logo-blue-200,--primary-200,--black-100,--white-0-6',
          duration: 0.3
        });
      }
    });
  });
}
```

---

### 5. Lenis Smooth Scrolling Setup
```javascript
import Lenis from 'lenis';

export function initLenis() {
  const lenis = new Lenis({
    duration: 1.2,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    smoothWheel: true,
  });

  function raf(time) {
    lenis.raf(time);
    requestAnimationFrame(raf);
  }
  requestAnimationFrame(raf);

  return lenis;
}
```

---

## 6. Ready-to-Drop Tailwind Config (`tailwind.config.js`)

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./src/**/*.{html,js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#fcfcfc',
        carbon: '#202020',
        obsidian: '#141414',
        accent: '#d7f13b', // Neon Chartreuse
        primary: {
          100: '#1d6dd7', // Electric Royal
          200: '#2859b5', // Sapphire
          300: '#2d4078',
          400: '#263867',
        },
        neutral: {
          100: '#ebebeb',
          200: '#141414',
        }
      },
      borderRadius: {
        'sm': '8px',
        'md': '12px',
        'card': '20px',
        'section': '40px',
        'pill': '999px',
      },
      boxShadow: {
        'pill': '0 4px 28px rgba(0, 0, 0, 0.13)',
        'card': '0 2px 12px rgba(0, 0, 0, 0.06)',
        'glow': '0 8px 20px rgba(0, 0, 0, 0.20)',
        'focus-ring': '0 0 0 2px rgba(40, 89, 181, 0.30)',
      },
      fontFamily: {
        display: ['Creato Display', 'Figtree', 'sans-serif'],
        sans: ['Figtree', 'Host Grotesk', 'DM Sans', 'sans-serif'],
      },
      animation: {
        'marquee': 'marquee 45s linear infinite',
      },
      keyframes: {
        marquee: {
          '0%': { transform: 'translateX(0%)' },
          '100%': { transform: 'translateX(-100%)' },
        }
      }
    },
  },
  plugins: [],
};
```
