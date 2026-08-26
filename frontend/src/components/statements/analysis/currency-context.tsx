"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";

type CurrencySource = "override" | "detected" | "default";

type StatementCurrencyResponse = {
  statement_id: string;
  currency: string;
  source: CurrencySource;
  detected_currency: string | null;
};

type CurrencyContextValue = {
  currency: string;
  source: CurrencySource;
  detectedCurrency: string | null;
  loading: boolean;
  setCurrency: (currency: string | null) => Promise<void>;
};

const CurrencyContext = createContext<CurrencyContextValue | null>(null);

/** Reads the statement's effective currency (user override, else AI-detected,
 * else a USD default), shared across every section on the analysis page that
 * displays an amount so they all stay in sync after an edit. */
export function useCurrency(): CurrencyContextValue {
  const ctx = useContext(CurrencyContext);
  if (!ctx) {
    throw new Error("useCurrency must be used within a CurrencyProvider");
  }
  return ctx;
}

export function CurrencyProvider({
  statementId,
  children,
}: {
  statementId: string;
  children: ReactNode;
}) {
  const [state, setState] = useState<StatementCurrencyResponse | null>(null);
  const getRequest = useApiRequest<StatementCurrencyResponse>();
  const updateRequest = useApiRequest<StatementCurrencyResponse>();

  useEffect(() => {
    getRequest.run(statementsEndpoints.currency(statementId), APP_METHOD.GET).then((data) => {
      if (data) setState(data);
    });
    // getRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  async function setCurrency(currency: string | null) {
    const data = await updateRequest.run(
      statementsEndpoints.currency(statementId),
      APP_METHOD.PATCH,
      JSON.stringify({ currency }),
    );
    if (data) setState(data);
  }

  return (
    <CurrencyContext.Provider
      value={{
        currency: state?.currency ?? "USD",
        source: state?.source ?? "default",
        detectedCurrency: state?.detected_currency ?? null,
        loading: !getRequest.hasSettled,
        setCurrency,
      }}
    >
      {children}
    </CurrencyContext.Provider>
  );
}
