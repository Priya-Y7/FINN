"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Theme = "light" | "dark" | "system";
export type Prefs = { theme: Theme; fontPct: number; name: string; briefing: boolean };
const DEFAULT: Prefs = { theme: "light", fontPct: 100, name: "", briefing: true };
const KEY = "finn_prefs";

type Ctx = { prefs: Prefs; set: (p: Partial<Prefs>) => void; reset: () => void; menuOpen: boolean; openMenu: () => void; closeMenu: () => void };
const PrefsCtx = createContext<Ctx>({ prefs: DEFAULT, set: () => {}, reset: () => {}, menuOpen: false, openMenu: () => {}, closeMenu: () => {} });
export const usePrefs = () => useContext(PrefsCtx);

function apply(p: Prefs) {
  const dark = p.theme === "dark" || (p.theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.fontSize = p.fontPct && p.fontPct !== 100 ? `${(16 * p.fontPct) / 100}px` : "";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0E1116" : "#F7F7F5");
}

export function PrefsProvider({ children }: { children: React.ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => { try { const s = JSON.parse(localStorage.getItem(KEY) || "{}"); setPrefs({ ...DEFAULT, ...s }); } catch {} }, []);
  useEffect(() => {
    apply(prefs);
    if (prefs.theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => apply(prefs);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [prefs]);
  const set = useCallback((p: Partial<Prefs>) => setPrefs((cur) => { const n = { ...cur, ...p }; try { localStorage.setItem(KEY, JSON.stringify(n)); } catch {} return n; }), []);
  const reset = useCallback(() => { try { localStorage.removeItem(KEY); localStorage.removeItem("finn_briefing_day"); localStorage.removeItem("finn_side"); } catch {} setPrefs(DEFAULT); }, []);
  return <PrefsCtx.Provider value={{ prefs, set, reset, menuOpen, openMenu: () => setMenuOpen(true), closeMenu: () => setMenuOpen(false) }}>{children}</PrefsCtx.Provider>;
}
