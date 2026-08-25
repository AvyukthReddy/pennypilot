"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { Skeleton } from "@/components/skeleton";

const SKELETON_ROW_COUNT = 3;

const ACCEPTED_TYPES = "application/pdf,text/csv,.pdf,.csv";
const MAX_STATEMENT_BYTES = 20 * 1024 * 1024;

type Statement = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  parse_error: string | null;
  created_at: string;
};

const NON_TERMINAL_STATUSES = new Set(["uploaded", "queued", "processing"]);
const POLL_INTERVAL_MS = 4000;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

const STATUS_PILL_STYLES: Record<string, string> = {
  ingested: "bg-emerald-600 text-white dark:bg-emerald-500",
  uploaded: "bg-amber-500 text-white dark:bg-amber-400 dark:text-black",
  queued: "bg-amber-500 text-white dark:bg-amber-400 dark:text-black",
  processing: "bg-amber-500 text-white dark:bg-amber-400 dark:text-black",
  failed: "bg-red-600 text-white dark:bg-red-500",
};

function StatusPill({ status }: { status: string }) {
  const classes = STATUS_PILL_STYLES[status] ?? "bg-zinc-500 text-white dark:bg-zinc-600";
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${classes}`}
    >
      {status}
    </span>
  );
}

function FileTypeBadge({ contentType }: { contentType: string }) {
  const label = contentType === "application/pdf" ? "PDF" : "CSV";
  return (
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border-2 border-black text-[10px] font-bold text-black dark:border-zinc-50 dark:text-zinc-50">
      {label}
    </div>
  );
}

function StatementRowSkeleton() {
  return (
    <li className="flex items-center gap-4 py-4">
      <Skeleton className="h-10 w-10 shrink-0" />
      <div className="min-w-0 flex-1 space-y-2">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-3 w-1/4" />
      </div>
      <Skeleton className="h-4 w-20 shrink-0" />
    </li>
  );
}

export function StatementsList() {
  const [statements, setStatements] = useState<Statement[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [viewingId, setViewingId] = useState<string | null>(null);
  const listRequest = useApiRequest<Statement[]>();
  const uploadRequest = useApiRequest<Statement>();
  const deleteRequest = useApiRequest<{ id: string }>();
  const viewRequest = useApiRequest<{ url: string }>();
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listRequest.run(statementsEndpoints.list(), APP_METHOD.GET).then((data) => {
      if (data) setStatements(data);
    });
    // listRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const hasPending = statements.some((s) => NON_TERMINAL_STATUSES.has(s.status));
    if (!hasPending) return;

    const interval = setInterval(() => {
      listRequest.run(statementsEndpoints.list(), APP_METHOD.GET).then((data) => {
        if (data) setStatements(data);
      });
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
    // listRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statements]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setUploadError(null);

    if (file.size > MAX_STATEMENT_BYTES) {
      setUploadError("File is too large, statements must be 20MB or smaller");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    const data = await uploadRequest.run(
      statementsEndpoints.upload(),
      APP_METHOD.POST,
      formData,
    );
    if (data) setStatements((prev) => [data, ...prev]);
  }

  async function handleView(id: string) {
    setViewingId(id);
    // Open the tab synchronously on click so browsers don't treat the later
    // redirect (after the signed-URL request resolves) as a blocked popup.
    // Can't pass noopener/noreferrer here, those make window.open() return
    // null, which would leave us with no handle to redirect later.
    const viewerTab = window.open("", "_blank");

    const data = await viewRequest.run(
      statementsEndpoints.view(id),
      APP_METHOD.GET,
    );
    setViewingId(null);

    if (data?.url && viewerTab) {
      viewerTab.opener = null;
      viewerTab.location.href = data.url;
    } else {
      viewerTab?.close();
    }
  }

  async function handleDelete(id: string) {
    setDeletingId(id);
    const data = await deleteRequest.run(
      statementsEndpoints.delete(id),
      APP_METHOD.DELETE,
    );
    setDeletingId(null);
    if (data) setStatements((prev) => prev.filter((s) => s.id !== id));
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadRequest.loading}
            className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
          >
            {uploadRequest.loading ? "Uploading…" : "Upload statement"}
          </button>
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            PDF or CSV, up to 20MB.
          </p>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_TYPES}
        onChange={handleFileChange}
        className="hidden"
      />

      {(uploadError || uploadRequest.error) && (
        <p
          className="text-sm text-red-600 dark:text-red-400"
          aria-live="polite"
        >
          {uploadError || uploadRequest.error}
        </p>
      )}

      {!listRequest.hasSettled && (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {Array.from({ length: SKELETON_ROW_COUNT }).map((_, i) => (
            <StatementRowSkeleton key={i} />
          ))}
        </ul>
      )}

      {listRequest.error && (
        <p
          className="text-sm text-red-600 dark:text-red-400"
          aria-live="polite"
        >
          {listRequest.error}
        </p>
      )}

      {listRequest.hasSettled &&
        !listRequest.loading &&
        !listRequest.error &&
        statements.length === 0 && (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            No statements uploaded yet.
          </p>
        )}

      {statements.length > 0 && (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {statements.map((statement) => (
            <li key={statement.id} className="flex items-center gap-4 py-4">
              <FileTypeBadge contentType={statement.content_type} />

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium text-black dark:text-zinc-50">
                    {statement.filename}
                  </p>
                  <StatusPill status={statement.status} />
                </div>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {formatBytes(statement.size_bytes)} ·{" "}
                  {new Date(statement.created_at).toLocaleDateString()}
                </p>
                {statement.parse_error && (
                  <p className="text-xs text-red-600 dark:text-red-400">
                    {statement.parse_error}
                  </p>
                )}
              </div>

              <div className="flex shrink-0 items-center gap-3">
                {statement.status === "ingested" && (
                  <Link
                    href={`/transactions?statement_id=${statement.id}&filename=${encodeURIComponent(statement.filename)}`}
                    className="text-sm font-medium text-black underline dark:text-zinc-50"
                  >
                    Transactions
                  </Link>
                )}
                {statement.status === "ingested" && statement.content_type === "application/pdf" && (
                  <Link
                    href={`/statements/analysis?statement_id=${statement.id}&filename=${encodeURIComponent(statement.filename)}`}
                    className="text-sm font-medium text-black underline dark:text-zinc-50"
                  >
                    Text blocks
                  </Link>
                )}
                <button
                  type="button"
                  onClick={() => handleView(statement.id)}
                  disabled={viewingId === statement.id}
                  className="text-sm font-medium text-black underline disabled:opacity-50 dark:text-zinc-50"
                >
                  {viewingId === statement.id ? "Opening…" : "View"}
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(statement.id)}
                  disabled={deletingId === statement.id}
                  className="text-sm font-medium text-red-600 underline disabled:opacity-50 dark:text-red-400"
                >
                  {deletingId === statement.id ? "Removing…" : "Remove"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {viewRequest.error && (
        <p
          className="text-sm text-red-600 dark:text-red-400"
          aria-live="polite"
        >
          {viewRequest.error}
        </p>
      )}

      {deleteRequest.error && (
        <p
          className="text-sm text-red-600 dark:text-red-400"
          aria-live="polite"
        >
          {deleteRequest.error}
        </p>
      )}
    </div>
  );
}
