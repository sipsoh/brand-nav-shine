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
        <header className="border-b border-neutral-200 bg-white">
          <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Picxify
            </Link>
            <div className="flex items-center gap-6 text-sm text-neutral-600">
              <Link href="/pricing" className="hover:text-neutral-900">
                Pricing
              </Link>
              <Link href="/app" className="hover:text-neutral-900">
                App
              </Link>
              <AuthControls />
              <Link
                href="/app/upload"
                className="rounded-lg bg-neutral-900 px-4 py-2 font-medium text-white hover:bg-neutral-700"
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
