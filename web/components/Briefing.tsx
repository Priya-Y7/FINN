"use client";
import { useEffect, useState } from "react";
import { speak, useSpeechSupport } from "./useSpeech";
import { usePrefs } from "./Prefs";

// P-37: shown once a day per browser, dismissible, reopened from the bell.
export default function Briefing({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const speech = useSpeechSupport();
  const { prefs } = usePrefs();
  useEffect(() => {
    try { setOpen(localStorage.getItem("finn_briefing_day") !== new Date().toDateString()); } catch { setOpen(true); }
  }, []);
  const close = () => { setOpen(false); try { localStorage.setItem("finn_briefing_day", new Date().toDateString()); } catch {} };
  if (!prefs.briefing) return null;
  if (!open) return (
    <button aria-label="Open briefing" onClick={() => setOpen(true)} className="press mb-3 inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted hover:border-accent hover:text-accent">🔔 Today’s briefing</button>
  );
  return (
    <div role="region" aria-label="Briefing" className="reveal relative mb-4 overflow-hidden rounded-card bg-gradient-to-br from-[#1F3A5F] to-[#2E5282] p-5 text-white">
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10" />
      <p className="text-[11px] font-semibold uppercase tracking-wider text-white/70">Briefing</p>
      <p className="mt-2 max-w-xl text-[17px] font-medium leading-snug">{text}</p>
      <div className="mt-4 flex items-center gap-4 text-xs">
        {speech.synthesis && <button onClick={() => speak(text)} aria-label="Read briefing aloud" className="press rounded-full bg-white/15 px-3 py-1.5 hover:bg-white/25">🔊 Read aloud</button>}
        <button onClick={close} className="text-white/70 hover:text-white">Dismiss</button>
      </div>
    </div>
  );
}
