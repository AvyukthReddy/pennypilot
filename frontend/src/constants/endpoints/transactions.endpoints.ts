import { getApiUrl } from "@/services/app.service";

type ListParams = {
  statementId?: string;
  limit?: number;
  offset?: number;
};

export const transactionsEndpoints = {
  list: (params?: ListParams) => {
    const query = new URLSearchParams();
    if (params?.statementId) query.set("statement_id", params.statementId);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return getApiUrl(`/api/transactions${qs ? `?${qs}` : ""}`);
  },
};
