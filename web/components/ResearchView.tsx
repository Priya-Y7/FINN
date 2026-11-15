"use client";
import { useEffect, useRef, useState } from "react";
import { API, get, send, Research, AskResult, Promise_ } from "@/lib/api";
import { Card, Segmented } from "./ui";
import { Gauge, Spark as VSpark } from "./viz";
import InfoPop from "./InfoPop";
import SourceSheet, { Chip } from "./SourceSheet";
import { listen, useSpeechSupport } from "./useSpeech";

const STATUS: Record<string, [string, string, string]> = {
  delivered: ["✓ Delivered", "text-good", "bg-goodbg"], partly: ["◐ Partly", "text-caution", "bg-cautionbg"], missed: ["✕ Missed", "text-bad", "bg-badbg"],
  not_due: ["◷ Not yet due", "text-neutral", "bg-page"], cant_verify: ["? Can't verify", "text-neutral", "bg-page"],
};
const fmt = (v: number | null | undefined, unit: string) => v == null ? "–" : unit === "%" ? `${v.toFixed(1)}%` : unit === "crore" ? `₹${Math.round(v).toLocaleString("en-IN")} Cr` : v.toFixed(2);

function Band({ p }: { p: Promise_ }) {   // target band and actual marker
  if (p.actual == null || p.target_low == null) return null;
  const lo = p.target_low, hi = p.target_high ?? p.target_low;
  const max = Math.max(lo, hi, p.actual) * 1.15, pos = (x: number) => `${(x / max) * 100}%`;
  return (
    <div className="relative my-2 h-2 rounded bg-page" aria-hidden>
      <div className="absolute h-2 rounded bg-accent/25" style={{ left: pos(lo), width: `max(4px, calc(${pos(hi)} - ${pos(lo)}))` }} />
      <div className="absolute -top-0.5 h-3 w-1 rounded bg-accent" style={{ left: pos(p.actual) }} />
    </div>
  );
}

function Ledger({ r, ticker, open }: { r: Research; ticker: string; open: (t: string, id: string) => void }) {
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState<number | null>(null);
  const pr = r.promises;
  if (!pr.available) return <Card><p className="text-sm text-muted">{pr.reason}</p></Card>;
  const d = pr.delivery!;
  const order = ["missed", "partly", "delivered", "cant_verify", "not_due"];
  const list = [...(pr.promises ?? [])].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status)).filter((p) => filter === "all" || (filter === "missed" && p.status === "missed"));
  return (
    <div className="space-y-3">
      <Card>
        <p className="text-xs text-muted">Delivery rate<InfoPop title="Delivery rate" formula="(Delivered + 0.5 × Partly) / (Delivered + Partly + Missed)" lines={[`Based on ${d.based_on} checkable promises. Not yet due (${d.not_due}) and can't verify (${d.cant_verify}) are excluded.`]} /></p>
        <div className="mx-auto w-44"><Gauge value={d.rate} label="delivered" /></div>
        <div className="mt-1 flex justify-center gap-3 text-[11px]"><span className="text-good">✓ {pr.promises?.filter((p) => p.status === "delivered").length}</span><span className="text-caution">◐ {pr.promises?.filter((p) => p.status === "partly").length}</span><span className="text-bad">✕ {pr.promises?.filter((p) => p.status === "missed").length}</span><span className="text-neutral">◷ {d.not_due + d.cant_verify}</span></div>
        <ul className="mt-3 space-y-1 text-sm">{pr.verdict?.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
        {!pr.verdict?.by_model && <p className="mt-1 text-[11px] text-muted">Verdict written by rules (no AI key set).</p>}
        {pr.calls_note && <p className="mt-1 text-xs text-caution">● {pr.calls_note}</p>}
      </Card>
      <div className="flex gap-2 text-xs">
        {[["all", "All"], ["missed", "Missed"], ["flags", `Flags (${pr.flags?.length ?? 0})`]].map(([k, l]) => <button key={k} onClick={() => setFilter(k)} className={`rounded-full border px-3 py-1 ${filter === k ? "border-accent bg-accent text-white" : "border-line bg-card"}`}>{l}</button>)}
      </div>
      {filter === "flags" ? (pr.flags?.length ? pr.flags.map((f, i) => (
        <Card key={i} className="!p-3"><p className="text-sm"><span className="text-caution">⚑ </span>{f.text}</p>{f.ids?.map((id) => <Chip key={id} id={id} ticker={ticker} onOpen={open} />)}</Card>
      )) : <p className="text-sm text-muted">No flags.</p>) : list.map((p, i) => {
        const [lab, tone, bg] = STATUS[p.status];
        return (
          <Card key={i} className="!p-3">
            <button className="w-full text-left" onClick={() => setExpanded(expanded === i ? null : i)}>
              <div className="flex items-start justify-between"><p className="text-sm font-medium">{p.metric_name} · {p.horizon_label}</p><span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${tone} ${bg}`}>{lab}</span></div>
              <p className="mt-1 text-xs text-muted">Promised on {p.call} call: {p.kind === "numeric" ? `${p.target_high != null && p.target_high !== p.target_low ? `${p.target_low}–${p.target_high}` : p.target_low}${p.unit === "%" ? "%" : " crore"}` : p.kind === "directional" ? `${p.direction === "down" ? "lower" : "higher"}` : "qualitative"}</p>
              <p className="text-xs">Delivered: <span className="font-mono">{p.status === "not_due" ? "not yet due" : fmt(p.actual, p.unit)}</span>{p.gap_bps != null && <span className={`ml-2 font-mono ${p.gap_bps >= 0 ? "text-good" : "text-bad"}`}>{p.gap_bps >= 0 ? "+" : ""}{Math.round(p.gap_bps)} bps</span>}</p>
              <Band p={p} />
            </button>
            {expanded === i && <div className="mt-1 border-t border-line pt-2 text-xs"><p className="italic">“{p.quote}”</p><p className="mt-1 text-muted">{p.note}</p><div className="mt-1"><Chip id={p.source_id} label={p.source_label} ticker={ticker} onOpen={open} /></div></div>}
          </Card>
        );
      })}
    </div>
  );
}

function Snapshot({ r }: { r: Research }) {
  const s = r.snapshot;
  if (!s.available) return <Card><p className="text-sm text-muted">{s.reason}</p></Card>;
  const t = s.trajectory!;
  const maxR = Math.max(...t.revenue.map((x) => x ?? 0), 1);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        {s.tiles!.map((x) => (
          <div key={x.key} className="rounded-card border border-line bg-card p-3">
            <p className="text-[11px] text-muted">{x.label}<InfoPop title={x.label} formula={x.formula} lines={[]} /></p>
            <p className="font-mono text-lg font-medium">{x.value == null ? "–" : x.unit === "crore" ? `₹${Math.round(x.value).toLocaleString("en-IN")} Cr` : x.unit === "%" ? `${x.value.toFixed(1)}%` : `${x.value.toFixed(2)}x`}</p>
            <VSpark values={x.spark} w={90} h={26} />
          </div>
        ))}
      </div>
      {s.callouts!.map((c, i) => <Card key={i} className="!p-3"><p className="text-sm"><span className={c.kind === "growing" ? "text-good" : "text-caution"}>● </span>{c.text}</p></Card>)}
      <Card>
        <p className="mb-2 text-sm font-semibold">Revenue and PAT by year<InfoPop title="Trajectory" formula="CAGR = (X_end / X_start)^(1/n) − 1" lines={["Bars: revenue (grey) and PAT (blue). Line: operating margin."]} /></p>
        <svg viewBox="0 0 358 120" className="w-full" role="img" aria-label="Revenue, PAT and margin by year">
          {t.years.map((y, i) => { const w = 358 / t.years.length; const rh = ((t.revenue[i] ?? 0) / maxR) * 90, ph = ((t.pat[i] ?? 0) / maxR) * 90;
            return <g key={y}><rect x={i * w + 2} y={100 - rh} width={w / 2 - 2} height={rh} fill="rgb(var(--line2))" /><rect x={i * w + w / 2} y={100 - ph} width={w / 2 - 2} height={ph} fill="rgb(var(--accentline))" /><text x={i * w + w / 2} y={114} fontSize="7" textAnchor="middle" fill="rgb(var(--muted))">{y}</text></g>; })}
          <polyline fill="none" stroke="rgb(var(--caution))" strokeWidth="1.5" points={t.margin.map((m, i) => `${i * (358 / t.years.length) + 358 / t.years.length / 2},${100 - ((m ?? 0) / 40) * 90}`).join(" ")} />
        </svg>
      </Card>
      <Card>
        <p className="text-sm font-semibold">Health</p>
        <p className="mt-1 text-xs text-muted">Free cash flow = cash from operations − capex</p>
        <ul className="mt-1 space-y-0.5 text-xs">{s.health!.fcf.map((f) => <li key={f.year} className="flex justify-between"><span>{f.year} FCF</span><span className={`font-mono ${(f.value ?? 0) >= 0 ? "text-good" : "text-bad"}`}>{f.value == null ? "–" : `₹${Math.round(f.value).toLocaleString("en-IN")} Cr`}</span></li>)}</ul>
        <ul className="mt-2 space-y-0.5 text-xs">{s.health!.working_capital_days.map((f) => <li key={f.year} className="flex justify-between"><span>{f.year} working-capital days</span><span className="font-mono">{f.days == null ? "–" : Math.round(f.days)}</span></li>)}</ul>
      </Card>
    </div>
  );
}

function BullBear({ r, ticker, open }: { r: Research; ticker: string; open: (t: string, id: string) => void }) {
  const b = r.bull_bear;
  if (!b.available) return <Card><p className="text-sm text-muted">{b.reason}</p></Card>;
  const block = (title: string, pts: { text: string; ids: string[] }[], bg: string, tone: string) => (
    <section className={`rounded-card border border-line p-3 ${bg}`}><p className={`mb-2 text-sm font-semibold ${tone}`}>{title}</p>
      <ul className="space-y-2">{pts.map((p, i) => <li key={i} className="text-sm">{p.text}<div className="mt-1">{Array.from(new Set(p.ids)).map((id) => <Chip key={id} id={id} label={b.sources?.[id]?.label} ticker={ticker} onOpen={open} />)}</div></li>)}</ul></section>
  );
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {block("▲ Bull case", b.bull!, "bg-goodbg", "text-good")}
      {block("▼ Bear case", b.bear!, "bg-badbg", "text-bad")}
      <p className="px-1 text-[11px] text-muted md:col-span-2">{b.footer}{!b.by_model && " Written by rules from computed figures (no AI key set)."}</p>
    </div>
  );
}

export default function ResearchView({ ticker, filing, name }: { ticker: string; filing?: string | null; name?: string }) {
  const [r, setR] = useState<Partial<Research>>({});
  const [steps, setSteps] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<"pvd" | "snap" | "bb">("pvd");
  const [src, setSrc] = useState<{ ticker: string; id: string } | null>(null);
  const [chat, setChat] = useState<{ q: string; a?: AskResult; err?: string }[]>([]);
  const [q, setQ] = useState("");
  const session = useRef<string>("");
  const speech = useSpeechSupport();
  const [listening, setListening] = useState(false);
  useEffect(() => { session.current = (typeof window !== "undefined" && (sessionStorage.getItem("finn_sid") || (() => { const s = Math.random().toString(36).slice(2); sessionStorage.setItem("finn_sid", s); return s; })())) || "anon"; }, []);
  useEffect(() => {
    setR({}); setSteps([]); setDone(false); setErr(null); setChat([]);
    const es = new EventSource(`${API}/research/${ticker}/stream`);
    es.addEventListener("step", (e) => setSteps((s) => [...s, JSON.parse((e as MessageEvent).data).text]));
    es.addEventListener("section", (e) => { const { name, data } = JSON.parse((e as MessageEvent).data); setR((x) => ({ ...x, [name]: data })); });
    es.addEventListener("error", (e) => { const d = (e as MessageEvent).data; if (d) setErr(JSON.parse(d).text); });
    es.addEventListener("done", () => { setDone(true); es.close(); });
    return () => es.close();
  }, [ticker]);
  const full = r as Research;
  const ask = async (text: string) => {
    if (!text.trim()) return;
    setChat((c) => [...c, { q: text }]); setQ("");
    try {
      const res = await fetch(`${API}/research/${ticker}/ask`, { method: "POST", headers: { "Content-Type": "application/json", "X-Session": session.current }, body: JSON.stringify({ question: text, filing_id: filing }) });
      const body = await res.json();
      setChat((c) => c.map((m, i) => i === c.length - 1 ? (res.ok ? { ...m, a: body } : { ...m, err: body.detail }) : m));
    } catch { setChat((c) => c.map((m, i) => i === c.length - 1 ? { ...m, err: "Could not reach the server." } : m)); }
  };
  const skeleton = <div className="h-24 animate-pulse rounded-card bg-line" aria-label="Loading" />;
  return (
    <div className="pb-24">
      <p className="mb-2 text-sm"><span className="font-mono font-medium">{ticker}</span> <span className="text-muted">{name ?? full.name}</span></p>
      {full.sample && <p className="mb-2 rounded-lg border border-line bg-card px-3 py-2 text-xs text-caution">● Sample data: synthetic financials and call transcripts.</p>}
      {!done && steps.length > 0 && (
        <div className="mb-3 rounded-card border border-line bg-card p-3" aria-live="polite">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium"><span className="dot-pulse h-2 w-2 rounded-full bg-accent" />Researching {ticker}…</div>
          <ol className="space-y-1">{steps.slice(-4).map((t, i, a) => <li key={t + i} className={`fade-in flex items-center gap-2 text-xs ${i === a.length - 1 ? "text-ink" : "text-muted"}`}><span className={i === a.length - 1 ? "text-accent" : "text-good"}>{i === a.length - 1 ? "◔" : "✓"}</span>{t}</li>)}</ol>
          <div className="mt-2 h-1 overflow-hidden rounded bg-page"><div className="h-1 rounded bg-accent transition-all duration-500" style={{ width: `${[full.snapshot, full.promises, full.bull_bear].filter(Boolean).length * 33 + 10}%` }} /></div>
        </div>)}
      {err && <p className="mb-2 text-xs text-bad">Something failed: {err}</p>}
      <Segmented value={tab} onChange={setTab} className="mb-3" options={[{ value: "pvd", label: "Promised vs Delivered" }, { value: "snap", label: "Snapshot" }, { value: "bb", label: "Bull vs Bear" }]} />
      <div key={tab} className="fade-in">
      {tab === "pvd" && (full.promises ? <Ledger r={full} ticker={ticker} open={(t, id) => setSrc({ ticker: t, id })} /> : skeleton)}
      {tab === "snap" && (full.snapshot ? <Snapshot r={full} /> : skeleton)}
      {tab === "bb" && (full.bull_bear ? <BullBear r={full} ticker={ticker} open={(t, id) => setSrc({ ticker: t, id })} /> : skeleton)}
      </div>
      <div className="mt-4 space-y-3">
        {chat.map((m, i) => (
          <div key={i}>
            <p className="ml-auto w-fit max-w-[85%] rounded-xl bg-accent px-3 py-2 text-sm text-white">{m.q}</p>
            <div className="mt-2 rounded-card border border-line bg-card p-3 text-sm">
              {m.err ? <span className="text-bad">{m.err}</span> : !m.a ? <span className="text-muted">Searching the company documents…</span> :
                m.a.found ? m.a.answer.map((s, j) => <p key={j} className="mb-1">{s.text} {Array.from(new Set(s.ids)).map((id) => <Chip key={id} id={id} label={m.a!.sources[id]?.label} ticker={ticker} onOpen={(t, x) => setSrc({ ticker: t, id: x })} />)}</p>) : <span>{m.a.text}</span>}
              {m.a && !m.a.by_model && m.a.found && <p className="mt-1 text-[11px] text-muted">Extracted passage (no AI key set).</p>}
            </div>
          </div>
        ))}
      </div>
      <div className="fixed bottom-14 left-0 right-0 z-10 border-t border-line bg-page/95 backdrop-blur lg:bottom-0 lg:left-[var(--side)] transition-[left] duration-300">
        <div className="mx-auto max-w-[430px] px-4 py-2 lg:max-w-3xl">
          {!chat.length && full.promises?.chips && <div className="mb-2 flex gap-2 overflow-x-auto">{full.promises.chips.map((c) => <button key={c} onClick={() => ask(c)} className="shrink-0 rounded-full border border-line bg-card px-3 py-1 text-xs">{c}</button>)}</div>}
          <form onSubmit={(e) => { e.preventDefault(); ask(q); }} className="flex gap-2">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Ask about ${ticker}…`} className="min-w-0 flex-1 rounded-lg border border-line bg-card px-3 py-2 text-sm" />
            {speech.recognition && <button type="button" aria-label={listening ? "Listening" : "Speak your question"} aria-pressed={listening} onClick={() => { setListening(true); listen((t) => setQ(t), () => setListening(false)); }} className={`flex items-center justify-center rounded-lg border px-2.5 transition-colors ${listening ? "border-accent bg-accent text-white" : "border-line bg-card text-ink hover:border-accent"}`}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><rect x="9" y="2.5" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0" /><path d="M12 18v3.5" /></svg></button>}
            <button className="rounded-lg bg-accent px-3 text-sm font-medium text-white">Ask</button>
          </form>
          <p className="mt-1 text-[10px] text-muted">Answers come from company documents only. Not advice.</p>
        </div>
      </div>
      <SourceSheet target={src} onClose={() => setSrc(null)} />
    </div>
  );
}
