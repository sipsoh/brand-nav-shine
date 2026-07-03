"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/app", label: "Home" },
  { href: "/app/upload", label: "Upload" },
  { href: "/app/dashboards", label: "Dashboards" },
  { href: "/app/settings", label: "Settings" },
];

export default function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  return (
    <div>
      <div className="border-b border-neutral-200 bg-white/85 backdrop-blur dark:border-white/10 dark:bg-[#0d0d0d]/85">
        <nav className="mx-auto flex max-w-7xl gap-1 px-6 py-2">
          {navItems.map((item) => {
            const active =
              item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-emerald-50 font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                    : "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-white/10 dark:hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="mx-auto max-w-7xl px-6">{children}</div>
    </div>
  );
}
