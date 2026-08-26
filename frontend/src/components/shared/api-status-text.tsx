import type { ReactNode } from "react";

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
      {children}
    </p>
  );
}

export function EmptyText({ children }: { children: ReactNode }) {
  return <p className="text-sm text-zinc-600 dark:text-zinc-400">{children}</p>;
}
