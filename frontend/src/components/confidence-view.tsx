"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { Skeleton } from "@/components/skeleton";

type ConfidenceStatusValue = "validated" | "needs_review" | "unreliable";

type ConfidenceBreakdown = {
  extraction: number;
  verification: number;
  financial_validation: number;
  balance_reconciliation: number;
  structural_consistency: number;
};

type StatementConfidenceResponse = {
  statement_id: string;
  score: number | null;
  status: ConfidenceStatusValue | null;
  warnings: string[];
  breakdown: ConfidenceBreakdown | null;
};

const STATUS_LABELS: Record<ConfidenceStatusValue, string> = {
  validated: "Validated",
  needs_review: "Needs review",
  unreliable: "Unreliable",
};

const STATUS_PILL_CLASSES: Record<ConfidenceStatusValue, string> = {
  validated: "bg-emerald-600 text-white dark:bg-emerald-500 dark:text-black",
  needs_review: "bg-amber-500 text-black dark:bg-amber-400 dark:text-black",
  unreliable: "bg-red-600 text-white dark:bg-red-500 dark:text-black",
};

const BREAKDOWN_LABELS: Record<keyof ConfidenceBreakdown, string> = {
  extraction: "Extraction",
  verification: "Verification",
  financial_validation: "Financial validation",
  balance_reconciliation: "Balance reconciliation",
  structural_consistency: "Structural consistency",
};

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function ConfidenceSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-6 w-32" />
      <Skeleton className="h-4 w-64" />
    </div>
  );
}

export function ConfidenceView({ statementId }: { statementId: string }) {
  const [confidence, setConfidence] = useState<StatementConfidenceResponse | null>(null);
  const confidenceRequest = useApiRequest<StatementConfidenceResponse>();

  useEffect(() => {
    confidenceRequest
      .run(statementsEndpoints.confidence(statementId), APP_METHOD.GET)
      .then((data) => {
        if (data) setConfidence(data);
      });
    // confidenceRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  if (!confidenceRequest.hasSettled) {
    return <ConfidenceSkeleton />;
  }

  if (confidenceRequest.error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
        {confidenceRequest.error}
      </p>
    );
  }

  if (!confidence || confidence.score === null || confidence.status === null) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        No confidence score yet. Either the pipeline hasn&apos;t run, or this
        statement has no transactions section to score.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <span
          className={`w-fit rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${STATUS_PILL_CLASSES[confidence.status]}`}
        >
          {STATUS_LABELS[confidence.status]}
        </span>
        <span className="text-2xl font-semibold text-black dark:text-zinc-50">
          {formatPercent(confidence.score)}
        </span>
      </div>

      {confidence.warnings.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm text-zinc-600 dark:text-zinc-400">
          {confidence.warnings.map((warning, index) => (
            <li key={index}>&bull; {warning}</li>
          ))}
        </ul>
      )}

      {confidence.breakdown && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 border-t border-zinc-200 pt-3 text-sm dark:border-zinc-800">
          {(Object.keys(confidence.breakdown) as (keyof ConfidenceBreakdown)[]).map((key) => (
            <div key={key} className="contents">
              <dt className="text-zinc-500 dark:text-zinc-400">{BREAKDOWN_LABELS[key]}</dt>
              <dd className="text-black dark:text-zinc-50">
                {formatPercent(confidence.breakdown![key])}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
