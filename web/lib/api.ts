export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export type Meta = { data_mode: "live" | "snapshot" | "sample" | "empty"; prices_refreshed_at: string | null;
  announcements_refreshed_at: string | null; llm_mock: boolean; last_job: { name: string; status: string; error?: string } | null };
export type Position = { ticker: string; name: string; sector: string; size: string; weight: number; target_weight: number;
  price: number; value: number; day_impact: number; day_change_pct: number | null; since_start_pct: number; as_of: string };
export type Portfolio = { positions: Position[]; total_value: number; day_impact: number; day_impact_pct: number };
export type Announcement = { id: string; ticker: string; ts: string; source: string; title: string; category_text: string | null;
  pdf_url: string | null; is_sample: number };

// Indian digit grouping, crore/lakh.
export function inr(n: number): string {
  const a = Math.abs(n), s = n < 0 ? "-" : "";
  if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(2)} L`;
  return `${s}₹${a.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}
export const price = (n: number) => n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const pct = (n: number | null) => (n == null ? "–" : `${n > 0 ? "▲ +" : n < 0 ? "▼ " : ""}${n.toFixed(2)}%`);
export const tone = (n: number | null) => (n == null || n === 0 ? "text-neutral" : n > 0 ? "text-good" : "text-bad");

export type Card = {
  kind: string; needs_review?: boolean; problems?: string[]; synthetic?: boolean; bank?: boolean; sentence?: string;
  tiles?: { key: string; value: number | null; bars: (number | null)[]; qoq_pct: number | null; yoy_pct: number | null;
    qoq: { abs: number | null; kind: string | null }; yoy: { abs: number | null; kind: string | null } }[];
  margin?: number | null; margin_change_bps_yoy?: number | null;
  line?: string; headline?: string; flag?: string | null; data?: Record<string, unknown>;
};
export type Breakdown = { base: number; severity: number; severity_reason: string; market: number; market_reason: string; position: number; formula: string };
export type Item = { id: string; ticker: string; name: string; sector: string; ts: string; source: string; title: string; category: string;
  tier: number; score: number; summary: string | null; pdf_url: string | null; day_change: number | null; is_sample: number;
  card: Card | null; breakdown: Breakdown | null; alt_links: { source: string; url: string }[] };
export type Digest = { from: string; to: string; notice: string | null; counts: Record<string, number>; summary: string; briefing: string;
  tiers: { act_now: Item[]; worth_knowing: Item[]; routine: Item[] } };
export type AlertItem = { id: number; ticker: string; name: string; date: string; kind: string; kind_label: string; status: string;
  day_change: number | null; detail: { text: string } };
export type Rule = { id: number; type: string; params: Record<string, any>; tickers: string[] | null; active: boolean };

export async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(API + path, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}
export const cat = (c: string) => c.replace(/_/g, " ").replace("m&a", "M&A").replace(/^./, (x) => x.toUpperCase());

export type Promise_ = { metric: string; metric_name: string; unit: string; call: string; horizon_label: string; kind: string; status: string;
  target_low: number | null; target_high: number | null; actual: number | null; achievement: number | null; gap_bps: number | null; quote: string;
  source_id: string; source_label: string; note: string; direction: string | null };
export type Research = { status?: string; ticker: string; name: string; sample: boolean; notes: string[];
  snapshot: { available: boolean; reason?: string; as_of?: string; tiles?: { key: string; label: string; value: number | null; unit: string; spark: (number | null)[]; formula: string }[];
    trajectory?: { years: string[]; revenue: (number | null)[]; pat: (number | null)[]; margin: (number | null)[] };
    callouts?: { kind: string; text: string }[]; health?: { working_capital_days: { year: string; days: number | null }[]; fcf: { year: string; value: number | null }[] } };
  promises: { available: boolean; reason?: string; promises?: Promise_[]; flags?: { kind: string; text: string; ids?: string[] }[];
    delivery?: { rate: number | null; based_on: number; delivered: number; partly: number; missed: number; not_due: number; cant_verify: number };
    verdict?: { lines: string[]; by_model: boolean }; calls_note?: string | null; chips?: string[]; dropped_unverified?: number };
  bull_bear: { available: boolean; reason?: string; bull?: { text: string; ids: string[] }[]; bear?: { text: string; ids: string[] }[]; sources?: Record<string, { label: string }>; by_model?: boolean; footer?: string } };
export type AskResult = { found: boolean; text: string; answer: { text: string; ids: string[] }[]; sources: Record<string, { label: string }>; cached: boolean; remaining: number; by_model?: boolean };

export type Overview = { ticker: string; name: string; sector: string; size: string; in_portfolio: number; weight: number; price: number; day_change: number | null; spark: number[] };
export type HistPt = { date: string; value: number };
