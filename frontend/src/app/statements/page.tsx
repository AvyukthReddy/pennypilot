import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { Navbar } from "@/components/navbar";
import { StatementsList } from "@/components/statements-list";
import { createClient } from "@/lib/supabase/server";

export default async function StatementsPage() {
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

      <div className="mx-auto flex max-w-2xl flex-col gap-10 px-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Statements
        </h1>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <StatementsList />
        </section>
      </div>
    </div>
  );
}
