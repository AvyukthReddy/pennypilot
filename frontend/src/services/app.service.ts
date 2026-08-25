import { APP_METHOD, JSON_CONTENT_TYPE, baseUrl, type AppMethod } from "@/constants/app.constants";
import { createClient } from "@/lib/supabase/client";

const ongoingRequests: Map<string, AbortController> = new Map();
const FILENAME_PATTERN = /filename="?([^"]+)"?/;

export const getApiUrl = (apiPath: string): string => `${baseUrl}${apiPath}`;

export const isAbortError = (err: unknown): boolean =>
  err instanceof Error && err.name === "AbortError";

const getAppHeaders = async (body?: string | FormData): Promise<HeadersInit> => {
  const headers = new Headers();

  headers.set("Cache-Control", "no-cache, no-store");

  if (!(body instanceof FormData)) {
    headers.set("Content-Type", JSON_CONTENT_TYPE);
  }

  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (session) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  return headers;
};

const buildRequestSignal = (
  controller: AbortController,
  externalSignal?: AbortSignal,
  timeoutMs?: number,
): AbortSignal => {
  const signals = [controller.signal];
  if (externalSignal) signals.push(externalSignal);
  if (timeoutMs) signals.push(AbortSignal.timeout(timeoutMs));
  return signals.length > 1 ? AbortSignal.any(signals) : controller.signal;
};

const extractFilename = (response: Response): string | undefined => {
  const disposition = response.headers.get("Content-Disposition");
  const match = disposition ? FILENAME_PATTERN.exec(disposition) : null;
  return match?.[1] ? decodeURIComponent(match[1]) : undefined;
};

const parseErrorBody = async <TError>(response: Response, isBlob?: boolean): Promise<TError> => {
  try {
    return isBlob ? ((await response.text()) as TError) : await response.json();
  } catch {
    return null as TError;
  }
};

type RequestOptions = {
  isBlob?: boolean;
  /** Dedupe/cancel key. Defaults to `${method} ${apiUrl}`, the full URL, including
   *  the query string, so two GETs that only differ by query params don't collide.
   *  Pass an explicit key to intentionally collapse requests (e.g. search-as-you-type). */
  abortKey?: string;
  credentials?: RequestCredentials;
  /** External signal (e.g. aborted from a component's unmount cleanup) that also cancels this request. */
  signal?: AbortSignal;
  /** Abort automatically if the request takes longer than this. */
  timeoutMs?: number;
};

/**
 * Every call is deduped by key (method + URL by default): starting a new request for the
 * same key aborts whichever request for that key is still in flight, so only the latest
 * one's response is ever used.
 */
export const getResponseAsync = async <TSuccess = unknown, TError = { detail?: string }>(
  apiUrl: string,
  method: AppMethod = APP_METHOD.GET,
  body?: string | FormData,
  options: RequestOptions = {},
): Promise<{ response: Response; data: TSuccess | TError; filename?: string }> => {
  const { isBlob, abortKey, credentials, signal: externalSignal, timeoutMs } = options;
  const requestKey = abortKey || `${method} ${apiUrl}`;

  ongoingRequests.get(requestKey)?.abort();
  const controller = new AbortController();
  ongoingRequests.set(requestKey, controller);

  const signal = buildRequestSignal(controller, externalSignal, timeoutMs);
  const headers = await getAppHeaders(body);

  try {
    const response = await fetch(apiUrl, {
      method,
      body,
      headers,
      signal,
      ...(credentials && { credentials }),
    });

    const filename = extractFilename(response);

    if (!response.ok) {
      const data = await parseErrorBody<TError>(response, isBlob);
      return { response, data, filename };
    }

    const data = (isBlob ? await response.blob() : await response.json()) as TSuccess;
    return { response, data, filename };
  } catch (err) {
    if (process.env.NODE_ENV !== "production") {
      if (isAbortError(err)) {
        console.warn("Request aborted:", requestKey);
      } else {
        console.error("Request failed:", err);
      }
    }
    throw err;
  } finally {
    // Only clean up if we're still the current owner of this key, an in-flight
    // request that lost a race (got superseded) must not delete the newer one's entry.
    if (ongoingRequests.get(requestKey) === controller) {
      ongoingRequests.delete(requestKey);
    }
  }
};
