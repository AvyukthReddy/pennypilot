import Link from "next/link";

import { FORM_INPUT_CLASS } from "@/constants/form.constants";

import { requestPasswordReset } from "./actions";

export default async function ForgotPasswordPage(props: Readonly<PageProps<"/forgot-password">>) {
  const searchParams = await props.searchParams;
  const error = typeof searchParams.error === "string" ? searchParams.error : undefined;
  const message = typeof searchParams.message === "string" ? searchParams.message : undefined;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-4 font-sans dark:bg-black">
      <div className="w-full max-w-sm">
        <h1 className="mb-2 text-center text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Reset your password
        </h1>
        <p className="mb-6 text-center text-sm text-zinc-600 dark:text-zinc-400">
          Enter your email and we&apos;ll send you a link to reset it.
        </p>

        <form action={requestPasswordReset} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="email" className="text-sm text-zinc-600 dark:text-zinc-400">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              className={FORM_INPUT_CLASS}
            />
          </div>

          {message && (
            <p className="text-sm text-emerald-600 dark:text-emerald-400" aria-live="polite">
              {message}
            </p>
          )}
          {error && (
            <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="mt-2 rounded-md bg-black px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
          >
            Send reset link
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-zinc-600 dark:text-zinc-400">
          Remembered it?{" "}
          <Link href="/login" className="font-medium text-black underline dark:text-zinc-50">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
