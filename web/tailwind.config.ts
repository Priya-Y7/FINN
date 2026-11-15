import type { Config } from "tailwindcss";
const v = (n: string) => `rgb(var(--${n}) / <alpha-value>)`;   // colours come from CSS variables so light and dark share one set of classes
export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: {
    colors: { page: v("page"), card: v("card"), line: v("line"), line2: v("line2"), ink: v("ink"), muted: v("muted"),
      accent: v("accent"), good: v("good"), bad: v("bad"), caution: v("caution"), neutral: v("neutral"),
      goodbg: v("goodbg"), badbg: v("badbg"), cautionbg: v("cautionbg"), accentbg: v("accentbg"), track: v("track") },
    fontFamily: { sans: ["Inter", "system-ui", "sans-serif"], mono: ["IBM Plex Mono", "ui-monospace", "monospace"] },
    borderRadius: { card: "14px" },
  } },
  plugins: [],
} satisfies Config;
