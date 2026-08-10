import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { DashboardPreview } from "@/components/dashboard-preview";
import { Navbar } from "@/components/navbar";
import { createClient } from "@/lib/supabase/server";

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

      <main className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Welcome back
        </h1>
        <p className="mt-2 max-w-xl text-zinc-600 dark:text-zinc-400">
          This is where your accounts, budgets, and insights will live. Nothing&apos;s connected
          yet — head to Settings to finish setting up your profile.
        </p>

        <div className="mt-10 max-w-sm">
          <DashboardPreview />
        </div>
      </main>
    </div>
  );
}
