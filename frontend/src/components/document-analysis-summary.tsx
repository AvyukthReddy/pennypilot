"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { Skeleton } from "@/components/skeleton";

type DocumentSection = {
  type: string;
  pages: number[];
};

type DocumentAnalysis = {
  document_type: "bank_statement" | "credit_card_statement" | "unknown";
  institution: string | null;
  account_type: string | null;
  account_last4: string | null;
  currency: string | null;
  statement_start: string | null;
  statement_end: string | null;
  beginning_balance: string | null;
  ending_balance: string | null;
  sections: DocumentSection[];
};

type StatementAnalysisResponse = {
  statement_id: string;
  document_analysis: DocumentAnalysis | null;
};

const DOCUMENT_TYPE_LABELS: Record<DocumentAnalysis["document_type"], string> = {
  bank_statement: "Bank statement",
  credit_card_statement: "Credit card statement",
  unknown: "Unknown document",
};

const SECTION_TYPE_LABELS: Record<string, string> = {
  account_summary: "Account summary",
  transactions: "Transactions",
  fees: "Fees",
  interest: "Interest",
  disclosures: "Disclosures",
  other: "Other",
};

function formatPageRange(pages: number[]): string {
  if (pages.length === 0) return "";
  const sorted = [...pages].sort((a, b) => a - b);
  const ranges: string[] = [];
  let start = sorted[0];
  let prev = sorted[0];

  for (let i = 1; i <= sorted.length; i++) {
    const current = sorted[i];
    if (current === prev + 1) {
      prev = current;
      continue;
    }
    ranges.push(start === prev ? `${start}` : `${start}–${prev}`);
    if (current !== undefined) {
      start = current;
      prev = current;
    }
  }

  return `pages ${ranges.join(", ")}`;
}

function formatPeriod(start: string | null, end: string | null): string | null {
  if (!start && !end) return null;
  if (start && end) return `${start} – ${end}`;
  return start ?? end;
}

function SummarySkeleton() {
  return (
    <div className="flex flex-col gap-3 rounded-md border-2 border-black p-4 dark:border-zinc-50">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-3 w-56" />
      <Skeleton className="h-3 w-48" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

export function DocumentAnalysisSummary({ statementId }: { statementId: string }) {
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null);
  const analysisRequest = useApiRequest<StatementAnalysisResponse>();

  useEffect(() => {
    analysisRequest
      .run(statementsEndpoints.analysis(statementId), APP_METHOD.GET)
      .then((data) => {
        if (data) setAnalysis(data.document_analysis);
      });
    // analysisRequest.run is stable (useCallback with no deps) — safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  if (!analysisRequest.hasSettled) {
    return <SummarySkeleton />;
  }

  if (analysisRequest.error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
        {analysisRequest.error}
      </p>
    );
  }

  if (!analysis) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Not yet classified — analysis may still be running, or this statement was
        skipped (e.g. a scanned PDF with no extracted text).
      </p>
    );
  }

  const period = formatPeriod(analysis.statement_start, analysis.statement_end);

  return (
    <div className="flex flex-col gap-3 rounded-md border-2 border-black p-4 dark:border-zinc-50">
      <span className="w-fit rounded-full bg-black px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white dark:bg-zinc-50 dark:text-black">
        {DOCUMENT_TYPE_LABELS[analysis.document_type]}
      </span>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
        {analysis.institution && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">Institution</dt>
            <dd className="text-black dark:text-zinc-50">{analysis.institution}</dd>
          </>
        )}
        {analysis.account_type && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">Account type</dt>
            <dd className="text-black dark:text-zinc-50">{analysis.account_type}</dd>
          </>
        )}
        {analysis.account_last4 && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">Account</dt>
            <dd className="text-black dark:text-zinc-50">•••• {analysis.account_last4}</dd>
          </>
        )}
        {analysis.currency && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">Currency</dt>
            <dd className="text-black dark:text-zinc-50">{analysis.currency}</dd>
          </>
        )}
        {period && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">Period</dt>
            <dd className="text-black dark:text-zinc-50">{period}</dd>
          </>
        )}
        {analysis.beginning_balance && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">Beginning balance</dt>
            <dd className="text-black dark:text-zinc-50">{analysis.beginning_balance}</dd>
          </>
        )}
        {analysis.ending_balance && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">Ending balance</dt>
            <dd className="text-black dark:text-zinc-50">{analysis.ending_balance}</dd>
          </>
        )}
      </dl>

      {analysis.sections.length > 0 && (
        <ul className="flex flex-col gap-1 border-t border-zinc-200 pt-3 text-sm dark:border-zinc-800">
          {analysis.sections.map((section, i) => (
            <li key={i} className="flex items-center justify-between gap-4">
              <span className="text-black dark:text-zinc-50">
                {SECTION_TYPE_LABELS[section.type] ?? section.type}
              </span>
              <span className="text-zinc-500 dark:text-zinc-400">
                {formatPageRange(section.pages)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
