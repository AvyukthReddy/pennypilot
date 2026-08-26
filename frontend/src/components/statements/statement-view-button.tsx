"use client";

import { useSignedUrlView } from "@/components/statements/use-signed-url-view";

export function StatementViewButton({ statementId }: { statementId: string }) {
  const { viewingId, view } = useSignedUrlView();

  return (
    <button
      type="button"
      onClick={() => view(statementId)}
      disabled={viewingId === statementId}
      className="text-sm font-medium text-black underline disabled:opacity-50 dark:text-zinc-50"
    >
      {viewingId === statementId ? "Opening…" : "View"}
    </button>
  );
}
