"use client";
import { useQuery } from "@tanstack/react-query";
import { get, Meta } from "@/lib/api";

export default function DataBanner() {
  const { data, isError } = useQuery({ queryKey: ["meta"], queryFn: () => get<Meta>("/meta") });
  if (isError) return <Note>Can’t reach the FINN server. Start it with <code>python start.py</code>.</Note>;
  if (!data) return null;
  if (data.data_mode === "sample") return <Note>Sample data: synthetic prices and announcements, not real market data.</Note>;
  if (data.data_mode === "snapshot") return <Note>Live sources unreachable. Showing the last saved snapshot{data.prices_refreshed_at ? ` (${data.prices_refreshed_at.slice(0, 10)})` : ""}.</Note>;
  if (data.data_mode === "empty") return <Note>No data yet. Run <code>python -m finn.cli sample</code> or <code>refresh</code>.</Note>;
  return null;
}
function Note({ children }: { children: React.ReactNode }) {
  return <div role="status" className="fade-in mb-3 rounded-lg border border-line bg-card px-3 py-2 text-xs text-caution">● {children}</div>;
}
