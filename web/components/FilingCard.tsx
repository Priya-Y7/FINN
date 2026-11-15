"use client";
import Link from "next/link";
import { Item, cat, pct, tone } from "@/lib/api";
import InfoPop from "./InfoPop";
import ResultsCard from "./ResultsCard";

const TIER = { 1: ["Act now", "text-bad", "bg-bad"], 2: ["Worth knowing", "text-caution", "bg-caution"], 3: ["Routine", "text-neutral", "bg-neutral"] } as const;
const ICON: Record<string, string> = { results: "📊", management_change: "👤", "m&a": "🤝", fund_raise: "💰", litigation: "⚖️", credit_rating: "🏷️", dividend: "💵", capex: "🏗️", press_release: "📣", insider_trading: "🕵️", pledging: "🔒", earnings_call: "🎙️", bonus_split: "✂️" };
const STARTERS: Record<string, string[]> = {
  results: ["What drove the margin change?", "Did this match what management guided?"],
  management_change: ["Who held this role before?"],
};
export function starters(c: string) { return STARTERS[c] ?? ["What does this filing change for the company?"]; }

function ScoreBar({ b, score }: { b: NonNullable<Item["breakdown"]>; score: number }) {
  const parts = [["Base", b.base, "rgb(var(--accentline))"], ["Severity", b.severity, "rgb(var(--caution))"], ["Market", b.market, "rgb(var(--bad))"], ["Position", b.position, "#2F8F83"]] as const;
  const total = parts.reduce((s, p) => s + p[1], 0) || 1;
  return (
    <div className="mt-3" title={`Score ${score}`}>
      <div className="flex h-1.5 overflow-hidden rounded-full bg-page">
        {parts.map(([l, v, c]) => v > 0 && <span key={l} className="grow-x" style={{ width: `${(v / total) * 100}%`, background: c }} title={`${l} ${v}`} />)}
      </div>
      <p className="mt-1 flex justify-between text-[10px] text-muted"><span>Priority {score}</span><span>{parts.filter((p) => p[1] > 0).map((p) => `${p[0]} ${p[1]}`).join(" · ")}</span></p>
    </div>
  );
}

export default function FilingCard({ it, compact = false, delay = 0 }: { it: Item; compact?: boolean; delay?: number }) {
  const b = it.breakdown;
  const link = it.pdf_url ?? it.alt_links[0]?.url ?? null;
  const [tierName, tierTone, tierBg] = TIER[it.tier as 1 | 2 | 3];
  return (
    <article style={{ animationDelay: `${delay}ms` }} className="reveal lift relative overflow-hidden rounded-card border border-line bg-card p-4 pl-5">
      <span className={`absolute bottom-0 left-0 top-0 w-1 ${tierBg}`} aria-hidden />
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-page text-base" aria-hidden>{ICON[it.category] ?? "📄"}</span>
          <div>
            <Link href={`/stock/${it.ticker}`} className="font-mono text-sm font-medium text-accent hover:underline">{it.ticker}</Link>
            <span className="ml-2 text-xs text-muted">{it.name}</span>
            <p className="text-[11px] text-muted">{cat(it.category)} · {new Date(it.ts).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</p>
          </div>
        </div>
        <div className="text-right">
          <span className={`text-[11px] font-semibold ${tierTone}`}>● {tierName}</span>
          {it.day_change != null && <p className={`font-mono text-xs ${tone(it.day_change)}`}>{pct(it.day_change)}</p>}
        </div>
      </div>
      {it.card?.headline && <p className="mt-3 text-[15px] font-semibold">{it.card.headline}</p>}
      {it.card?.kind === "results" ? <ResultsCard card={it.card} link={link} /> : <p className="mt-3 text-sm leading-snug">{it.card?.line || it.title}</p>}
      {it.card?.flag && <p className="mt-2 inline-block rounded-md bg-cautionbg px-2 py-1 text-xs text-caution">⚑ {it.card.flag}</p>}
      {it.card?.synthetic && it.card.kind !== "results" && <p className="mt-1 text-[11px] text-caution">● Synthetic details (sample data)</p>}
      {b && <div className="flex items-end gap-1"><div className="flex-1"><ScoreBar b={b} score={it.score} /></div><InfoPop title="Priority score" formula={b.formula} lines={[`Score ${it.score} = base ${b.base} + severity ${b.severity}${b.severity_reason ? ` (${b.severity_reason})` : ""} + market reaction ${b.market}${b.market_reason ? ` (${b.market_reason})` : ""} + position ${b.position}`]} /></div>}
      {!compact && (
        <div className="mt-3 flex items-center justify-between border-t border-line pt-3 text-xs">
          {link ? <a className="font-medium text-accent hover:underline" href={link} target="_blank" rel="noreferrer">View filing ↗</a> : <span />}
          <Link className="press rounded-lg bg-accent px-3 py-1.5 font-medium text-white transition-opacity hover:opacity-90" href={`/ask?ticker=${it.ticker}&filing=${it.id}`}>Ask about this →</Link>
        </div>
      )}
    </article>
  );
}
