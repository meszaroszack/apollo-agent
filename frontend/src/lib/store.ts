import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SessionConfig {
  sessionId: string;
  dryRun: boolean;
  sentimentEnabled: boolean;
  bankrollUsd: number;
}

interface ApolloStore {
  sessionId: string | null;
  sessionConfig: SessionConfig | null;
  halted: boolean;
  haltReason: string | null;
  setSession: (config: SessionConfig) => void;
  clearSession: () => void;
  setHalted: (reason: string) => void;
}

export const useApolloStore = create<ApolloStore>()(
  persist(
    (set) => ({
      sessionId: null,
      sessionConfig: null,
      halted: false,
      haltReason: null,
      setSession: (config) =>
        set({
          sessionId: config.sessionId,
          sessionConfig: config,
          halted: false,
          haltReason: null,
        }),
      clearSession: () =>
        set({ sessionId: null, sessionConfig: null, halted: false, haltReason: null }),
      setHalted: (reason) => set({ halted: true, haltReason: reason }),
    }),
    {
      name: "apollo-session",
      // Only persist session ID and config — never keys
      partialize: (state) => ({
        sessionId: state.sessionId,
        sessionConfig: state.sessionConfig,
      }),
    }
  )
);
