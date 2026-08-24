import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { DocumentAnalysisSummary } from "@/components/document-analysis-summary";
import { FinancialValidationView } from "@/components/financial-validation-view";
import { Navbar } from "@/components/navbar";
import { StatementPagesView } from "@/components/statement-pages-view";
import { StatementViewButton } from "@/components/statement-view-button";
import { TransactionRegionsView } from "@/components/transaction-regions-view";
import { TransactionSchemaView } from "@/components/transaction-schema-view";
import { TransactionVerificationView } from "@/components/transaction-verification-view";
import { createClient } from "@/lib/supabase/server";

type SearchParams = Promise<{ [key: string]: string | string[] | undefined }>;

export default async function StatementAnalysisPage({
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

  if (!statementId) {
    redirect("/statements");
  }

  return (
    <div className="min-h-screen bg-zinc-50 font-sans dark:bg-black">
      <Navbar email={user.email ?? ""} />

      <div className="mx-auto flex max-w-4xl flex-col gap-10 px-4 py-16">
        <div className="flex flex-row items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
              Document analysis
            </h1>
            {filename && (
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{filename}</p>
            )}
          </div>
          <StatementViewButton statementId={statementId} />
        </div>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <DocumentAnalysisSummary statementId={statementId} />
        </section>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <h2 className="mb-4 text-lg font-semibold text-black dark:text-zinc-50">
            Transaction regions
          </h2>
          <TransactionRegionsView statementId={statementId} />
        </section>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <h2 className="mb-4 text-lg font-semibold text-black dark:text-zinc-50">
            Transaction schema
          </h2>
          <TransactionSchemaView statementId={statementId} />
        </section>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <h2 className="mb-4 text-lg font-semibold text-black dark:text-zinc-50">
            Transaction verification
          </h2>
          <TransactionVerificationView statementId={statementId} />
        </section>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <h2 className="mb-4 text-lg font-semibold text-black dark:text-zinc-50">
            Financial validation
          </h2>
          <FinancialValidationView statementId={statementId} />
        </section>

        <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
          <StatementPagesView statementId={statementId} />
        </section>
      </div>
    </div>
  );
}
