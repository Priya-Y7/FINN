"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get, send, Meta } from "@/lib/api";
import { useToast } from "./ui";
import DataBanner from "./DataBanner";
import MenuDrawer from "./MenuDrawer";
import { usePrefs } from "./Prefs";

const I = (d: string) => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>;
const TABS = [
  { href: "/", label: "Today", icon: I("M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10") },
  { href: "/alerts", label: "Alerts", icon: I("M6 8a6 6 0 0112 0c0 7 3 8 3 8H3s3-1 3-8M10 20a2 2 0 004 0") },
  { href: "/ask", label: "Ask", icon: I("M21 12a8 8 0 01-11.6 7.1L4 20l1-4.6A8 8 0 1121 12z") },
  { href: "/portfolio", label: "Portfolio", icon: I("M21 12A9 9 0 1112 3v9h9z") },
];

export function Wordmark({ big = false }: { big?: boolean }) {
  return (
    <div className={big ? "flex flex-col" : "flex items-baseline gap-2"}>
      <span className={`${big ? "text-[28px] leading-none" : "text-[22px]"} font-semibold tracking-tight`}>finn<span className="text-accent">.</span></span>
      <span className={big ? "mt-1 text-[11px] text-muted" : "hidden text-xs text-muted sm:inline"}>Only what matters.</span>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: alerts } = useQuery({ queryKey: ["alerts"], queryFn: () => get<{ unread: number }>("/alerts"), refetchInterval: 60_000 });
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: () => get<Meta>("/meta") });
  const unread = alerts?.unread ?? 0;
  const { openMenu, prefs } = usePrefs();
  const [collapsed, setCollapsed] = useState(false);       // desktop sidebar: full (236px) or icons only (72px)
  useEffect(() => { try { setCollapsed(localStorage.getItem("finn_side") === "1"); } catch {} }, []);
  const toggle = () => setCollapsed((c) => { try { localStorage.setItem("finn_side", c ? "0" : "1"); } catch {} return !c; });
  const refresh = async () => {
    try { const r = await send<{ started: boolean; reason?: string }>("POST", "/refresh"); toast(r.started ? "Refreshing data in the background…" : r.reason ?? "Already refreshing"); [4000, 12000, 25000].forEach((t) => setTimeout(() => qc.invalidateQueries(), t)); }
    catch { toast("Could not reach the server"); }
  };
  const on = (h: string) => (h === "/" ? path === "/" : path.startsWith(h));
  const mode = meta?.data_mode ?? "empty";
  const dot = mode === "live" ? "bg-good" : mode === "empty" ? "bg-neutral" : "bg-caution";
  return (
    <div className="min-h-screen transition-[grid-template-columns] duration-300 lg:grid lg:grid-cols-[var(--side)_1fr]" style={{ "--side": collapsed ? "72px" : "236px" } as React.CSSProperties}>
      <aside className={`sticky top-0 hidden h-screen flex-col overflow-hidden border-r border-line bg-card transition-[padding] duration-300 lg:flex ${collapsed ? "p-3" : "p-5"}`}>
        <div className={`flex items-center ${collapsed ? "flex-col gap-3" : "justify-between"}`}>
          {collapsed ? <span className="text-[22px] font-semibold tracking-tight">f<span className="text-accent">.</span></span> : <Wordmark big />}
          <button onClick={toggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="press flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-page hover:text-ink">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" />{collapsed ? <path d="M14 10l2 2-2 2" /> : <path d="M16 10l-2 2 2 2" />}</svg>
          </button>
        </div>
        <nav className="mt-8 space-y-1">
          {TABS.map((t) => (
            <Link key={t.href} href={t.href} aria-current={on(t.href) ? "page" : undefined} title={collapsed ? t.label : undefined}
              className={`press relative flex items-center rounded-xl py-2.5 text-sm transition-colors ${collapsed ? "justify-center px-0" : "gap-3 px-3"} ${on(t.href) ? "bg-accent font-medium text-white" : "text-muted hover:bg-page hover:text-ink"}`}>
              {t.icon}{!collapsed && <span>{t.label}</span>}
              {t.label === "Alerts" && unread > 0 && (collapsed
                ? <span className="absolute right-1.5 top-1 rounded-full bg-accent px-1 text-[9px] font-semibold text-white ring-2 ring-card">{unread > 99 ? "99+" : unread}</span>
                : <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold ${on(t.href) ? "bg-white text-accent" : "bg-accent text-white"}`}>{unread > 99 ? "99+" : unread}</span>)}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          <button onClick={openMenu} title={collapsed ? "Menu and settings" : undefined} aria-label="Menu and settings"
            className={`press flex w-full items-center rounded-xl py-2.5 text-sm text-muted transition-colors hover:bg-page hover:text-ink ${collapsed ? "justify-center px-0" : "gap-3 px-3"}`}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" /></svg>
            {!collapsed && <span>Settings</span>}
          </button>
          {collapsed ? (
            <div className="flex flex-col items-center gap-2">
              <span title={mode === "live" ? "Live data" : mode === "snapshot" ? "Saved snapshot" : mode === "sample" ? "Sample data" : "No data yet"} className={`h-2.5 w-2.5 rounded-full ${dot} ${mode === "live" ? "dot-pulse" : ""}`} />
              <button onClick={refresh} aria-label="Refresh data" title="Refresh now" className="press flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-card text-accent hover:border-accent">↻</button>
            </div>
          ) : (
            <>
          <div className="rounded-xl border border-line bg-page p-3 text-xs">
            <p className="flex items-center gap-2 font-medium"><span className={`h-2 w-2 rounded-full ${dot} ${mode === "live" ? "dot-pulse" : ""}`} />{mode === "live" ? "Live data" : mode === "snapshot" ? "Saved snapshot" : mode === "sample" ? "Sample data" : "No data yet"}</p>
            {meta?.prices_refreshed_at && <p className="mt-1 text-muted">Last refreshed {new Date(meta.prices_refreshed_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</p>}
            <button onClick={refresh} className="press mt-2 w-full rounded-lg border border-line bg-card py-1.5 font-medium text-accent hover:border-accent">↻ Refresh now</button>
          </div>
          <p className="px-1 text-[11px] leading-snug text-muted">Primary sources only: exchange filings, annual reports, concall transcripts.</p>
            </>
          )}
        </div>
      </aside>
      <div className="min-w-0">
        <header className="flex items-center justify-between px-4 pb-2 pt-5 lg:hidden">
          <div className="flex items-center gap-3">
            <button onClick={openMenu} aria-label="Open menu" className="press flex h-8 w-8 items-center justify-center rounded-full bg-accent text-xs font-semibold text-white">{(prefs.name.trim()[0] || "G").toUpperCase()}</button>
            <Wordmark />
          </div>
          <div className="flex items-center gap-2">
            <button onClick={refresh} aria-label="Refresh data" className="press rounded-full border border-line bg-card px-3 py-1 text-xs text-accent">↻ Refresh</button>
          </div>
        </header>
        <div className="mx-auto w-full max-w-[430px] pb-24 lg:max-w-[1080px] lg:px-8 lg:pb-12 lg:pt-8">
          <div className="px-4 lg:px-0"><DataBanner /></div>
          <main className="px-4 lg:px-0">{children}</main>
        </div>
      </div>
      <MenuDrawer dataLabel={mode === "live" ? "Live data" : mode === "snapshot" ? "Saved snapshot" : mode === "sample" ? "Sample data" : "No data yet"}
        updated={meta?.prices_refreshed_at ? new Date(meta.prices_refreshed_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : undefined} onRefresh={refresh} />
      <nav className="fixed bottom-0 left-0 right-0 z-20 border-t border-line bg-card/95 backdrop-blur lg:hidden" aria-label="Main">
        <ul className="mx-auto grid max-w-[430px] grid-cols-4">
          {TABS.map((t) => (
            <li key={t.href}>
              <Link href={t.href} aria-current={on(t.href) ? "page" : undefined} className={`press relative flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] ${on(t.href) ? "font-semibold text-accent" : "text-muted"}`}>
                {on(t.href) && <span className="absolute top-0 h-0.5 w-8 rounded-full bg-accent" />}
                {t.icon}{t.label}
                {t.label === "Alerts" && unread > 0 && <span className="absolute right-[26%] top-1.5 rounded-full bg-accent px-1.5 text-[9px] font-semibold text-white">{unread > 99 ? "99+" : unread}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
