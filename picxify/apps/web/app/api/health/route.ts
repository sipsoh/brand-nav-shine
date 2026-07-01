import { NextResponse } from "next/server";

export function GET() {
  return NextResponse.json({ ok: true, service: "picxify-web", version: "0.1.0" });
}
