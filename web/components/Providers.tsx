"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ToastProvider } from "./ui";
import { PrefsProvider } from "./Prefs";
export default function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } }));
  return <QueryClientProvider client={qc}><PrefsProvider><ToastProvider>{children}</ToastProvider></PrefsProvider></QueryClientProvider>;
}
