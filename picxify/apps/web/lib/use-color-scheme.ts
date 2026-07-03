"use client";

import { useEffect, useState } from "react";

/** Tracks the active theme so canvas-rendered charts (which can't read CSS)
 * pick the matching palette. Dark mode is class-based (a `.dark` class on
 * <html>), not OS-based, so this mirrors that class and stays in sync with a
 * future in-app toggle. With no toggle set yet, it resolves to light. */
export function useColorScheme(): "light" | "dark" {
  const [scheme, setScheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const root = document.documentElement;
    const read = () => setScheme(root.classList.contains("dark") ? "dark" : "light");
    read();
    const observer = new MutationObserver(read);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return scheme;
}
