"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export const Card = ({ children, className = "", hover = false, delay = 0 }: { children: React.ReactNode; className?: string; hover?: boolean; delay?: number }) =>
  <section style={{ animationDelay: `${delay}ms` }} className={`reveal rounded-card border border-line bg-card p-4 ${hover ? "lift" : ""} ${className}`}>{children}</section>;

export const Empty = ({ title, body, icon = "◌" }: { title: string; body: string; icon?: string }) => (
  <div className="reveal rounded-card border border-dashed border-line bg-card p-8 text-center">
    <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-page text-lg text-neutral">{icon}</div>
    <p className="text-[15px] font-medium">{title}</p><p className="mx-auto mt-1 max-w-xs text-sm text-muted">{body}</p>
  </div>
);

export const Skeleton = ({ className = "h-24" }: { className?: string }) => <div aria-label="Loading" className={`shimmer rounded-card ${className}`} />;

export function Segmented<T extends string>({ value, onChange, options, className = "" }: { value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode }[]; className?: string }) {
  const idx = Math.max(0, options.findIndex((o) => o.value === value));
  return (
    <div role="tablist" className={`relative grid rounded-xl border border-line bg-card p-1 text-xs ${className}`} style={{ gridTemplateColumns: `repeat(${options.length}, 1fr)` }}>
      <span aria-hidden className="absolute bottom-1 top-1 rounded-lg bg-accent transition-all duration-300 ease-out" style={{ width: `calc((100% - 8px) / ${options.length})`, left: `calc(4px + ${idx} * (100% - 8px) / ${options.length})` }} />
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={o.value === value} onClick={() => onChange(o.value)}
          className={`press relative z-10 rounded-lg px-2 py-2 font-medium transition-colors ${o.value === value ? "text-white" : "text-muted hover:text-ink"}`}>{o.label}</button>
      ))}
    </div>
  );
}

export const Chipbtn = ({ on, onClick, children }: { on?: boolean; onClick: () => void; children: React.ReactNode }) =>
  <button onClick={onClick} className={`press shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${on ? "border-accent bg-accent text-white" : "border-line bg-card text-muted hover:border-accent hover:text-accent"}`}>{children}</button>;

// ---- toasts ----
const ToastCtx = createContext<(msg: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string }[]>([]);
  const n = useRef(0);
  const push = useCallback((msg: string) => {
    const id = ++n.current;
    setItems((s) => [...s, { id, msg }]);
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-20 left-0 right-0 z-50 flex flex-col items-center gap-2 lg:bottom-6">
        {items.map((t) => <div key={t.id} style={{ animation: "toastIn .25s ease both" }} className="pointer-events-auto rounded-xl bg-ink px-4 py-2 text-sm text-card shadow-lg">{t.msg}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}

export function useCountUp(target: number, ms = 800) {
  const [v, setV] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const start = performance.now(), a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms), e = 1 - Math.pow(1 - p, 3);
      setV(a + (target - a) * e);
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}
export function Num({ value, format, className = "" }: { value: number; format: (n: number) => string; className?: string }) {
  const v = useCountUp(value);
  return <span className={className}>{format(v)}</span>;
}
