import { getApiUrl } from "@/services/app.service";

export type TransactionType = "credit" | "debit";
export type TransactionSortBy = "transaction_date" | "amount" | "description" | "created_at";
export type SortOrder = "asc" | "desc";

type ListParams = {
  statementId?: string;
  documentNames?: string[];
  type?: TransactionType;
  startDate?: string;
  endDate?: string;
  sortBy?: TransactionSortBy;
  sortOrder?: SortOrder;
  page?: number;
  pageSize?: number;
};

export const transactionsEndpoints = {
  list: (params?: ListParams) => {
    const query = new URLSearchParams();
    if (params?.statementId) query.set("statement_id", params.statementId);
    for (const name of params?.documentNames ?? []) query.append("document_name", name);
    if (params?.type) query.set("type", params.type);
    if (params?.startDate) query.set("start_date", params.startDate);
    if (params?.endDate) query.set("end_date", params.endDate);
    if (params?.sortBy) query.set("sort_by", params.sortBy);
    if (params?.sortOrder) query.set("sort_order", params.sortOrder);
    if (params?.page) query.set("page", String(params.page));
    if (params?.pageSize) query.set("page_size", String(params.pageSize));
    const qs = query.toString();
    return getApiUrl(`/api/transactions${qs ? `?${qs}` : ""}`);
  },
};
