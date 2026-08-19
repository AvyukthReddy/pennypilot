import { getApiUrl } from "@/services/app.service";

export const statementsEndpoints = {
  list: () => getApiUrl("/api/statements"),
  upload: () => getApiUrl("/api/statements"),
  view: (id: string) => getApiUrl(`/api/statements/${id}/view`),
  delete: (id: string) => getApiUrl(`/api/statements/${id}`),
};
