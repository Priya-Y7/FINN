"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get, send, pct, tone, AlertItem } from "@/lib/api";
import { Chipbtn, Empty, Skeleton, useToast } from "@/components/ui";

const KIND: Record<string, [string, string]> = { price: ["Price move", "📈"], volume: ["Volume spike", "📊"], announcement: ["Filing", "📄"], confirmed: ["Confirmed move", "🎯"] };

export default function Alerts() {
  const qc = useQueryClient();
  const toast = useToast();
  const [kind, setKind] = useState<string | null>(null);
  const [leaving, setLeaving] = useState<number[]>([]);
  const { data, isLoading } = useQuery({ queryKey: ["alerts"], queryFn: () => get<{ unread: number; items: AlertItem[] }>("/alerts"), refetchInterval: 60_000 });
  // P-35 (stretch): browser notification when new alerts arrive while the app is open and permission was granted.
  const prev = useRef<number | null>(null);
  const [perm, setPerm] = useState<string>("unsupported");
  useEffect(() => { if (typeof Notification !== "undefined") setPerm(Notification.permission); }, []);
  useEffect(() => {
    if (data && prev.current !== null && data.unread > prev.current && perm === "granted") new Notification("finn", { body: `${data.unread - prev.current} new alert(s)` });
    if (data) prev.current = data.unread;
  }, [data?.unread]);

  const seen = async (id: number) => { await send("POST", `/alerts/${id}/seen`); qc.invalidateQueries({ queryKey: ["alerts"] }); };
  const dismiss = async (id: number) => {
    setLeaving((l) => [...l, id]);
    setTimeout(async () => { await send("POST", `/alerts/${id}/dismiss`); setLeaving((l) => l.filter((x) => x !== id)); qc.invalidateQueries({ queryKey: ["alerts"] }); }, 280);
  };
  const markAll = async () => { const ids = (data?.items ?? []).filter((a) => a.status === "new").map((a) => a.id); await Promise.all(ids.map((i) => send("POST", `/alerts/${i}/seen`))); qc.invalidateQueries({ queryKey: ["alerts"] }); toast(`Marked ${ids.length} as read`); };

  const items = (data?.items ?? []).filter((a) => !kind || a.kind_label === kind);
  const groups = items.reduce<Record<string, AlertItem[]>>((g, a) => ((g[a.date] ||= []).push(a), g), {});
  const kinds = Array.from(new Set((data?.items ?? []).map((a) => a.kind_label)));
  const dayLabel = (d: string) => { const t = new Date().toISOString().slice(0, 10); return d === t ? "Today" : new Date(d).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }); };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-end justify-between">
        <div><h1 className="text-xl font-semibold">Alerts</h1><p className="text-xs text-muted">{data?.unread ?? 0} unread · thresholds are yours to set</p></div>
        <div className="flex items-center gap-3 text-xs">
          {perm === "default" && <button onClick={async () => setPerm(await Notification.requestPermission())} className="text-accent ">Enable notifications</button>}
          {!!data?.unread && <button onClick={markAll} className="text-accent ">Mark all read</button>}
          <Link href="/alerts/rules" className="press rounded-lg bg-accent px-3 py-1.5 font-medium text-white">⚙ Rules</Link>
        </div>
      </div>
      {kinds.length > 1 && <div className="flex gap-2 overflow-x-auto scroll-hide"><Chipbtn on={!kind} onClick={() => setKind(null)}>All</Chipbtn>{kinds.map((k) => <Chipbtn key={k} on={kind === k} onClick={() => setKind(k)}>{KIND[k]?.[0] ?? k}</Chipbtn>)}</div>}
      {isLoading && <div className="space-y-2"><Skeleton className="h-20" /><Skeleton className="h-20" /></div>}
      {data && !items.length && <Empty icon="🔕" title="No alerts" body="Nothing has crossed your thresholds. Adjust them under Rules." />}
      {Object.entries(groups).map(([date, list]) => (
        <section key={date}>
          <p className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-muted">{dayLabel(date)}</p>
          <div className="space-y-2">
            {list.map((a, n) => (
              <article key={a.id} onClick={() => a.status === "new" && seen(a.id)} style={{ animationDelay: `${Math.min(n, 8) * 40}ms`, ...(leaving.includes(a.id) ? { animation: "slideOut .28s ease forwards" } : {}) }}
                className="reveal lift relative cursor-pointer overflow-hidden rounded-card border border-line bg-card p-3.5 pl-4">
                {a.status === "new" && <span className="dot-pulse absolute left-1.5 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-accent" aria-label="unread" />}
                <div className="flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-page text-base" aria-hidden>{KIND[a.kind_label]?.[1] ?? "🔔"}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p><Link href={`/stock/${a.ticker}`} onClick={(e) => e.stopPropagation()} className="font-mono text-sm font-medium text-accent hover:underline">{a.ticker}</Link><span className="ml-2 text-xs text-muted">{a.name}</span></p>
                      {a.day_change != null && <span className={`font-mono text-xs ${tone(a.day_change)}`}>{pct(a.day_change)}</span>}
                    </div>
                    <p className="mt-0.5 text-sm leading-snug">{a.detail.text}</p>
                    <p className="mt-1 flex items-center justify-between text-[11px] text-muted"><span>{KIND[a.kind_label]?.[0] ?? a.kind_label}</span>
                      <button onClick={(e) => { e.stopPropagation(); dismiss(a.id); }} className="rounded-md px-2 py-0.5 text-accent hover:bg-page">Dismiss ✕</button></p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
