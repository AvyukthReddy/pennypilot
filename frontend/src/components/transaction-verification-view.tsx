"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { Skeleton } from "@/components/skeleton";

type IssueType =
  | "missing_transaction"
  | "duplicate_transaction"
  | "wrong_date"
  | "wrong_amount"
  | "wrong_sign"
  | "split_or_merged_transaction"
  | "other";

type VerificationIssue = {
  type: IssueType;
  page: number;
  description: string;
};

type StatementTransactionVerificationResponse = {
  statement_id: string;
  valid: boolean | null;
  issues: VerificationIssue[];
};

const ISSUE_LABELS: Record<IssueType, string> = {
  missing_transaction: "Missing transaction",
  duplicate_transaction: "Duplicate transaction",
  wrong_date: "Wrong date",
  wrong_amount: "Wrong amount",
  wrong_sign: "Wrong debit/credit sign",
  split_or_merged_transaction: "Split or merged transaction",
  other: "Other issue",
};

function VerificationSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-8 w-full" />
    </div>
  );
}

export function TransactionVerificationView({ statementId }: { statementId: string }) {
  const [report, setReport] = useState<StatementTransactionVerificationResponse | null>(null);
  const verificationRequest = useApiRequest<StatementTransactionVerificationResponse>();

  useEffect(() => {
    verificationRequest
      .run(statementsEndpoints.transactionVerification(statementId), APP_METHOD.GET)
      .then((data) => {
        if (data) setReport(data);
      });
    // verificationRequest.run is stable (useCallback with no deps) — safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  if (!verificationRequest.hasSettled) {
    return <VerificationSkeleton />;
  }

  if (verificationRequest.error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
        {verificationRequest.error}
      </p>
    );
  }

  if (!report || report.valid === null) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        No verification has run yet — either extraction hasn&apos;t run, or no
        transactions were extracted to check.
      </p>
    );
  }

  if (report.valid && report.issues.length === 0) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        All extracted transactions were verified — no issues found.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-zinc-500 dark:text-zinc-400">
            <th className="py-1 pr-4 font-medium">Issue</th>
            <th className="py-1 pr-4 font-medium">Page</th>
            <th className="py-1 font-medium">Description</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {report.issues.map((issue, index) => (
            <tr key={index}>
              <td className="py-1.5 pr-4 text-black dark:text-zinc-50">
                {ISSUE_LABELS[issue.type]}
              </td>
              <td className="py-1.5 pr-4 text-zinc-600 dark:text-zinc-400">{issue.page}</td>
              <td className="py-1.5 text-zinc-600 dark:text-zinc-400">{issue.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
