import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import Link from "next/link";
import { AuthControls } from "@/components/auth/auth-controls";
import { clerkEnabled } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Picxify — Drop in messy data. Get the story.",
  description:
    "Picxify turns messy business data into polished, trustworthy, client-ready dashboards with source traces and shareable links.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const content = (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-neutral-200 bg-white dark:border-white/10 dark:bg-[#0d0d0d]">
          <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-semibold tracking-tight dark:text-white">
              Picxify
            </Link>
            <div className="flex items-center gap-6 text-sm text-neutral-600 dark:text-neutral-400">
              <Link href="/pricing" className="hover:text-neutral-900 dark:hover:text-white">
                Pricing
              </Link>
              <Link href="/app" className="hover:text-neutral-900 dark:hover:text-white">
                App
              </Link>
              <AuthControls />
              <Link
                href="/app/upload"
                className="rounded-lg bg-neutral-900 px-4 py-2 font-medium text-white hover:bg-neutral-700 dark:bg-white/10 dark:hover:bg-white/20"
              >
                Create a dashboard
              </Link>
            </div>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );

  return clerkEnabled ? <ClerkProvider>{content}</ClerkProvider> : content;
}
