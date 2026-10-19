"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

interface ToastItem {
  id: string;
  message: string;
  tone: "success" | "error";
}

const ToastContext = createContext<{
  push: (message: string, tone?: ToastItem["tone"]) => void;
} | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((message: string, tone: ToastItem["tone"] = "success") => {
    const id = `${Date.now()}-${Math.random()}`;
    setItems((previous) => [...previous, { id, message, tone }]);
    setTimeout(() => {
      setItems((previous) => previous.filter((item) => item.id !== id));
    }, 2500);
  }, []);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-72 flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={`rounded-lg border px-3 py-2 text-sm ${
              item.tone === "success"
                ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-100"
                : "border-rose-500/30 bg-rose-500/15 text-rose-100"
            }`}
          >
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}
