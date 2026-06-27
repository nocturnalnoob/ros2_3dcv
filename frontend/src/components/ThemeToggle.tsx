import { useEffect } from "react";
import { useTheme } from "../store";

/** Applies the persisted theme to <html data-theme> and renders a toggle. */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return (
    <button className="theme-toggle" onClick={toggle}
            title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}>
      {theme === "light" ? "🌙 Dark" : "☀️ Light"}
    </button>
  );
}

/** Hook to apply the theme without rendering the button (used at app root). */
export function useApplyTheme() {
  const theme = useTheme((s) => s.theme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
}
