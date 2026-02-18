"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
  { href: "/sizes", label: "Sizes", icon: "📏" },
  { href: "/rules", label: "Rules", icon: "🔀" },
  { href: "/sets", label: "Sets", icon: "📦" },
  { href: "/measurements", label: "Measurements", icon: "🔬" },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen">
      <aside className="w-56 bg-zinc-900 text-white flex flex-col">
        <div className="p-4 text-lg font-bold border-b border-zinc-700">
          💅 SEV Admin
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
                pathname.startsWith(item.href)
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-400 hover:text-white hover:bg-zinc-800"
              )}
            >
              <span>{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="p-4 border-t border-zinc-700">
          <form action="/api/auth/signout" method="POST">
            <button className="text-sm text-zinc-400 hover:text-white">Sign out</button>
          </form>
        </div>
      </aside>
      <main className="flex-1 overflow-auto bg-zinc-50 p-6">{children}</main>
    </div>
  );
}
