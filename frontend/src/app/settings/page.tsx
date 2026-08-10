import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { Navbar } from "@/components/navbar";
import { ProfileForm } from "@/components/profile-form";
import { createClient } from "@/lib/supabase/server";

import { changePassword } from "./actions";

export default async function SettingsPage(props: Readonly<PageProps<"/settings">>) {
  const supabase = createClient(await cookies());
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const searchParams = await props.searchParams;
  const error = typeof searchParams.error === "string" ? searchParams.error : undefined;
  const message = typeof searchParams.message === "string" ? searchParams.message : undefined;

  const inputClass =
    "rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-black outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50";

  return (
    <div className="min-h-screen bg-zinc-50 font-sans dark:bg-black">
      <Navbar email={user.email ?? ""} />

      <div className="mx-auto flex max-w-2xl flex-col gap-10 px-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Settings
        </h1>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <h2 className="mb-4 text-lg font-semibold text-black dark:text-zinc-50">Profile</h2>
          <ProfileForm />
        </section>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <h2 className="mb-4 text-lg font-semibold text-black dark:text-zinc-50">Password</h2>
          <form action={changePassword} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <label htmlFor="password" className="text-sm text-zinc-600 dark:text-zinc-400">
                New password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
                className={inputClass}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label
                htmlFor="confirmPassword"
                className="text-sm text-zinc-600 dark:text-zinc-400"
              >
                Confirm new password
              </label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
                className={inputClass}
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
              className="mt-2 self-start rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
            >
              Update password
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
