import { NextResponse, type NextRequest } from "next/server";

// Lightweight route guard: pages under these prefixes need a session hint cookie.
// Real authorisation is always enforced by the backend on every API call.
const PROTECTED = ["/dashboard", "/cases", "/research", "/settings", "/admin"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    if (!request.cookies.get("ns_csrf")) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      url.searchParams.set("next", pathname);
      return NextResponse.redirect(url);
    }
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/cases/:path*", "/research/:path*", "/settings/:path*", "/admin/:path*"],
};
