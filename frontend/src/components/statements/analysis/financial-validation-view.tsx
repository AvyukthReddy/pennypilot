"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { useCurrency } from "@/components/currency-context";
import { formatCurrency } from "@/lib/format-currency";
import { Skeleton } from "@/components/skeleton";

type FinancialIssueType =
  | "invalid_date"
  | "date_outside_period"
  | "invalid_amount"
  | "duplicate_transaction"
  | "balance_mismatch";

type FinancialValidationIssue = {
  type: FinancialIssueType;
  description: string;
};

type BalanceCheck = {
  beginning_balance: string;
  net_change: string;
  expected_ending_balance: string;
  actual_ending_balance: string;
  reconciled: boolean;
};

type RecoveryAttempt = {
  page: number;
  succeeded: boolean;
};

type StatementFinancialValidationResponse = {
  statement_id: string;
  valid: boolean | null;
  issues: FinancialValidationIssue[];
  balance_check: BalanceCheck | null;
  recovery_attempts: RecoveryAttempt[];
};

function formatRecoveryNote(attempts: RecoveryAttempt[]): string {
  const succeededPage = attempts.find((a) => a.succeeded)?.page;
  const pages = attempts.map((a) => a.page).join(", ");
  if (succeededPage !== undefined) {
    return `Recovery: re-extracted page ${succeededPage}, resolved`;
  }
  return `Recovery attempted on page${attempts.length > 1 ? "s" : ""} ${pages}, still unresolved`;
}

const ISSUE_LABELS: Record<FinancialIssueType, string> = {
  invalid_date: "Invalid date",
  date_outside_period: "Date outside statement period",
  invalid_amount: "Invalid amount",
  duplicate_transaction: "Duplicate transaction",
  balance_mismatch: "Balance mismatch",
};

function ValidationSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-8 w-full" />
    </div>
  );
}

export function FinancialValidationView({ statementId }: { statementId: string }) {
  const [report, setReport] = useState<StatementFinancialValidationResponse | null>(null);
  const validationRequest = useApiRequest<StatementFinancialValidationResponse>();
  const { currency } = useCurrency();

  useEffect(() => {
    validationRequest
      .run(statementsEndpoints.financialValidation(statementId), APP_METHOD.GET)
      .then((data) => {
        if (data) setReport(data);
      });
    // validationRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  if (!validationRequest.hasSettled) {
    return <ValidationSkeleton />;
  }

  if (validationRequest.error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
        {validationRequest.error}
      </p>
    );
  }

  if (!report || report.valid === null) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        No financial validation has run yet. Either extraction hasn&apos;t run, or
        no transactions were extracted to check.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {report.valid && report.issues.length === 0 ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          All checks passed, no issues found.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-zinc-500 dark:text-zinc-400">
                <th className="py-1 pr-4 font-medium">Issue</th>
                <th className="py-1 font-medium">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {report.issues.map((issue, index) => (
                <tr key={index}>
                  <td className="py-1.5 pr-4 text-black dark:text-zinc-50">
                    {ISSUE_LABELS[issue.type]}
                  </td>
                  <td className="py-1.5 text-zinc-600 dark:text-zinc-400">
                    {issue.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {report.balance_check && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 border-t border-zinc-200 pt-3 text-sm dark:border-zinc-800">
          <dt className="text-zinc-500 dark:text-zinc-400">Beginning balance</dt>
          <dd className="text-black dark:text-zinc-50">
            {formatCurrency(report.balance_check.beginning_balance, currency)}
          </dd>
          <dt className="text-zinc-500 dark:text-zinc-400">Net change</dt>
          <dd className="text-black dark:text-zinc-50">
            {formatCurrency(report.balance_check.net_change, currency)}
          </dd>
          <dt className="text-zinc-500 dark:text-zinc-400">Expected ending balance</dt>
          <dd className="text-black dark:text-zinc-50">
            {formatCurrency(report.balance_check.expected_ending_balance, currency)}
          </dd>
          <dt className="text-zinc-500 dark:text-zinc-400">Actual ending balance</dt>
          <dd className="text-black dark:text-zinc-50">
            {formatCurrency(report.balance_check.actual_ending_balance, currency)}
          </dd>
          <dt className="text-zinc-500 dark:text-zinc-400">Reconciled</dt>
          <dd className="text-black dark:text-zinc-50">
            {report.balance_check.reconciled ? "Yes" : "No"}
          </dd>
        </dl>
      )}

      {report.recovery_attempts.length > 0 && (
        <p className="border-t border-zinc-200 pt-3 text-sm text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
          {formatRecoveryNote(report.recovery_attempts)}
        </p>
      )}
    </div>
  );
}
