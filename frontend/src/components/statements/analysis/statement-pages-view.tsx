"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { Skeleton } from "@/components/skeleton";

type TextBlock = {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

type ImageRegion = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type Page = {
  page_number: number;
  width: number;
  height: number;
  text: string;
  text_blocks: TextBlock[];
  images: ImageRegion[];
};

type StatementPagesResponse = {
  statement_id: string;
  pages: Page[];
};

function PageSkeleton() {
  return (
    <div className="space-y-2 rounded-md border-2 border-black p-4 dark:border-zinc-50">
      <Skeleton className="h-4 w-1/4" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-5/6" />
    </div>
  );
}

export function StatementPagesView({ statementId }: { statementId: string }) {
  const [pages, setPages] = useState<Page[]>([]);
  const pagesRequest = useApiRequest<StatementPagesResponse>();

  useEffect(() => {
    pagesRequest.run(statementsEndpoints.pages(statementId), APP_METHOD.GET).then((data) => {
      if (data) setPages(data.pages);
    });
    // pagesRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  return (
    <div className="flex flex-col gap-4">
      {!pagesRequest.hasSettled && (
        <div className="flex flex-col gap-4">
          <PageSkeleton />
          <PageSkeleton />
        </div>
      )}

      {pagesRequest.error && (
        <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
          {pagesRequest.error}
        </p>
      )}

      {pagesRequest.hasSettled && !pagesRequest.loading && !pagesRequest.error && pages.length === 0 && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          No page data for this statement. Either it hasn&apos;t finished analysis yet, or it&apos;s
          a CSV (which has no pages).
        </p>
      )}

      {pages.map((page) => (
        <details
          key={page.page_number}
          className="rounded-md border-2 border-black open:pb-4 dark:border-zinc-50"
          open={page.page_number === 1}
        >
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-black dark:text-zinc-50">
            Page {page.page_number}: {Math.round(page.width)}×{Math.round(page.height)} ·{" "}
            {page.text_blocks.length} text blocks
            {page.images.length > 0 ? ` · ${page.images.length} images` : ""}
          </summary>

          <div className="px-4">
            {page.text_blocks.length === 0 ? (
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                No text extracted on this page.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="text-zinc-500 dark:text-zinc-400">
                      <th className="py-1 pr-3 font-medium">x</th>
                      <th className="py-1 pr-3 font-medium">y</th>
                      <th className="py-1 pr-3 font-medium">width</th>
                      <th className="py-1 pr-3 font-medium">height</th>
                      <th className="py-1 font-medium">text</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                    {page.text_blocks.map((block, i) => (
                      <tr key={i}>
                        <td className="py-1 pr-3 text-zinc-500 dark:text-zinc-400">
                          {block.x.toFixed(0)}
                        </td>
                        <td className="py-1 pr-3 text-zinc-500 dark:text-zinc-400">
                          {block.y.toFixed(0)}
                        </td>
                        <td className="py-1 pr-3 text-zinc-500 dark:text-zinc-400">
                          {block.width.toFixed(0)}
                        </td>
                        <td className="py-1 pr-3 text-zinc-500 dark:text-zinc-400">
                          {block.height.toFixed(0)}
                        </td>
                        <td className="py-1 text-black dark:text-zinc-50">{block.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}
