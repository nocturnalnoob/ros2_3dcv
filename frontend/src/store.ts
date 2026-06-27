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

export type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  toggle: () => void;
}

// Theme preference, persisted across sessions. Defaults to light.
export const useTheme = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: "light",
      toggle: () => set({ theme: get().theme === "light" ? "dark" : "light" }),
    }),
    { name: "ros2-3dcv-theme" }
  )
);
