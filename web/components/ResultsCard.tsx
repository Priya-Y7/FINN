import { Card, Item, inr, pct } from "@/lib/api";
const LABEL: Record<string, string> = { revenue: "Revenue", ebitda: "EBITDA", pbt: "PBT", pat: "PAT", nii: "Net interest income", ppop: "PPOP" };
const chip = (p: number | null, kind?: string | null) => {
  if (kind) return <span className="rounded bg-page px-1.5 py-0.5 text-[11px] text-ink">{kind}</span>;
  if (p == null) return <span className="rounded bg-page px-1.5 py-0.5 text-[11px] text-neutral">n.m.</span>;
  return <span className={`rounded bg-page px-1.5 py-0.5 font-mono text-[11px] ${p >= 0 ? "text-good" : "text-bad"}`}>{p >= 0 ? "▲" : "▼"} {Math.abs(p).toFixed(0)}%</span>;
};
function Bars({ v }: { v: (number | null)[] }) {
  const max = Math.max(...v.map((x) => Math.abs(x ?? 0)), 1);
  return <svg width="36" height="16" aria-hidden>{v.map((x, i) => <rect key={i} x={i * 13} y={16 - (Math.abs(x ?? 0) / max) * 16} width="9" height={(Math.abs(x ?? 0) / max) * 16} fill={i === 2 ? "rgb(var(--accentline))" : "rgb(var(--line2))"} />)}</svg>;
}
export default function ResultsCard({ card, link }: { card: Card; link?: string | null }) {
  if (card.needs_review)
    return <p className="mt-2 rounded-lg bg-page p-2 text-xs text-caution">● Needs review: numbers not shown. {link && <a className="text-accent " href={link} target="_blank" rel="noreferrer">Open filing</a>}</p>;
  return (
    <div className="mt-2">
      <div className="grid grid-cols-2 gap-2">
        {card.tiles!.map((t) => (
          <div key={t.key} className="rounded-lg border border-line p-2">
            <p className="text-[11px] text-muted">{LABEL[t.key]}</p>
            <p className="font-mono text-sm font-medium">{t.value == null ? "–" : inr(t.value * 1e7)}</p>
            <div className="mt-1 flex items-center justify-between gap-1">
              <span className="grid grid-cols-[auto_auto] items-center gap-x-1 gap-y-0.5 text-[10px] text-muted"><span>QoQ</span>{chip(t.qoq_pct, t.qoq.kind)}<span>YoY</span>{chip(t.yoy_pct, t.yoy.kind)}</span>
              <Bars v={t.bars} />
            </div>
          </div>
        ))}
      </div>
      {card.sentence && <p className="mt-2 text-sm">{card.sentence}</p>}
      {card.synthetic && <p className="mt-1 text-[11px] text-caution">● Synthetic figures (sample data)</p>}
    </div>
  );
}
