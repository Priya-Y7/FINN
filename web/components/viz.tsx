"use client";
import { useId, useMemo, useRef, useState } from "react";

export const COLORS = { good: "rgb(var(--good))", bad: "rgb(var(--bad))", ink: "rgb(var(--accentline))", mute: "rgb(var(--neutral))", caution: "rgb(var(--caution))" };
export const SECTOR_COLORS = ["rgb(var(--accentline))", "#3E6A9E", "#7FA3CC", "#2F8F83", "rgb(var(--caution))", "rgb(var(--neutral))", "#6B5B95", "#C27C5B", "rgb(var(--muted))", "#A3B8D1", "#4C7A5A"];

/** Small area sparkline. Colour follows direction unless fixed. */
export function Spark({ values, w = 80, h = 28, color, fill = true, className = "" }: { values: (number | null)[]; w?: number; h?: number; color?: string; fill?: boolean; className?: string }) {
  const id = useId();
  const xs = values.filter((v): v is number => v != null);
  if (xs.length < 2) return <svg width={w} height={h} className={className} />;
  const lo = Math.min(...xs), hi = Math.max(...xs), pad = 2;
  const pts = xs.map((v, i) => [pad + (i / (xs.length - 1)) * (w - pad * 2), h - pad - ((v - lo) / (hi - lo || 1)) * (h - pad * 2)]);
  const c = color ?? (xs[xs.length - 1] >= xs[0] ? COLORS.good : COLORS.bad);
  const line = pts.map((p) => p.join(",")).join(" ");
  return (
    <svg width={w} height={h} className={className} aria-hidden>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={c} stopOpacity=".25" /><stop offset="1" stopColor={c} stopOpacity="0" /></linearGradient></defs>
      {fill && <polygon points={`${pad},${h} ${line} ${w - pad},${h}`} fill={`url(#${id})`} />}
      <polyline points={line} fill="none" stroke={c} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export type Slice = { label: string; value: number; color: string };
/** Donut with hover highlight. */
export function Donut({ slices, size = 180, thickness = 22, centerTop, centerBottom, active, onActive }: { slices: Slice[]; size?: number; thickness?: number; centerTop?: string; centerBottom?: string; active?: string | null; onActive?: (l: string | null) => void }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const r = (size - thickness) / 2, C = 2 * Math.PI * r;
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Allocation donut">
      <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--track))" strokeWidth={thickness} />
        {slices.map((s, i) => {
          const len = (s.value / total) * C, off = -acc;
          acc += len;
          const dim = active && active !== s.label;
          return (
            <circle key={s.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={s.color} strokeWidth={active === s.label ? thickness + 5 : thickness}
              strokeDasharray={`${Math.max(0, len - 2)} ${C}`} strokeDashoffset={off} opacity={dim ? 0.35 : 1}
              style={{ transition: "all .25s ease", cursor: "pointer", animation: `fadeIn .6s ease ${i * 60}ms both` }}
              onMouseEnter={() => onActive?.(s.label)} onMouseLeave={() => onActive?.(null)} onClick={() => onActive?.(active === s.label ? null : s.label)} />
          );
        })}
      </g>
      <text x="50%" y="48%" textAnchor="middle" className="fill-ink" fontSize="20" fontWeight="600" fontFamily="IBM Plex Mono">{centerTop}</text>
      <text x="50%" y="62%" textAnchor="middle" className="fill-muted" fontSize="11">{centerBottom}</text>
    </svg>
  );
}

/** Half-circle gauge, 0..1, animates on mount. */
export function Gauge({ value, label }: { value: number | null; label?: string }) {
  const r = 70, C = Math.PI * r, v = Math.max(0, Math.min(1, value ?? 0));
  const color = value == null ? COLORS.mute : v >= 0.7 ? COLORS.good : v >= 0.4 ? COLORS.caution : COLORS.bad;
  return (
    <svg viewBox="0 0 180 104" className="w-full max-w-[220px]" role="img" aria-label={`Delivery rate ${value == null ? "unknown" : Math.round(v * 100) + "%"}`}>
      <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="rgb(var(--track))" strokeWidth="14" strokeLinecap="round" />
      <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke={color} strokeWidth="14" strokeLinecap="round" strokeDasharray={`${C}`} strokeDashoffset={C * (1 - v)} style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(.2,.7,.2,1)" }} />
      <text x="90" y="82" textAnchor="middle" fontSize="30" fontWeight="600" fontFamily="IBM Plex Mono" className="fill-ink">{value == null ? "–" : `${Math.round(v * 100)}%`}</text>
      <text x="90" y="99" textAnchor="middle" fontSize="10" className="fill-muted">{label}</text>
    </svg>
  );
}

export type Pt = { label: string; y: number; v?: number; flag?: boolean; note?: string };
/** Interactive line chart: crosshair, tooltip, optional volume bars and flag markers. */
export function LineChart({ pts, height = 200, format = (n: number) => n.toFixed(2), color = COLORS.ink, showVolume = false }: { pts: Pt[]; height?: number; format?: (n: number) => string; color?: string; showVolume?: boolean }) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const id = useId();
  const W = 640, H = height, vh = showVolume ? 34 : 0, top = 10, bot = 18, ph = H - vh - top - bot;
  const geo = useMemo(() => {
    const ys = pts.map((p) => p.y), lo = Math.min(...ys), hi = Math.max(...ys), mv = Math.max(...pts.map((p) => p.v ?? 0), 1);
    const x = (i: number) => (i / Math.max(pts.length - 1, 1)) * W, y = (v: number) => top + ph - ((v - lo) / (hi - lo || 1)) * ph;
    return { lo, hi, mv, x, y };
  }, [pts, ph]);
  if (pts.length < 2) return <div className="h-24" />;
  const line = pts.map((p, i) => `${geo.x(i)},${geo.y(p.y)}`).join(" ");
  const move = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    setHover(Math.max(0, Math.min(pts.length - 1, Math.round(((e.clientX - r.left) / r.width) * (pts.length - 1)))));
  };
  const h = hover != null ? pts[hover] : null;
  return (
    <div className="relative select-none">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full touch-none" onPointerMove={move} onPointerLeave={() => setHover(null)} role="img" aria-label="Price chart">
        <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".18" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
        {[0, 0.5, 1].map((t) => <line key={t} x1="0" x2={W} y1={top + ph * t} y2={top + ph * t} stroke="rgb(var(--track))" />)}
        <text x="2" y={top + 9} fontSize="10" className="fill-muted">{format(geo.hi)}</text>
        <text x="2" y={top + ph - 3} fontSize="10" className="fill-muted">{format(geo.lo)}</text>
        {showVolume && pts.map((p, i) => <rect key={i} x={geo.x(i) - W / pts.length / 2.6} y={H - bot - ((p.v ?? 0) / geo.mv) * vh} width={Math.max(1.5, W / pts.length / 1.4)} height={((p.v ?? 0) / geo.mv) * vh} fill={hover === i ? color : "rgb(var(--line2))"} />)}
        <polygon points={`0,${top + ph} ${line} ${W},${top + ph}`} fill={`url(#${id})`} />
        <polyline points={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" pathLength={1} style={{ strokeDasharray: 1, strokeDashoffset: 0, animation: "drawLine 1s ease both", ["--len" as string]: 1 }} />
        {pts.map((p, i) => p.flag && <circle key={i} cx={geo.x(i)} cy={geo.y(p.y)} r="4.5" fill={COLORS.caution} stroke="rgb(var(--card))" strokeWidth="1.5"><title>{p.note}</title></circle>)}
        {h && <><line x1={geo.x(hover!)} x2={geo.x(hover!)} y1={top} y2={top + ph} stroke="rgb(var(--neutral))" strokeDasharray="3 3" /><circle cx={geo.x(hover!)} cy={geo.y(h.y)} r="5" fill={color} stroke="rgb(var(--card))" strokeWidth="2" /></>}
        <text x="0" y={H - 3} fontSize="10" className="fill-muted">{pts[0].label}</text>
        <text x={W} y={H - 3} fontSize="10" textAnchor="end" className="fill-muted">{pts[pts.length - 1].label}</text>
      </svg>
      {h && (
        <div className="pointer-events-none absolute top-1 rounded-lg border border-line bg-card px-2 py-1 text-[11px] shadow-md" style={{ left: `${(hover! / (pts.length - 1)) * 100}%`, transform: `translateX(${hover! > pts.length * 0.6 ? "-105%" : "8px"})` }}>
          <p className="text-muted">{h.label}</p><p className="font-mono font-medium">{format(h.y)}</p>{h.note && <p className="text-caution">{h.note}</p>}
        </div>
      )}
    </div>
  );
}
