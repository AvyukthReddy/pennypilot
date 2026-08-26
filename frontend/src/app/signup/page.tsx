import Link from "next/link";

import { FORM_INPUT_CLASS } from "@/constants/form.constants";

import { signup } from "./actions";

export default async function SignupPage(props: Readonly<PageProps<"/signup">>) {
  const searchParams = await props.searchParams;
  const error = typeof searchParams.error === "string" ? searchParams.error : undefined;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-4 font-sans dark:bg-black">
      <div className="w-full max-w-sm">
        <h1 className="mb-6 text-center text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Create your PennyPilot account
        </h1>

        <form action={signup} className="flex flex-col gap-4">
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

          <div className="flex flex-col gap-1">
            <label htmlFor="password" className="text-sm text-zinc-600 dark:text-zinc-400">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              required
              minLength={6}
              autoComplete="new-password"
              className={FORM_INPUT_CLASS}
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="mt-2 rounded-md bg-black px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
          >
            Sign up
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-zinc-600 dark:text-zinc-400">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-black underline dark:text-zinc-50">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
