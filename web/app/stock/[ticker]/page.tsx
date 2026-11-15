"use client";
import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { get, price, pct, tone, Item } from "@/lib/api";
import { Card, Segmented, Skeleton } from "@/components/ui";
import { LineChart } from "@/components/viz";
import FilingCard from "@/components/FilingCard";

type Row = { date: string; close: number; volume: number; ret_pct: number | null; z_ret: number | null; vol_ratio: number | null };
const RANGES = [{ value: "30", label: "1M" }, { value: "90", label: "3M" }, { value: "250", label: "1Y" }];

export default function Stock() {
  const { ticker } = useParams<{ ticker: string }>();
  const [range, setRange] = useState("30");
  const { data: rows } = useQuery({ queryKey: ["px", ticker, range], queryFn: () => get<Row[]>(`/stocks/${ticker}/prices?days=${range}`) });
  const { data: ov } = useQuery({ queryKey: ["overview"], queryFn: () => get<{ ticker: string; name: string; sector: string; in_portfolio: number }[]>("/overview") });
  const { data: anns } = useQuery({ queryKey: ["stock-ann", ticker], queryFn: () => get<Omit<Item, "name" | "day_change" | "card" | "breakdown" | "alt_links">[]>(`/announcements?ticker=${ticker}&days=30`) });
  if (!rows) return <div className="space-y-3"><Skeleton className="h-10" /><Skeleton className="h-72" /></div>;
  const me = ov?.find((o) => o.ticker === ticker);
  const last = rows[rows.length - 1], first = rows[0];
  const flagged = (r: Row) => (r.z_ret != null && Math.abs(r.z_ret) >= 2.5) || (r.vol_ratio != null && r.vol_ratio >= 2);
  const change = (last.close / first.close - 1) * 100;
  const hi = Math.max(...rows.map((r) => r.close)), lo = Math.min(...rows.map((r) => r.close));
  const stat = (l: string, v: string, t = "") => <div className="rounded-xl bg-page p-3"><p className="text-[11px] text-muted">{l}</p><p className={`font-mono text-sm font-medium ${t}`}>{v}</p></div>;
  return (
    <div className="space-y-4">
      <Link href="/portfolio" className="text-xs text-accent ">← Portfolio</Link>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><p className="text-xs text-muted">{me?.name ?? ""}{me?.sector ? ` · ${me.sector}` : ""}</p>
          <h1 className="font-mono text-2xl font-medium">{ticker}</h1>
          <p className="font-mono text-3xl">₹{price(last.close)} <span className={`text-base ${tone(last.ret_pct)}`}>{pct(last.ret_pct)}</span></p></div>
        <div className="flex items-center gap-3"><Segmented value={range} onChange={setRange} options={RANGES} className="w-44" />
          <Link href={`/ask?ticker=${ticker}`} className="press rounded-lg bg-accent px-3 py-2 text-xs font-medium text-white">Research →</Link></div>
      </div>
      <Card className="!p-3">
        <LineChart showVolume height={260} format={(n) => `₹${price(n)}`} color={change >= 0 ? "rgb(var(--good))" : "rgb(var(--bad))"}
          pts={rows.map((r) => ({ label: new Date(r.date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: range === "250" ? "2-digit" : undefined }), y: r.close, v: r.volume, flag: flagged(r),
            note: flagged(r) ? `Alert day: ${r.z_ret != null && Math.abs(r.z_ret) >= 2.5 ? `|z| ${Math.abs(r.z_ret).toFixed(1)}` : ""} ${r.vol_ratio != null && r.vol_ratio >= 2 ? `vol ${r.vol_ratio.toFixed(1)}x` : ""}` : undefined }))} />
        <p className="mt-1 text-[11px] text-muted">● Amber dots mark days an alert would fire (|z| ≥ 2.5 or volume ≥ 2x). Hover or drag across the chart.</p>
      </Card>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stat("Period change", pct(change), tone(change))}{stat("Period high", `₹${price(hi)}`)}{stat("Period low", `₹${price(lo)}`)}
        {stat("Latest z-score", last.z_ret == null ? "–" : last.z_ret.toFixed(2), last.z_ret != null && Math.abs(last.z_ret) >= 2.5 ? "text-caution" : "")}
      </div>
      <p className="px-1 text-xs font-semibold text-muted">Filings, last 30 days</p>
      <div className="grid gap-3 lg:grid-cols-2">
        {anns?.length ? anns.map((a, i) => <FilingCard key={a.id} compact delay={i * 50} it={{ ...a, name: "", day_change: null, card: null, breakdown: null, alt_links: [] }} />) : <p className="text-sm text-muted">No filings in this period.</p>}
      </div>
    </div>
  );
}
