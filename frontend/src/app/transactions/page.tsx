import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { Navbar } from "@/components/navbar";
import { TransactionsList } from "@/components/transactions-list";
import { createClient } from "@/lib/supabase/server";

type SearchParams = Promise<{ [key: string]: string | string[] | undefined }>;

export default async function TransactionsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const supabase = createClient(await cookies());
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const params = await searchParams;
  const statementId = typeof params.statement_id === "string" ? params.statement_id : undefined;
  const filename = typeof params.filename === "string" ? params.filename : undefined;

  return (
    <div className="min-h-screen bg-zinc-50 font-sans dark:bg-black">
      <Navbar email={user.email ?? ""} />

      <div className="mx-auto flex max-w-4xl flex-col gap-10 px-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Transactions
        </h1>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <TransactionsList initialStatementId={statementId} initialFilename={filename} />
        </section>
      </div>
    </div>
  );
}
