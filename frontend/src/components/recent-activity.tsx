"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { transactionsEndpoints } from "@/constants/endpoints/transactions.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { TransactionRowSkeleton } from "@/components/skeleton";

const RECENT_LIMIT = 5;

type Transaction = {
  id: string;
  transaction_date: string;
  description: string;
  amount: string;
};

type TransactionListResponse = {
  items: Transaction[];
  total: number;
};

function formatAmount(amount: string): string {
  const value = Number(amount);
  const sign = value >= 0 ? "+" : "-";
  return `${sign}$${Math.abs(value).toFixed(2)}`;
}

export function RecentActivity() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  // Starts false synchronously (unlike listRequest.loading, which only
  // flips true once the effect below actually runs, a render after mount)
  // — gating the empty-state message on this instead avoids a flash of
  // "No transactions yet" before the first fetch has even started.
  const [hasFetchedOnce, setHasFetchedOnce] = useState(false);
  const listRequest = useApiRequest<TransactionListResponse>();

  useEffect(() => {
    listRequest
      .run(transactionsEndpoints.list({ limit: RECENT_LIMIT }), APP_METHOD.GET)
      .then((data) => {
        setHasFetchedOnce(true);
        if (!data) return;
        setTransactions(data.items);
        setTotal(data.total);
      });
    // listRequest.run is stable (useCallback with no deps) — safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-black dark:text-zinc-50">Recent activity</h2>
        {!!total && (
          <Link
            href="/transactions"
            className="text-sm font-medium text-black underline dark:text-zinc-50"
          >
            View all
          </Link>
        )}
      </div>

      {(!hasFetchedOnce || listRequest.loading) && (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {Array.from({ length: RECENT_LIMIT }).map((_, i) => (
            <TransactionRowSkeleton key={i} />
          ))}
        </ul>
      )}

      {listRequest.error && (
        <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
          {listRequest.error}
        </p>
      )}

      {hasFetchedOnce && !listRequest.loading && !listRequest.error && total === 0 && (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            No transactions yet. Upload a statement to get started.
          </p>
          <Link
            href="/statements"
            className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
          >
            Upload a statement
          </Link>
        </div>
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
    </div>
  );
}
