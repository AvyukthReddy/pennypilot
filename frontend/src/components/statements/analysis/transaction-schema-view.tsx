"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { Skeleton } from "@/components/skeleton";

type FieldSource = {
  source: string;
  semantics: "debit" | "credit" | "amount" | null;
};

type TransactionFields = {
  transaction_date: FieldSource;
  post_date: FieldSource | null;
  description: FieldSource;
  amount: FieldSource[];
  currency: FieldSource | null;
};

type StatementTransactionSchemaResponse = {
  statement_id: string;
  transaction_fields: TransactionFields | null;
};

type SchemaRow = { label: string; source: string };

function buildRows(fields: TransactionFields): SchemaRow[] {
  const rows: SchemaRow[] = [
    { label: "Transaction date", source: fields.transaction_date.source },
  ];
  if (fields.post_date) {
    rows.push({ label: "Post date", source: fields.post_date.source });
  }
  rows.push({ label: "Description", source: fields.description.source });
  for (const amount of fields.amount) {
    rows.push({
      label: amount.semantics ? `Amount (${amount.semantics})` : "Amount",
      source: amount.source,
    });
  }
  if (fields.currency) {
    rows.push({ label: "Currency", source: fields.currency.source });
  }
  return rows;
}

function SchemaSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-8 w-full" />
    </div>
  );
}

export function TransactionSchemaView({ statementId }: { statementId: string }) {
  const [fields, setFields] = useState<TransactionFields | null>(null);
  const schemaRequest = useApiRequest<StatementTransactionSchemaResponse>();

  useEffect(() => {
    schemaRequest
      .run(statementsEndpoints.transactionSchema(statementId), APP_METHOD.GET)
      .then((data) => {
        if (data) setFields(data.transaction_fields);
      });
    // schemaRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  if (!schemaRequest.hasSettled) {
    return <SchemaSkeleton />;
  }

  if (schemaRequest.error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
        {schemaRequest.error}
      </p>
    );
  }

  if (!fields) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        No transaction schema discovered yet. Either discovery hasn&apos;t run yet, or
        no transaction regions were detected on this statement.
      </p>
    );
  }

  const rows = buildRows(fields);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-zinc-500 dark:text-zinc-400">
            <th className="py-1 pr-4 font-medium">Field</th>
            <th className="py-1 font-medium">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {rows.map((row) => (
            <tr key={row.label}>
              <td className="py-1.5 pr-4 text-black dark:text-zinc-50">{row.label}</td>
              <td className="py-1.5 text-zinc-600 dark:text-zinc-400">{row.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
