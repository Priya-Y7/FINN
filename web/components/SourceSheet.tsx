"use client";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";

type Src = { label: string; document: string; page: number; section: string; text: string; url: string | null; sample: boolean };

export function Chip({ id, label, ticker, onOpen }: { id: string; label?: string; ticker: string; onOpen: (t: string, id: string) => void }) {
  return <button onClick={() => onOpen(ticker, id)} className="mr-1 inline-block rounded-md border border-line bg-page px-1.5 py-0.5 font-mono text-[11px] text-accent">{label ?? id}</button>;
}

export default function SourceSheet({ target, onClose }: { target: { ticker: string; id: string } | null; onClose: () => void }) {
  const [s, setS] = useState<Src | null>(null);
  useEffect(() => { setS(null); if (target) get<Src>(`/sources/${target.ticker}/${target.id}`).then(setS).catch(() => setS(null)); }, [target?.id]);
  if (!target) return null;
  return (
    <div className="fixed inset-0 z-30 bg-black/30" onClick={onClose}>
      <div role="dialog" aria-label="Source" onClick={(e) => e.stopPropagation()} className="absolute bottom-0 left-0 right-0 mx-auto max-h-[70vh] max-w-[430px] overflow-y-auto rounded-t-card bg-card p-4">
        {!s ? <p className="text-sm text-muted">Loading source…</p> : (<>
          <p className="font-mono text-xs text-accent">{s.label}</p>
          <p className="text-xs text-muted">{s.document} · page {s.page} · {s.section}</p>
          <p className="mt-3 whitespace-pre-line text-sm">{s.text}</p>
          {s.sample && <p className="mt-2 text-[11px] text-caution">● Synthetic passage (sample data)</p>}
          {s.url && <a href={s.url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-accent ">Open original PDF</a>}
        </>)}
        <button onClick={onClose} className="mt-3 block text-xs text-muted ">Close</button>
      </div>
    </div>
  );
}
