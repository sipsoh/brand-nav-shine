"use client";

import { useEffect, useState } from "react";

/** Tracks the system light/dark preference so canvas-rendered charts (which
 * can't rely on CSS media queries) can pick the matching theme. */
export function useColorScheme(): "light" | "dark" {
  const [scheme, setScheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    setScheme(query.matches ? "dark" : "light");
    const onChange = (event: MediaQueryListEvent) => setScheme(event.matches ? "dark" : "light");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return scheme;
}
