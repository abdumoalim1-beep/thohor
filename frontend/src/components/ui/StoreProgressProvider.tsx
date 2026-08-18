"use client";

import { createContext, useContext } from "react";

import { StoreProgress, useStoreProgress } from "@/lib/useStoreProgress";

const StoreProgressContext = createContext<StoreProgress | null>(null);

export function StoreProgressProvider({ storeId, children }: { storeId: string; children: React.ReactNode }) {
  const progress = useStoreProgress(storeId);
  return <StoreProgressContext.Provider value={progress}>{children}</StoreProgressContext.Provider>;
}

export function useStoreProgressContext(): StoreProgress {
  const context = useContext(StoreProgressContext);
  if (!context) throw new Error("useStoreProgressContext must be used within a StoreProgressProvider");
  return context;
}
