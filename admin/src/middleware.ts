export { auth as middleware } from "@/lib/auth";

export const config = {
  matcher: [
    // Protect everything except login, static files, and auth API
    "/((?!login|api/auth|_next/static|_next/image|favicon.ico).*)",
  ],
};
