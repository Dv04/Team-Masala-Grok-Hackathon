import type { Metadata } from "next";
import "./globals.css";
import { ToastProvider } from "@/components/ui/toast";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "GrokBot Hackathon Starter",
  description:
    "Reusable AI agent hackathon starter with mock workflows and modular ownership boundaries.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-zinc-950 text-zinc-100">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
