"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { get, Digest, Item } from "@/lib/api";
import { Chipbtn, Empty, Segmented, Skeleton } from "@/components/ui";
import FilingCard from "@/components/FilingCard";
import Briefing from "@/components/Briefing";
import { Heatmap, Movers, PortfolioHero } from "@/components/PortfolioWidgets";

const WINDOWS = [{ l: "24 hours", d: 1 }, { l: "3 days", d: 3 }, { l: "7 days", d: 7 }, { l: "30 days", d: 30 }];
type Tier = "act" | "worth" | "routine";

export default function Today() {
  const [days, setDays] = useState(1);
  const [custom, setCustom] = useState<{ from: string; to: string } | null>(null);
  const [showCustom, setShowCustom] = useState(false);
  const [tier, setTier] = useState<Tier | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const qs = custom ? `from=${custom.from}&to=${custom.to}` : `days=${days}`;
  const { data, isLoading } = useQuery({ queryKey: ["digest", qs], queryFn: () => get<Digest>(`/digest?${qs}`) });

  const lists: Record<Tier, Item[]> = { act: data?.tiers.act_now ?? [], worth: data?.tiers.worth_knowing ?? [], routine: data?.tiers.routine ?? [] };
  const active: Tier = tier ?? (lists.act.length ? "act" : lists.worth.length ? "worth" : "routine");
  const cats = Array.from(new Set(lists[active].map((i) => i.category))).filter(Boolean);
  const shown = lists[active].filter((i) => !category || i.category === category);

  return (
    <div className="lg:grid lg:grid-cols-[1fr_340px] lg:gap-6">
      <div className="min-w-0 space-y-4">
        <div className="lg:hidden space-y-4"><PortfolioHero /></div>
        {data && <Briefing text={data.briefing} />}
        <div className="flex items-center gap-2 overflow-x-auto scroll-hide">
          {WINDOWS.map((w) => <Chipbtn key={w.d} on={!custom && days === w.d} onClick={() => { setDays(w.d); setCustom(null); setShowCustom(false); }}>{w.l}</Chipbtn>)}
          <Chipbtn on={!!custom || showCustom} onClick={() => setShowCustom((s) => !s)}>Custom ▾</Chipbtn>
        </div>
        {showCustom && (
          <form className="pop flex flex-wrap items-end gap-3 rounded-card border border-line bg-card p-3 text-xs"
            onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); const a = f.get("a") as string, b = f.get("b") as string; if (a && b) { setCustom({ from: a, to: b }); setShowCustom(false); } }}>
            <label>From<input name="a" type="date" className="mt-1 block rounded-lg border border-line p-1.5" /></label>
            <label>To<input name="b" type="date" className="mt-1 block rounded-lg border border-line p-1.5" /></label>
            <button className="press rounded-lg bg-accent px-4 py-2 font-medium text-white">Apply</button>
          </form>
        )}
        {isLoading && <div className="space-y-3"><Skeleton className="h-14" /><Skeleton className="h-40" /><Skeleton className="h-40" /></div>}
        {data && (
          <>
            <div>
              <p className="mb-2 text-sm font-medium" aria-live="polite">{data.summary}</p>
              <Segmented<Tier> value={active} onChange={(t) => { setTier(t); setCategory(null); }}
                options={[{ value: "act", label: `Act now · ${lists.act.length}` }, { value: "worth", label: `Worth knowing · ${lists.worth.length}` }, { value: "routine", label: `Routine · ${lists.routine.length}` }]} />
            </div>
            {data.notice && <p className="rounded-lg border border-line bg-card px-3 py-2 text-xs text-caution">● {data.notice}</p>}
            {cats.length > 1 && <div className="flex gap-2 overflow-x-auto scroll-hide"><Chipbtn on={!category} onClick={() => setCategory(null)}>All</Chipbtn>{cats.map((c) => <Chipbtn key={c} on={category === c} onClick={() => setCategory(c)}>{c.replace(/_/g, " ")}</Chipbtn>)}</div>}
            {!shown.length && <Empty icon="✓" title={active === "act" ? "Nothing needs you right now" : "Nothing here"} body="No filings in this tier for the selected window. Try a longer window." />}
            {active === "routine"
              ? shown.length > 0 && <ul className="reveal divide-y divide-line rounded-card border border-line bg-card px-4">{shown.map((i) => <li key={i.id} className="flex items-center justify-between gap-3 py-2.5 text-xs"><span><span className="font-mono text-accent">{i.ticker}</span> · {i.title}</span>{i.pdf_url && <a className="shrink-0 text-accent " href={i.pdf_url} target="_blank" rel="noreferrer">filing</a>}</li>)}</ul>
              : <div className="grid gap-3 xl:grid-cols-1">{shown.map((i, n) => <FilingCard key={i.id} it={i} delay={Math.min(n, 8) * 60} />)}</div>}
          </>
        )}
      </div>
      <aside className="mt-6 space-y-4 lg:mt-0">
        <div className="hidden lg:block"><PortfolioHero /></div>
        <Heatmap />
        <Movers />
      </aside>
    </div>
  );
}
