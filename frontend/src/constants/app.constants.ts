export const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";

export const JSON_CONTENT_TYPE = "application/json;charset=UTF-8";

export const APP_METHOD = {
  GET: "GET",
  POST: "POST",
  PUT: "PUT",
  DELETE: "DELETE",
} as const;

export type AppMethod = (typeof APP_METHOD)[keyof typeof APP_METHOD];
