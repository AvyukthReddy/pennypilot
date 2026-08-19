import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Navbar } from "@/components/navbar";
import { RecentActivity } from "@/components/recent-activity";
import { createClient } from "@/lib/supabase/server";

const QUICK_LINK_CLASSES =
  "rounded-md border-2 border-black px-4 py-2 text-sm font-medium text-black hover:bg-black hover:text-white dark:border-zinc-50 dark:text-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black";

export default async function HomePage() {
  const supabase = createClient(await cookies());
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <div className="min-h-screen bg-zinc-50 font-sans dark:bg-black">
      <Navbar email={user.email ?? ""} />

      <main className="mx-auto max-w-4xl px-6 py-16">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Welcome back
        </h1>
        <p className="mt-2 max-w-xl text-zinc-600 dark:text-zinc-400">
          Here&apos;s what&apos;s happened recently across your uploaded statements.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/statements" className={QUICK_LINK_CLASSES}>
            Upload a statement
          </Link>
          <Link href="/transactions" className={QUICK_LINK_CLASSES}>
            View transactions
          </Link>
        </div>

        <div className="mt-10 max-w-2xl">
          <RecentActivity />
        </div>
      </main>
    </div>
  );
}
