"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { transactionsEndpoints } from "@/constants/endpoints/transactions.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { TransactionRowSkeleton } from "@/components/skeleton";

const PAGE_SIZE = 50;
const SKELETON_ROW_COUNT = 5;

type Transaction = {
  id: string;
  statement_id: string;
  transaction_date: string;
  post_date: string | null;
  description: string;
  amount: string;
  currency: string | null;
  created_at: string;
};

type TransactionListResponse = {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
};

function formatAmount(amount: string): string {
  const value = Number(amount);
  const sign = value >= 0 ? "+" : "-";
  return `${sign}$${Math.abs(value).toFixed(2)}`;
}

export function TransactionsList({
  initialStatementId,
  initialFilename,
}: {
  initialStatementId?: string;
  initialFilename?: string;
}) {
  const [statementId, setStatementId] = useState(initialStatementId);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const listRequest = useApiRequest<TransactionListResponse>();

  function loadMore() {
    listRequest
      .run(
        transactionsEndpoints.list({ statementId, limit: PAGE_SIZE, offset: transactions.length }),
        APP_METHOD.GET,
      )
      .then((data) => {
        if (!data) return;
        setTotal(data.total);
        setTransactions((prev) => [...prev, ...data.items]);
      });
  }

  useEffect(() => {
    // The previous filter's rows staying visible until the new page arrives
    // (replacing them) is an acceptable brief "stale while loading" state.
    listRequest
      .run(transactionsEndpoints.list({ statementId, limit: PAGE_SIZE, offset: 0 }), APP_METHOD.GET)
      .then((data) => {
        if (!data) return;
        setTotal(data.total);
        setTransactions(data.items);
      });
    // listRequest.run is stable (useCallback with no deps) — safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  function clearFilter() {
    setStatementId(undefined);
  }

  const hasMore = transactions.length < total;

  return (
    <div className="flex flex-col gap-4">
      {statementId && (
        <div className="flex items-center justify-between gap-3 rounded-md border-2 border-black bg-zinc-50 px-4 py-2 text-sm dark:border-zinc-50 dark:bg-zinc-900">
          <span className="text-black dark:text-zinc-50">
            Filtered to{" "}
            <span className="font-medium">{initialFilename ?? "this statement"}</span>
          </span>
          <button
            type="button"
            onClick={clearFilter}
            className="font-medium text-black underline dark:text-zinc-50"
          >
            Clear filter
          </button>
        </div>
      )}

      {(!listRequest.hasSettled || listRequest.loading) && transactions.length === 0 && (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {Array.from({ length: SKELETON_ROW_COUNT }).map((_, i) => (
            <TransactionRowSkeleton key={i} />
          ))}
        </ul>
      )}

      {listRequest.error && (
        <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
          {listRequest.error}
        </p>
      )}

      {listRequest.hasSettled && !listRequest.loading && !listRequest.error && transactions.length === 0 && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {statementId ? "No transactions for this statement." : "No transactions yet."}
        </p>
      )}

      {transactions.length > 0 && (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {transactions.map((txn) => {
            const isNegative = Number(txn.amount) < 0;
            return (
              <li key={txn.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-black dark:text-zinc-50">
                    {txn.description}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(txn.transaction_date).toLocaleDateString()}
                  </p>
                </div>
                <span
                  className={
                    isNegative
                      ? "shrink-0 text-sm font-semibold text-red-600 dark:text-red-400"
                      : "shrink-0 text-sm font-semibold text-emerald-600 dark:text-emerald-400"
                  }
                >
                  {formatAmount(txn.amount)}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {hasMore && (
        <button
          type="button"
          onClick={loadMore}
          disabled={listRequest.loading}
          className="self-center rounded-md border-2 border-black px-4 py-2 text-sm font-medium text-black hover:bg-black hover:text-white disabled:opacity-50 dark:border-zinc-50 dark:text-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black"
        >
          {listRequest.loading ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
