import Link from "next/link";

import { logout } from "@/app/actions";

export function Navbar({ email }: { email: string }) {
  return (
    <header className="border-b-2 border-black bg-white dark:border-zinc-50 dark:bg-black">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link
          href="/dashboard"
          className="text-lg font-semibold tracking-tight text-black dark:text-zinc-50"
        >
          PennyPilot
        </Link>

        <nav className="flex items-center gap-4">
          <Link
            href="/dashboard"
            className="text-sm font-medium text-black hover:underline dark:text-zinc-50"
          >
            Dashboard
          </Link>
          <Link
            href="/statements"
            className="text-sm font-medium text-black hover:underline dark:text-zinc-50"
          >
            Statements
          </Link>
          <Link
            href="/transactions"
            className="text-sm font-medium text-black hover:underline dark:text-zinc-50"
          >
            Transactions
          </Link>
          <Link
            href="/settings"
            className="text-sm font-medium text-black hover:underline dark:text-zinc-50"
          >
            Settings
          </Link>
          <span className="hidden text-sm text-zinc-600 sm:inline dark:text-zinc-400">
            {email}
          </span>
          <form action={logout}>
            <button
              type="submit"
              className="rounded-md border-2 border-black px-3 py-1.5 text-sm font-medium text-black hover:bg-black hover:text-white dark:border-zinc-50 dark:text-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black"
            >
              Sign out
            </button>
          </form>
        </nav>
      </div>
    </header>
  );
}
