import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "centrade-theme";
const DARK = "(prefers-color-scheme: dark)";

function stored(): Theme | null {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // stockage bloqué : le thème suit le système
  }
}

/** Thème effectif : le choix de l'opérateur s'il existe, sinon le réglage du système (posé par les jetons CSS). */
export function useTheme() {
  const [choice, setChoice] = useState<Theme | null>(stored);
  const [system, setSystem] = useState<Theme>(() => (matchMedia(DARK).matches ? "dark" : "light"));

  useEffect(() => {
    const query = matchMedia(DARK);
    const listener = () => setSystem(query.matches ? "dark" : "light");
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (choice) root.dataset.theme = choice;
    else delete root.dataset.theme;
  }, [choice]);

  const theme = choice ?? system;
  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setChoice(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* choix valable pour la session seulement */
    }
  }, [theme]);

  return { theme, toggle };
}
