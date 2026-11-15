"use client";
import { useEffect, useState } from "react";

// P-38: browser speech APIs only. Buttons are hidden where the browser lacks support.
export function useSpeechSupport() {
  const [s, setS] = useState({ recognition: false, synthesis: false });
  useEffect(() => {
    const w = window as any;
    setS({ recognition: !!(w.SpeechRecognition || w.webkitSpeechRecognition), synthesis: "speechSynthesis" in window });
  }, []);
  return s;
}

export function listen(onText: (t: string) => void, onEnd: () => void) {
  const w = window as any;
  const R = w.SpeechRecognition || w.webkitSpeechRecognition;
  const rec = new R();
  rec.lang = "en-IN";
  rec.interimResults = false;
  rec.onresult = (e: any) => onText(e.results[0][0].transcript);
  rec.onend = onEnd;
  rec.onerror = onEnd;
  rec.start();
  return rec;
}

export function speak(text: string) {
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-IN";
  window.speechSynthesis.speak(u);
}
