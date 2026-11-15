"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { get, inr, pct, tone, Portfolio, HistPt, Overview } from "@/lib/api";
import { Card, Num, Skeleton } from "./ui";
import { LineChart, Spark } from "./viz";

export function PortfolioHero() {
  const { data: pf } = useQuery({ queryKey: ["portfolio"], queryFn: () => get<Portfolio>("/portfolio") });
  const { data: hist } = useQuery({ queryKey: ["hist"], queryFn: () => get<HistPt[]>("/portfolio/history?days=90") });
  if (!pf) return <Skeleton className="h-52" />;
  const up = pf.day_impact >= 0;
  return (
    <Card className="overflow-hidden !p-0">
      <div className="p-4 pb-0">
        <p className="text-xs text-muted">Portfolio value</p>
        <p className="font-mono text-[30px] font-medium leading-tight"><Num value={pf.total_value} format={inr} /></p>
        <p className={`mt-0.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-xs ${up ? "bg-goodbg text-good" : "bg-badbg text-bad"}`}>{pct(pf.day_impact_pct)} · {inr(pf.day_impact)} today</p>
      </div>
      {hist && hist.length > 2 && <div className="px-2 pb-1 pt-2"><LineChart pts={hist.map((h) => ({ label: new Date(h.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" }), y: h.value }))} height={130} format={inr} color={up ? "rgb(var(--good))" : "rgb(var(--bad))"} /></div>}
    </Card>
  );
}

export function Heatmap() {
  const { data } = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview[]>("/overview") });
  if (!data) return <Skeleton className="h-44" />;
  const rows = data.filter((r) => r.in_portfolio);
  const tint = (c: number | null) => {
    if (c == null) return "rgb(var(--track))";
    const a = Math.min(1, Math.abs(c) / 3);
    return c >= 0 ? `rgb(var(--good) / ${0.12 + a * 0.5})` : `rgb(var(--bad) / ${0.12 + a * 0.5})`;
  };
  return (
    <Card className="!p-3">
      <div className="mb-2 flex items-center justify-between px-1"><p className="text-sm font-semibold">Market today</p><p className="text-[11px] text-muted">Day change by stock</p></div>
      <div className="grid grid-cols-4 gap-1.5">
        {rows.map((r, i) => (
          <Link key={r.ticker} href={`/stock/${r.ticker}`} title={`${r.name}: ${pct(r.day_change)}`} style={{ background: tint(r.day_change), animationDelay: `${i * 18}ms` }}
            className="pop press rounded-lg p-1.5 text-center transition-transform hover:scale-[1.06] hover:shadow-md">
            <p className="truncate font-mono text-[10px] font-medium">{r.ticker}</p>
            <p className={`font-mono text-[11px] font-semibold ${tone(r.day_change)}`}>{r.day_change == null ? "–" : `${r.day_change > 0 ? "+" : ""}${r.day_change.toFixed(1)}%`}</p>
          </Link>
        ))}
      </div>
    </Card>
  );
}

export function Movers() {
  const { data: pf } = useQuery({ queryKey: ["portfolio"], queryFn: () => get<Portfolio>("/portfolio") });
  const { data: ov } = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview[]>("/overview") });
  if (!pf) return <Skeleton className="h-60" />;
  const top = [...pf.positions].sort((a, b) => Math.abs(b.day_impact) - Math.abs(a.day_impact)).slice(0, 6);
  const max = Math.max(...top.map((p) => Math.abs(p.day_impact)), 1);
  return (
    <Card className="!p-4">
      <p className="mb-3 text-sm font-semibold">Biggest movers by impact</p>
      <ul className="space-y-2.5">
        {top.map((p, i) => {
          const w = (Math.abs(p.day_impact) / max) * 100, up = p.day_impact >= 0;
          const sp = ov?.find((o) => o.ticker === p.ticker)?.spark;
          return (
            <li key={p.ticker} className="reveal" style={{ animationDelay: `${i * 50}ms` }}>
              <Link href={`/stock/${p.ticker}`} className="group flex items-center gap-3">
                <div className="w-20"><p className="font-mono text-xs font-medium group-hover:text-accent">{p.ticker}</p><p className={`font-mono text-[11px] ${tone(p.day_change_pct)}`}>{pct(p.day_change_pct)}</p></div>
                <div className="relative h-5 flex-1 rounded bg-page"><div className={`grow-x absolute inset-y-0 left-0 rounded ${up ? "bg-good/70" : "bg-bad/70"}`} style={{ width: `${w}%` }} /></div>
                <div className="w-20 text-right"><p className={`font-mono text-xs ${tone(p.day_impact)}`}>{inr(p.day_impact)}</p></div>
                {sp && <Spark values={sp} w={46} h={20} className="hidden sm:block" />}
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
