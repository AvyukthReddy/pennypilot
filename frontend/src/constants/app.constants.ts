export const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";

export const JSON_CONTENT_TYPE = "application/json;charset=UTF-8";

export const APP_METHOD = {
  GET: "GET",
  POST: "POST",
  PUT: "PUT",
  PATCH: "PATCH",
  DELETE: "DELETE",
} as const;

export type AppMethod = (typeof APP_METHOD)[keyof typeof APP_METHOD];

// Shared cadence for any client-side polling against non-terminal statement
// state (the statements list and the analysis page's pipeline progress).
export const POLL_INTERVAL_MS = 30000;
