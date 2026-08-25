import { getApiUrl } from "@/services/app.service";

export const statementsEndpoints = {
  list: () => getApiUrl("/api/statements"),
  upload: () => getApiUrl("/api/statements"),
  view: (id: string) => getApiUrl(`/api/statements/${id}/view`),
  pages: (id: string) => getApiUrl(`/api/statements/${id}/pages`),
  analysis: (id: string) => getApiUrl(`/api/statements/${id}/analysis`),
  transactionRegions: (id: string) => getApiUrl(`/api/statements/${id}/transaction-regions`),
  transactionSchema: (id: string) => getApiUrl(`/api/statements/${id}/transaction-schema`),
  transactionVerification: (id: string) =>
    getApiUrl(`/api/statements/${id}/transaction-verification`),
  financialValidation: (id: string) => getApiUrl(`/api/statements/${id}/financial-validation`),
  confidence: (id: string) => getApiUrl(`/api/statements/${id}/confidence`),
  delete: (id: string) => getApiUrl(`/api/statements/${id}`),
};
