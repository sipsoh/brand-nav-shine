// Clerk activates as soon as NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is set (see .env.example).
// Until then the app renders without auth so local dev and CI builds work keyless.
export const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
