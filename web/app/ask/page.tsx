"use client";
import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { API, get, pct, tone, Overview } from "@/lib/api";
import { Card, Chipbtn, Skeleton } from "@/components/ui";
import { Spark } from "@/components/viz";
import ResearchView from "@/components/ResearchView";

type C = { ticker: string; name: string; in_portfolio?: number };

function Inner() {
  const sp = useSearchParams(), router = useRouter();
  const ticker = sp.get("ticker"), filing = sp.get("filing");
  const [q, setQ] = useState("");
  const [sector, setSector] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addErr, setAddErr] = useState<string | null>(null);
  const qc = useQueryClient();
  const { data: ov } = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview[]>("/overview") });
  const { data: recent } = useQuery({ queryKey: ["recent"], queryFn: () => get<C[]>("/research/recent") });
  const sectors = useMemo(() => Array.from(new Set((ov ?? []).map((o) => o.sector))), [ov]);
  if (ticker) return <div><button onClick={() => router.push("/ask")} className="mb-3 text-xs text-accent ">← All companies</button><ResearchView ticker={ticker} filing={filing} name={ov?.find((c) => c.ticker === ticker)?.name} /></div>;
  const go = (t: string) => router.push(`/ask?ticker=${t}`);
  const sym = q.trim().toUpperCase().replace(/\.(NS|BO)$/, "");
  const canAdd = /^[A-Z0-9&-]{1,20}$/.test(sym) && !(ov ?? []).some((o) => o.ticker === sym);
  const addAndGo = async () => {        // any NSE ticker works: check it on Yahoo, load prices, then research
    setAdding(true); setAddErr(null);
    try {
      const r = await fetch(`${API}/companies/add`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker: sym }) });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || "Could not add this company");
      await qc.invalidateQueries({ queryKey: ["overview"] });
      go(body.ticker);
    } catch (e) { setAddErr(e instanceof Error ? e.message : "Could not add this company"); }
    setAdding(false);
  };
  const list = (ov ?? []).filter((o) => (!sector || o.sector === sector) && (!q || (o.name + o.ticker).toLowerCase().includes(q.toLowerCase())));
  return (
    <div className="space-y-4">
      <div className="rounded-card bg-gradient-to-br from-[#1F3A5F] to-[#2E5A8F] p-5 text-white">
        <p className="text-lg font-semibold">Ask about any company</p>
        <p className="mt-1 text-xs text-white/75">Promised vs delivered, bull vs bear, and cited answers from filings and concalls.</p>
        <div className="relative mt-3"><span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden>🔎</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search, or type any NSE ticker (e.g. TCS)" aria-label="Search company" className="w-full rounded-lg border-0 bg-card py-2.5 pl-9 pr-3 text-sm text-ink shadow-sm outline-none focus:ring-2 focus:ring-white/60" /></div>
      </div>
      {q && canAdd && (
        <button onClick={addAndGo} disabled={adding} className="press lift flex w-full items-center justify-between rounded-card border border-dashed border-accent bg-card p-3.5 text-left disabled:opacity-60">
          <span><span className="block text-sm font-medium">Research <span className="font-mono">{sym}</span> on NSE</span><span className="block text-xs text-muted">Not in your list. FINN will look it up and read its filings.</span></span>
          <span className="text-accent">{adding ? "Checking…" : "→"}</span>
        </button>)}
      {addErr && <p className="px-1 text-xs text-bad">{addErr}</p>}
      {recent && recent.length > 0 && <div><p className="mb-1.5 px-1 text-xs font-semibold text-muted">Recently researched</p><div className="flex flex-wrap gap-2">{recent.map((r) => <button key={r.ticker} onClick={() => go(r.ticker)} className="press rounded-full border border-line bg-card px-3 py-1 font-mono text-xs hover:border-accent">{r.ticker}</button>)}</div></div>}
      <div className="flex gap-2 overflow-x-auto scroll-hide"><Chipbtn on={!sector} onClick={() => setSector(null)}>All sectors</Chipbtn>{sectors.map((s) => <Chipbtn key={s} on={sector === s} onClick={() => setSector(s)}>{s}</Chipbtn>)}</div>
      {!ov && <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-24" />)}</div>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((o, i) => (
          <button key={o.ticker} onClick={() => go(o.ticker)} style={{ animationDelay: `${Math.min(i, 12) * 30}ms` }} className="reveal lift press rounded-card border border-line bg-card p-3.5 text-left">
            <div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="font-mono text-sm font-medium">{o.ticker}</p><p className="truncate text-xs text-muted">{o.name}</p></div>
              {o.in_portfolio ? <span className="rounded-full bg-accentbg px-2 py-0.5 text-[10px] font-medium text-accent">Held</span> : null}</div>
            <div className="mt-2 flex items-end justify-between"><div><p className="text-[11px] text-muted">{o.sector}</p><p className={`font-mono text-sm ${tone(o.day_change)}`}>{pct(o.day_change)}</p></div><Spark values={o.spark} w={84} h={30} /></div>
          </button>
        ))}
      </div>
      {ov && !list.length && !canAdd && <Card><p className="text-sm text-muted">No match.</p></Card>}
    </div>
  );
}
export default function Ask() { return <Suspense><Inner /></Suspense>; }
