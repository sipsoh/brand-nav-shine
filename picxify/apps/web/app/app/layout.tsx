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
      <div className="border-b border-neutral-200 bg-white/85 backdrop-blur">
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
                    ? "bg-indigo-50 font-semibold text-indigo-600"
                    : "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900"
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
