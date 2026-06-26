import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ModuleStatus = "not_started" | "attempted" | "passed";

interface ProgressState {
  status: Record<string, ModuleStatus>;
  savedCode: Record<string, string>;
  setStatus: (id: string, s: ModuleStatus) => void;
  saveCode: (id: string, code: string) => void;
}

// Anonymous progress lives in localStorage; swap for an account-backed store
// behind the same interface when auth is added.
export const useProgress = create<ProgressState>()(
  persist(
    (set) => ({
      status: {},
      savedCode: {},
      setStatus: (id, s) =>
        set((st) => ({ status: { ...st.status, [id]: s } })),
      saveCode: (id, code) =>
        set((st) => ({ savedCode: { ...st.savedCode, [id]: code } })),
    }),
    { name: "ros2-3dcv-progress" }
  )
);
