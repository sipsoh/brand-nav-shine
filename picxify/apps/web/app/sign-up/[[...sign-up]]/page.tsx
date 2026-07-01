import { SignUp } from "@clerk/nextjs";
import { clerkEnabled } from "@/lib/auth";

export default function SignUpPage() {
  if (!clerkEnabled) {
    return (
      <div className="mx-auto max-w-xl px-6 py-24 text-center text-neutral-600">
        Authentication is not configured yet. Set <code>NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code>{" "}
        and <code>CLERK_SECRET_KEY</code> in <code>.env.local</code> to enable sign-up.
      </div>
    );
  }
  return (
    <div className="flex justify-center py-16">
      <SignUp />
    </div>
  );
}
