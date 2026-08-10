import Link from "next/link";

export default function AuthCodeErrorPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-4 text-center font-sans dark:bg-black">
      <div className="w-full max-w-sm">
        <h1 className="mb-3 text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          That link didn&apos;t work
        </h1>
        <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-400">
          This confirmation link is invalid or has expired. Request a new one below.
        </p>
        <div className="flex justify-center gap-3">
          <Link
            href="/forgot-password"
            className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
          >
            Reset password
          </Link>
          <Link
            href="/login"
            className="rounded-md border-2 border-black px-4 py-2 text-sm font-medium text-black hover:bg-black hover:text-white dark:border-zinc-50 dark:text-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black"
          >
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
