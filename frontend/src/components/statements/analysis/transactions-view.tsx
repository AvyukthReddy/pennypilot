"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { transactionsEndpoints } from "@/constants/endpoints/transactions.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { useCurrency } from "@/components/currency-context";
import { formatSignedCurrency } from "@/lib/format-currency";
import { Skeleton } from "@/components/skeleton";

const MAX_ROWS = 200;

type Transaction = {
  id: string;
  transaction_date: string;
  post_date: string | null;
  description: string;
  amount: string;
  currency: string | null;
};

type TransactionListResponse = {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
};

function TransactionsSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-8 w-full" />
    </div>
  );
}

export function TransactionsView({ statementId }: { statementId: string }) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const listRequest = useApiRequest<TransactionListResponse>();
  const { currency } = useCurrency();

  useEffect(() => {
    listRequest
      .run(transactionsEndpoints.list({ statementId, limit: MAX_ROWS }), APP_METHOD.GET)
      .then((data) => {
        if (!data) return;
        setTransactions(data.items);
        setTotal(data.total);
      });
    // listRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  if (!listRequest.hasSettled) {
    return <TransactionsSkeleton />;
  }

  if (listRequest.error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
        {listRequest.error}
      </p>
    );
  }

  if (transactions.length === 0) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        No transactions extracted for this statement yet.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-zinc-500 dark:text-zinc-400">
              <th className="py-1 pr-4 font-medium">Date</th>
              <th className="py-1 pr-4 font-medium">Description</th>
              <th className="py-1 font-medium">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {transactions.map((txn) => {
              const isNegative = Number(txn.amount) < 0;
              return (
                <tr key={txn.id}>
                  <td className="py-1.5 pr-4 text-zinc-600 dark:text-zinc-400">
                    {txn.transaction_date}
                  </td>
                  <td className="py-1.5 pr-4 text-black dark:text-zinc-50">{txn.description}</td>
                  <td
                    className={
                      isNegative
                        ? "py-1.5 font-medium text-red-600 dark:text-red-400"
                        : "py-1.5 font-medium text-emerald-600 dark:text-emerald-400"
                    }
                  >
                    {formatSignedCurrency(txn.amount, currency)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {total > transactions.length && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Showing {transactions.length} of {total} transactions.
        </p>
      )}
    </div>
  );
}
