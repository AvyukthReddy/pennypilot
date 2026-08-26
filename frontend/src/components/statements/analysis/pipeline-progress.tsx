"use client";

import { useEffect, useState } from "react";

import { APP_METHOD, POLL_INTERVAL_MS } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { isNonTerminalStatus } from "@/components/statements/statement-status";
import { ErrorText } from "@/components/shared/api-status-text";
import { Skeleton } from "@/components/shared/skeleton";

type StatementProgressResponse = {
  statement_id: string;
  status: string;
  processing_stage: string | null;
  processing_detail: string | null;
  parse_error: string | null;
};

type StageState = "done" | "current" | "pending" | "error";

const STAGES: { id: string; label: string }[] = [
  { id: "ingesting", label: "Analyzing document" },
  { id: "understanding", label: "Classifying document" },
  { id: "detecting_regions", label: "Detecting transaction regions" },
  { id: "discovering_schema", label: "Discovering transaction schema" },
  { id: "extracting", label: "Extracting and verifying transactions" },
  { id: "validating", label: "Validating and reconciling" },
  { id: "scoring_confidence", label: "Scoring confidence" },
];

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5" aria-hidden>
      <circle cx="10" cy="10" r="9" className="fill-emerald-600 dark:fill-emerald-500" />
      <path
        d="M6 10.5l2.5 2.5L14 7.5"
        stroke="white"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ErrorIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5" aria-hidden>
      <circle cx="10" cy="10" r="9" className="fill-red-600 dark:fill-red-500" />
      <path
        d="M7 7l6 6M13 7l-6 6"
        stroke="white"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <span
      aria-hidden
      className="block h-5 w-5 animate-spin rounded-full border-2 border-zinc-300 border-t-black dark:border-zinc-700 dark:border-t-zinc-50"
    />
  );
}

function PendingIcon() {
  return (
    <span
      aria-hidden
      className="block h-5 w-5 rounded-full border-2 border-zinc-300 dark:border-zinc-700"
    />
  );
}

function StageIcon({ state }: { state: StageState }) {
  if (state === "done") return <CheckIcon />;
  if (state === "error") return <ErrorIcon />;
  if (state === "current") return <SpinnerIcon />;
  return <PendingIcon />;
}

function ProgressSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-5 w-5 shrink-0 rounded-full" />
          <Skeleton className="h-4 w-48" />
        </div>
      ))}
    </div>
  );
}

export function PipelineProgress({ statementId }: { statementId: string }) {
  const [progress, setProgress] = useState<StatementProgressResponse | null>(null);
  const progressRequest = useApiRequest<StatementProgressResponse>();

  useEffect(() => {
    progressRequest
      .run(statementsEndpoints.progress(statementId), APP_METHOD.GET)
      .then((data) => {
        if (data) setProgress(data);
      });
    // progressRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  useEffect(() => {
    if (!progress || !isNonTerminalStatus(progress.status)) return;

    const interval = setInterval(() => {
      progressRequest
        .run(statementsEndpoints.progress(statementId), APP_METHOD.GET)
        .then((data) => {
          if (data) setProgress(data);
        });
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
    // progressRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress?.status, statementId]);

  // Fully done: the rest of the page already tells the story, no need for
  // a step list that would just show every stage checked off. Renders
  // nothing at all (not even the section shell) so the page doesn't show
  // an empty "Processing status" box once a statement finishes.
  if (progressRequest.hasSettled && !progressRequest.error && (!progress || progress.status === "ingested")) {
    return null;
  }

  return (
    <section className="rounded-2xl border-2 border-black bg-white p-6 dark:border-zinc-50 dark:bg-zinc-950">
      <h2 className="mb-4 text-lg font-semibold text-black dark:text-zinc-50">
        Processing status
      </h2>

      {!progressRequest.hasSettled && <ProgressSkeleton />}

      {progressRequest.error && <ErrorText>{progressRequest.error}</ErrorText>}

      {progressRequest.hasSettled && !progressRequest.error && progress && (
        <PipelineSteps progress={progress} />
      )}
    </section>
  );
}

function PipelineSteps({ progress }: { progress: StatementProgressResponse }) {
  const currentIndex = STAGES.findIndex((stage) => stage.id === progress.processing_stage);

  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-2.5">
        {STAGES.map((stage, index) => {
          const state: StageState =
            progress.status === "failed" && index === currentIndex
              ? "error"
              : index < currentIndex
                ? "done"
                : index === currentIndex
                  ? "current"
                  : "pending";
          return (
            <li key={stage.id} className="flex items-center gap-3">
              <StageIcon state={state} />
              <span
                className={
                  state === "pending"
                    ? "text-sm text-zinc-500 dark:text-zinc-400"
                    : "text-sm font-medium text-black dark:text-zinc-50"
                }
              >
                {stage.label}
              </span>
              {state === "current" && progress.processing_detail && (
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  {progress.processing_detail}
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {progress.status === "failed" && progress.parse_error && (
        <p className="text-sm text-red-600 dark:text-red-400">{progress.parse_error}</p>
      )}
    </div>
  );
}
