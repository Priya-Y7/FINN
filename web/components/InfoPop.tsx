"use client";
import { useState } from "react";
// P-09: tap or hover shows definition, formula and this item's own breakdown.
export default function InfoPop({ title, formula, lines }: { title: string; formula: string; lines: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button aria-label={`About ${title}`} onClick={() => setOpen((o) => !o)}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-neutral text-[10px] text-muted">i</button>
      {open && (
        <span role="tooltip" className="absolute right-0 top-5 z-20 block w-64 rounded-lg border border-line bg-card p-3 text-left text-xs shadow-md">
          <span className="block font-semibold text-ink">{title}</span>
          <span className="mt-1 block font-mono text-[11px] text-muted">{formula}</span>
          {lines.map((l, i) => <span key={i} className="mt-1 block text-ink">{l}</span>)}
        </span>
      )}
    </span>
  );
}
