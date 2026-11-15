"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get, send, Rule } from "@/lib/api";
import { Card } from "@/components/ui";
import InfoPop from "@/components/InfoPop";

type Preview = { count: number; days: number; by_day: Record<string, number> };

function usePreview(type: string, params: any) {
  const [p, setP] = useState<Preview | null>(null);
  useEffect(() => {
    if (type !== "price" && type !== "volume") return;
    const t = setTimeout(() => send<Preview>("POST", "/alert-rules/preview", { type, params }).then(setP).catch(() => setP(null)), 250);
    return () => clearTimeout(t);
  }, [type, JSON.stringify(params)]);
  return p;
}
function Mini({ p }: { p: Preview }) {
  const days = Object.entries(p.by_day).sort();
  const max = Math.max(1, ...days.map(([, n]) => n));
  return <svg width="100%" height="24" aria-hidden>{days.map(([d, n], i) => <rect key={d} x={i * 8} y={24 - (n / max) * 24} width="5" height={(n / max) * 24} fill="rgb(var(--accentline))" />)}</svg>;
}

function RuleCard({ rule }: { rule: Rule }) {
  const qc = useQueryClient();
  const [params, setParams] = useState<any>(rule.params);
  const [active, setActive] = useState(rule.active);
  const preview = usePreview(rule.type, params);
  const save = async () => { await send("PUT", `/alert-rules/${rule.id}`, { type: rule.type, params, active, tickers: rule.tickers }); qc.invalidateQueries({ queryKey: ["alerts"] }); };
  const title = { price: "Price move", volume: "Volume spike", announcement: "Filing alert", confirmed: "Confirmed move" }[rule.type] ?? rule.type;
  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">{title}
          {rule.type === "price" && <InfoPop title="Unusual move" formula="z = (r_t − mean of previous 20 returns) / std dev" lines={["r_t = (P_t − P_t−1) / P_t−1 × 100 on adjusted prices."]} />}
          {rule.type === "volume" && <InfoPop title="Volume ratio" formula="VR = V_t / mean(V over previous N days, excl. today)" lines={["Skipped when average volume is very low."]} />}
        </p>
        <label className="text-xs"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> On</label>
      </div>
      {rule.type === "price" && (<>
        <div className="mt-2 flex gap-2 text-xs">
          {["z", "pct"].map((m) => <button key={m} onClick={() => setParams({ ...params, mode: m })} className={`rounded-full border px-3 py-1 ${params.mode === m ? "border-accent bg-accent text-white" : "border-line"}`}>{m === "z" ? "Unusual for this stock" : "Fixed %"}</button>)}
        </div>
        {params.mode === "z"
          ? <label className="mt-2 block text-xs">|z| ≥ <span className="font-mono">{params.z}</span><input className="w-full" type="range" min="1.5" max="4" step="0.1" value={params.z} onChange={(e) => setParams({ ...params, z: +e.target.value })} /></label>
          : <label className="mt-2 block text-xs">Move ≥ <span className="font-mono">{params.pct}%</span><input className="w-full" type="range" min="1" max="15" step="0.5" value={params.pct} onChange={(e) => setParams({ ...params, pct: +e.target.value })} /></label>}
      </>)}
      {rule.type === "volume" && (<>
        <label className="mt-2 block text-xs">Trigger ≥ <span className="font-mono">{params.ratio}x</span> average<input className="w-full" type="range" min="1.5" max="5" step="0.1" value={params.ratio} onChange={(e) => setParams({ ...params, ratio: +e.target.value })} /></label>
        <label className="block text-xs">Average over <span className="font-mono">{params.n}</span> days<input className="w-full" type="range" min="10" max="60" step="5" value={params.n} onChange={(e) => setParams({ ...params, n: +e.target.value })} /></label>
      </>)}
      {rule.type === "announcement" && (<>
        <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
          {["results", "management_change", "m&a", "fund_raise", "litigation", "credit_rating", "dividend", "capex", "press_release", "insider_trading", "pledging"].map((c) => {
            const on = params.categories.includes(c);
            return <button key={c} onClick={() => setParams({ ...params, categories: on ? params.categories.filter((x: string) => x !== c) : [...params.categories, c] })} className={`rounded-full border px-2 py-1 ${on ? "border-accent bg-accent text-white" : "border-line"}`}>{c.replace("_", " ")}</button>;
          })}
        </div>
        <label className="mt-2 block text-xs">Minimum tier
          <select className="ml-2 rounded border border-line p-1" value={params.min_tier} onChange={(e) => setParams({ ...params, min_tier: +e.target.value })}><option value={1}>Act now only</option><option value={2}>Worth knowing and up</option><option value={3}>Everything</option></select></label>
        <label className="mt-2 block text-xs">Keyword (optional)<input className="ml-2 rounded border border-line p-1" value={params.keyword || ""} onChange={(e) => setParams({ ...params, keyword: e.target.value })} /></label>
      </>)}
      {rule.type === "confirmed" && <p className="mt-2 text-xs text-muted">Adds one combined alert when a price and a volume alert fire for the same stock on the same day.</p>}
      {preview && (rule.type === "price" || rule.type === "volume") && (
        <div className="mt-2"><p className="text-xs text-muted">Would have fired <b className="text-ink">{preview.count}</b> times in the last {preview.days} days.</p><Mini p={preview} /></div>
      )}
      <button onClick={save} className="mt-3 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white">Save</button>
    </Card>
  );
}

export default function Rules() {
  const { data } = useQuery({ queryKey: ["rules"], queryFn: () => get<Rule[]>("/alert-rules") });
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div><Link href="/alerts" className="text-xs text-accent ">← Alerts</Link><h1 className="mt-1 text-xl font-semibold">Alert rules</h1><p className="text-xs text-muted">Drag a slider and see how often it would have fired in the last 30 days.</p></div>
      {data?.map((r) => <RuleCard key={r.id} rule={r} />)}
    </div>
  );
}
