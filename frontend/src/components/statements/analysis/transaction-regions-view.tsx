"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { Skeleton } from "@/components/skeleton";

type TransactionRegion = {
  page: number;
  region: [number, number, number, number];
};

type StatementTransactionRegionsResponse = {
  statement_id: string;
  transaction_regions: TransactionRegion[] | null;
};

function RegionsSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-8 w-full" />
      <Skeleton className="h-8 w-full" />
    </div>
  );
}

export function TransactionRegionsView({ statementId }: { statementId: string }) {
  const [regions, setRegions] = useState<TransactionRegion[]>([]);
  const regionsRequest = useApiRequest<StatementTransactionRegionsResponse>();

  useEffect(() => {
    regionsRequest
      .run(statementsEndpoints.transactionRegions(statementId), APP_METHOD.GET)
      .then((data) => {
        if (data) setRegions(data.transaction_regions ?? []);
      });
    // regionsRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  if (!regionsRequest.hasSettled) {
    return <RegionsSkeleton />;
  }

  if (regionsRequest.error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
        {regionsRequest.error}
      </p>
    );
  }

  if (regions.length === 0) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        No transaction regions detected. Either detection hasn&apos;t run yet, or no
        transaction section was found on this statement.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-zinc-500 dark:text-zinc-400">
            <th className="py-1 pr-4 font-medium">Page</th>
            <th className="py-1 font-medium">Region [x0, y0, x1, y1]</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {regions.map((r) => (
            <tr key={r.page}>
              <td className="py-1.5 pr-4 text-black dark:text-zinc-50">{r.page}</td>
              <td className="py-1.5 text-zinc-600 dark:text-zinc-400">
                [{r.region.map((n) => Math.round(n)).join(", ")}]
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
