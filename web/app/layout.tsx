import "./globals.css";
import type { Metadata, Viewport } from "next";
import Providers from "@/components/Providers";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = { title: "finn", description: "Only what matters.", manifest: "/manifest.json", icons: { icon: "/icon.svg" } };
export const viewport: Viewport = { themeColor: "#F7F7F5", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* apply the saved theme before first paint so dark mode never flashes light */}
        <script dangerouslySetInnerHTML={{ __html: `try{var p=JSON.parse(localStorage.getItem("finn_prefs")||"{}");if(p.theme==="dark"||(p.theme==="system"&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark");if(p.fontPct&&p.fontPct!==100)document.documentElement.style.fontSize=(16*p.fontPct/100)+"px"}catch(e){}` }} />
      </head>
      <body>
        <Providers><AppShell>{children}</AppShell></Providers>
      </body>
    </html>
  );
}
