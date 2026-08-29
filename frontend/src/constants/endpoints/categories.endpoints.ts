import { getApiUrl } from "@/services/app.service";

export const categoriesEndpoints = {
  list: () => getApiUrl("/api/categories"),
  create: () => getApiUrl("/api/categories"),
  update: (id: string) => getApiUrl(`/api/categories/${id}`),
  delete: (id: string) => getApiUrl(`/api/categories/${id}`),
  reorder: () => getApiUrl("/api/categories/reorder"),
};
