"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { AppMethod } from "@/constants/app.constants";
import { getResponseAsync, isAbortError } from "@/services/app.service";

type ApiOptions = NonNullable<Parameters<typeof getResponseAsync>[3]>;

function extractErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    if (typeof record.message === "string") return record.message;
  }
  return fallback;
}

/**
 * Wraps getResponseAsync with the loading/error/status bookkeeping every call
 * site needs anyway, and cancels any in-flight request automatically when the
 * component unmounts (no manual AbortController needed at call sites).
 *
 * `run` resolves to the parsed success data, or `undefined` on failure
 * (including a request superseded/unmounted mid-flight, which is treated as
 * silent — `error`/`status` are only set for real failures). For an
 * `if (data) {...} else {...}` shape, the else branch reads `error`/`status`
 * from the hook instead of a raw `response` — `run` doesn't return one.
 */
export function useApiRequest<TSuccess = unknown, TError = { detail?: string }>() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const unmountController = useRef<AbortController | undefined>(undefined);

  useEffect(() => {
    unmountController.current = new AbortController();
    return () => unmountController.current?.abort();
  }, []);

  const run = useCallback(
    async (
      apiUrl: string,
      method?: AppMethod,
      body?: string | FormData,
      options?: ApiOptions,
    ): Promise<TSuccess | undefined> => {
      setLoading(true);
      setError(null);
      setStatus(null);

      const { signal: callerSignal, ...restOptions } = options ?? {};

      try {
        const { response, data } = await getResponseAsync<TSuccess, TError>(apiUrl, method, body, {
          ...restOptions,
          signal: callerSignal ?? unmountController.current?.signal,
        });

        setStatus(response.status);

        if (!response.ok) {
          setError(extractErrorMessage(data, "Something went wrong"));
          return undefined;
        }

        return data as TSuccess;
      } catch (err) {
        if (!isAbortError(err)) {
          setError(err instanceof Error ? err.message : "Something went wrong");
        }
        return undefined;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  return { loading, error, status, run };
}
