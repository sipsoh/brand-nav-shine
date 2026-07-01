"use client";

import { UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { clerkEnabled } from "@/lib/auth";

export function AuthControls() {
  if (!clerkEnabled) {
    return null;
  }
  return <SignedState />;
}

function SignedState() {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) {
    return null;
  }
  if (!isSignedIn) {
    return (
      <Link href="/sign-in" className="hover:text-neutral-900">
        Sign in
      </Link>
    );
  }
  return <UserButton />;
}
