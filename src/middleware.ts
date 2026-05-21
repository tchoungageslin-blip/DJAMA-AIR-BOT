import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Public routes
  const publicRoutes = ["/login", "/api/webhook", "/api/dashboard/auth/login"];
  if (publicRoutes.some((route) => pathname.startsWith(route))) {
    return NextResponse.next();
  }

  // API routes pass through (auth handled by FastAPI)
  if (pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  // Dashboard routes are protected client-side (token check in layout)
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
