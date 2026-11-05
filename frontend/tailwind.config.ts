import type { Config } from "tailwindcss";
export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0b0c0d", 900: "#111315", 850: "#16191b", 800: "#1c2023", 700: "#262b2f", 600: "#363c41", 400: "#7d868d", 300: "#a9b1b7", 100: "#e8ecef" },
        volt: { DEFAULT: "#39ff88", dim: "#2bd36f", glow: "rgba(57,255,136,0.18)" },
        warn: "#ffb547",
        bad: "#ff5d6c",
      },
      fontFamily: { sans: ["var(--font-sans)", "system-ui", "sans-serif"], mono: ["var(--font-mono)", "ui-monospace", "monospace"] },
    },
  },
  plugins: [],
} satisfies Config;
