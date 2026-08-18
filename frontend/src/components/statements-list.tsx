"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";

const ACCEPTED_TYPES = "application/pdf,text/csv,.pdf,.csv";
const MAX_STATEMENT_BYTES = 20 * 1024 * 1024;

type Statement = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  created_at: string;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
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
    // listRequest.run is stable (useCallback with no deps) — safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setUploadError(null);

    if (file.size > MAX_STATEMENT_BYTES) {
      setUploadError("File is too large — statements must be 20MB or smaller");
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
    // Can't pass noopener/noreferrer here — those make window.open() return
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

      {listRequest.loading && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Loading statements…
        </p>
      )}

      {listRequest.error && (
        <p
          className="text-sm text-red-600 dark:text-red-400"
          aria-live="polite"
        >
          {listRequest.error}
        </p>
      )}

      {!listRequest.loading &&
        !listRequest.error &&
        statements.length === 0 && (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            No statements uploaded yet.
          </p>
        )}

      {statements.length > 0 && (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {statements.map((statement) => (
            <li
              key={statement.id}
              className="flex items-center justify-between gap-4 py-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-black dark:text-zinc-50">
                  {statement.filename}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {formatBytes(statement.size_bytes)} ·{" "}
                  {new Date(statement.created_at).toLocaleDateString()} ·{" "}
                  {statement.status}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
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
