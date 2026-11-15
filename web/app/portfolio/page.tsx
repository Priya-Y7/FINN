"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { get, inr, price, pct, tone, Portfolio, Overview } from "@/lib/api";
import { Card, Empty, Num, Segmented, Skeleton } from "@/components/ui";
import { Donut, SECTOR_COLORS, Spark } from "@/components/viz";

type Sort = "value" | "impact" | "change" | "drift";

export default function PortfolioTab() {
  const { data, isLoading } = useQuery({ queryKey: ["portfolio"], queryFn: () => get<Portfolio>("/portfolio") });
  const { data: ov } = useQuery({ queryKey: ["overview"], queryFn: () => get<Overview[]>("/overview") });
  const [sort, setSort] = useState<Sort>("value");
  const [active, setActive] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const sectors = useMemo(() => {
    const m = new Map<string, number>();
    data?.positions.forEach((p) => m.set(p.sector, (m.get(p.sector) ?? 0) + p.weight));
    return Array.from(m, ([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value).map((s, i) => ({ ...s, color: SECTOR_COLORS[i % SECTOR_COLORS.length] }));
  }, [data]);

  if (isLoading) return <div className="space-y-3"><Skeleton className="h-64" /><Skeleton className="h-40" /></div>;
  if (!data?.positions.length) return <Empty title="No holdings" body="Holdings are computed once prices are loaded." />;
  const rows = [...data.positions].filter((p) => !active || p.sector === active).sort((a, b) =>
    sort === "value" ? b.value - a.value : sort === "impact" ? b.day_impact - a.day_impact : sort === "change" ? (b.day_change_pct ?? 0) - (a.day_change_pct ?? 0) : Math.abs(b.weight - b.target_weight) - Math.abs(a.weight - a.target_weight));
  const maxW = Math.max(...data.positions.map((p) => Math.max(p.weight, p.target_weight)));
  const gainers = data.positions.filter((p) => p.day_impact > 0).length;
  return (
    <div className="space-y-5">
      <div><h1 className="text-xl font-semibold">Portfolio</h1><p className="text-xs text-muted">Mock portfolio: ₹10 Cr split by fixed weights on the start date. Weights drift as prices move.</p></div>
      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <Card className="flex flex-col items-center gap-3">
          <Donut slices={sectors} size={200} centerTop={active ? `${sectors.find((s) => s.label === active)?.value.toFixed(1)}%` : String(data.positions.length)} centerBottom={active ?? "stocks"} active={active} onActive={setActive} />
          <ul className="grid w-full grid-cols-2 gap-x-4 gap-y-1 text-xs">
            {sectors.map((s) => (
              <li key={s.label}><button onMouseEnter={() => setActive(s.label)} onMouseLeave={() => setActive(null)} onClick={() => setActive(active === s.label ? null : s.label)} className={`flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-page ${active && active !== s.label ? "opacity-40" : ""}`}>
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} /><span className="flex-1 truncate">{s.label}</span><span className="font-mono text-muted">{s.value.toFixed(1)}%</span></button></li>
            ))}
          </ul>
        </Card>
        <div className="grid content-start gap-3 sm:grid-cols-3">
          <Card><p className="text-xs text-muted">Total value</p><p className="font-mono text-xl font-medium"><Num value={data.total_value} format={inr} /></p></Card>
          <Card><p className="text-xs text-muted">Today</p><p className={`font-mono text-xl font-medium ${tone(data.day_impact)}`}>{pct(data.day_impact_pct)}</p><p className={`font-mono text-xs ${tone(data.day_impact)}`}>{inr(data.day_impact)}</p></Card>
          <Card><p className="text-xs text-muted">Breadth</p><p className="font-mono text-xl font-medium">{gainers}<span className="text-sm text-muted"> / {data.positions.length} up</span></p><div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-badbg"><span className="grow-x bg-good" style={{ width: `${(gainers / data.positions.length) * 100}%` }} /></div></Card>
          <Card className="sm:col-span-3 !p-3"><p className="mb-2 px-1 text-xs font-semibold">Weights: actual vs target</p>
            <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
              {data.positions.slice(0, 10).map((p) => (
                <div key={p.ticker} className="flex items-center gap-2 text-[11px]"><span className="w-20 truncate font-mono">{p.ticker}</span>
                  <div className="relative h-2 flex-1 rounded bg-page"><div className="grow-x absolute inset-y-0 left-0 rounded bg-accent" style={{ width: `${(p.weight / maxW) * 100}%` }} /><span className="absolute -top-0.5 h-3 w-0.5 bg-ink" style={{ left: `${(p.target_weight / maxW) * 100}%` }} title={`Target ${p.target_weight}%`} /></div>
                  <span className="w-12 text-right font-mono text-muted">{p.weight.toFixed(1)}%</span></div>
              ))}
            </div></Card>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">Holdings{active ? ` · ${active}` : ""}</p>
        <Segmented<Sort> className="w-full sm:w-96" value={sort} onChange={setSort} options={[{ value: "value", label: "Value" }, { value: "impact", label: "Impact" }, { value: "change", label: "Change" }, { value: "drift", label: "Drift" }]} />
      </div>
      <div className="grid gap-2 lg:grid-cols-2">
        {rows.map((p, i) => {
          const sp = ov?.find((o) => o.ticker === p.ticker)?.spark, isOpen = open === p.ticker;
          return (
            <article key={p.ticker} style={{ animationDelay: `${Math.min(i, 10) * 30}ms` }} className="reveal lift rounded-card border border-line bg-card p-3">
              <button className="flex w-full items-center gap-3 text-left" onClick={() => setOpen(isOpen ? null : p.ticker)} aria-expanded={isOpen}>
                <div className="min-w-0 flex-1"><p className="font-mono text-sm font-medium">{p.ticker}</p><p className="truncate text-xs text-muted">{p.name} · {p.sector}</p></div>
                {sp && <Spark values={sp} w={64} h={26} />}
                <div className="w-24 text-right"><p className="font-mono text-sm">₹{price(p.price)}</p><p className={`font-mono text-xs ${tone(p.day_change_pct)}`}>{pct(p.day_change_pct)}</p></div>
              </button>
              {isOpen && (
                <div className="fade-in mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3 text-xs sm:grid-cols-4">
                  <div><p className="text-muted">Value</p><p className="font-mono">{inr(p.value)}</p></div>
                  <div><p className="text-muted">Weight</p><p className="font-mono">{p.weight.toFixed(2)}% <span className="text-muted">/ {p.target_weight}%</span></p></div>
                  <div><p className="text-muted">Day impact</p><p className={`font-mono ${tone(p.day_impact)}`}>{inr(p.day_impact)}</p></div>
                  <div><p className="text-muted">Since start</p><p className={`font-mono ${tone(p.since_start_pct)}`}>{pct(p.since_start_pct)}</p></div>
                  <Link href={`/stock/${p.ticker}`} className="col-span-2 text-accent sm:col-span-2">Price chart & filings →</Link>
                  <Link href={`/ask?ticker=${p.ticker}`} className="col-span-2 text-accent sm:col-span-2">Research this company →</Link>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
