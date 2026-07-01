import Link from "next/link";

const navItems = [
  { href: "/app", label: "Home" },
  { href: "/app/upload", label: "Upload" },
  { href: "/app/dashboards", label: "Dashboards" },
  { href: "/app/settings", label: "Settings" },
];

export default function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mx-auto flex max-w-6xl gap-8 px-6">
      <aside className="w-44 shrink-0 border-r border-neutral-200 py-8 pr-4">
        <nav className="flex flex-col gap-1 text-sm">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-2 text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
