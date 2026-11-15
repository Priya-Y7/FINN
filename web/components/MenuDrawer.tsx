"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Segmented, useToast } from "./ui";
import { Theme, usePrefs } from "./Prefs";

const Switch = ({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) => (
  <button role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(!on)}
    className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${on ? "bg-accent" : "bg-line2"}`}>
    <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
  </button>
);
const Row = ({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) => (
  <div className="flex items-center justify-between gap-4 py-3">
    <div className="min-w-0"><p className="text-sm font-medium">{title}</p>{hint && <p className="text-xs text-muted">{hint}</p>}</div>{children}
  </div>
);
const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="border-t border-line px-5 py-3"><p className="pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</p>{children}</section>
);

export default function MenuDrawer({ dataLabel, updated, onRefresh }: { dataLabel: string; updated?: string; onRefresh: () => void }) {
  const { prefs, set, reset, menuOpen, closeMenu } = usePrefs();
  const toast = useToast();
  const [perm, setPerm] = useState<string>("unsupported");
  useEffect(() => { if (typeof Notification !== "undefined") setPerm(Notification.permission); }, [menuOpen]);
  useEffect(() => {
    if (!menuOpen) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && closeMenu();
    window.addEventListener("keydown", k);
    const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", k); document.body.style.overflow = prev; };
  }, [menuOpen, closeMenu]);
  if (!menuOpen) return null;
  const notify = async (v: boolean) => {
    if (!v) { toast("Turn notifications off in your browser's site settings"); return; }
    if (typeof Notification === "undefined") { toast("This browser does not support notifications"); return; }
    const r = await Notification.requestPermission(); setPerm(r);
    toast(r === "granted" ? "Alerts will notify you while FINN is open" : "Notifications are blocked in your browser");
  };
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Menu">
      <div className="fade-in absolute inset-0 bg-black/40" onClick={closeMenu} />
      <aside className="drawer-in absolute left-0 top-0 flex h-full w-[88%] max-w-[360px] flex-col overflow-y-auto border-r border-line bg-card shadow-2xl">
        <div className="flex items-center justify-between px-5 pb-3 pt-5">
          <p className="text-base font-semibold">Menu</p>
          <button onClick={closeMenu} aria-label="Close menu" className="press flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-page hover:text-ink">✕</button>
        </div>
        <div className="flex items-center gap-3 px-5 pb-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent text-lg font-semibold text-white">{(prefs.name.trim()[0] || "G").toUpperCase()}</span>
          <div className="min-w-0 flex-1">
            <input value={prefs.name} onChange={(e) => set({ name: e.target.value.slice(0, 40) })} placeholder="Your name" aria-label="Your name"
              className="w-full rounded-lg border border-transparent bg-transparent px-1 py-0.5 text-[15px] font-medium outline-none placeholder:text-ink/50 hover:border-line focus:border-accent" />
          </div>
        </div>

        <Section title="Appearance">
          <div className="py-2"><Segmented<Theme> value={prefs.theme} onChange={(theme) => set({ theme })} options={[{ value: "light", label: "☀ Light" }, { value: "dark", label: "☾ Dark" }, { value: "system", label: "Auto" }]} /></div>
          <div className="py-3">
            <div className="flex items-center justify-between"><p className="text-sm font-medium">Font size</p><span className="text-xs text-muted">{prefs.fontPct}%</span></div>
            <div className="mt-2 flex items-center gap-3">
              <span className="text-xs text-muted" aria-hidden>A</span>
              <input type="range" min={85} max={130} step={5} value={prefs.fontPct} onChange={(e) => set({ fontPct: Number(e.target.value) })} aria-label="Font size" className="h-1.5 w-full cursor-pointer accent-[rgb(var(--accent))]" />
              <span className="text-lg text-muted" aria-hidden>A</span>
            </div>
          </div>
        </Section>

        <Section title="Alerts and briefing">
          <Row title="Browser notifications" hint={perm === "denied" ? "Blocked in browser settings" : "When something crosses your thresholds"}><Switch on={perm === "granted"} onChange={notify} label="Browser notifications" /></Row>
          <Row title="Daily briefing" hint="The summary card on Today"><Switch on={prefs.briefing} onChange={(briefing) => { set({ briefing }); if (briefing) try { localStorage.removeItem("finn_briefing_day"); } catch {} }} label="Daily briefing" /></Row>
          <Link href="/alerts/rules" onClick={closeMenu} className="press my-1 flex items-center justify-between rounded-lg bg-page px-3 py-2.5 text-sm font-medium text-accent">Set alert thresholds <span aria-hidden>→</span></Link>
        </Section>

        <Section title="Data">
          <Row title={dataLabel} hint={updated ? `Last refreshed ${updated}` : "Prices not loaded yet"}>
            <button onClick={() => { onRefresh(); closeMenu(); }} className="press rounded-lg border border-line bg-card px-3 py-1.5 text-xs font-medium text-accent hover:border-accent">↻ Refresh</button>
          </Row>
        </Section>

        <Section title="About">
          <button onClick={() => { reset(); toast("Preferences reset"); }} className="press mb-3 text-xs font-medium text-bad">Reset all preferences</button>
        </Section>
      </aside>
    </div>
  );
}
