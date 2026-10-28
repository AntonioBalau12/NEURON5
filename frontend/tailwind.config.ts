import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "white-100": "#fcfcfc",
        "black-100": "#202020",
        "primary-100": "#d7f13b", // Neon Lime
        "primary-200": "#9ebc19", // DNA Olive Lime
        "primary-400": "#76910a", // Deep Olive Lime
        "neutral-100": "#ebebeb",
        "neutral-200": "#141414",
        "accent": "#d7f13b", // QA DNA Chartreuse Lime
        "status-true": "#10b981",
        "status-false": "#ef4444",
        "status-unsure": "#f59e0b",
      },
      fontFamily: {
        display: ["var(--font-creato)", "sans-serif"],
        body: ["var(--font-figtree)", "sans-serif"],
      },
      borderRadius: {
        "20px": "20px",
        "40px": "40px",
      },
    },
  },
  plugins: [],
};
export default config;

