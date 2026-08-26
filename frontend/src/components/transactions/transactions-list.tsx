"use client";

import { useEffect, useMemo, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import {
  transactionsEndpoints,
  type SortOrder,
  type TransactionSortBy,
  type TransactionType,
} from "@/constants/endpoints/transactions.endpoints";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { formatSignedCurrency } from "@/lib/format-currency";
import { FORM_INPUT_CLASS } from "@/constants/form.constants";
import { DOCUMENT_TYPE_LABELS, DOCUMENT_TYPE_OPTIONS } from "@/constants/document-analysis.constants";
import { ErrorText, EmptyText } from "@/components/shared/api-status-text";
import { TransactionRowSkeleton } from "@/components/shared/skeleton";
import { MultiSelectFilter } from "@/components/shared/multi-select-filter";

const PAGE_SIZE = 25;
const SKELETON_ROW_COUNT = 5;

const SORT_OPTIONS: { value: TransactionSortBy; label: string }[] = [
  { value: "transaction_date", label: "Date" },
  { value: "amount", label: "Amount" },
  { value: "description", label: "Description" },
  { value: "created_at", label: "Date added" },
];

type Transaction = {
  id: string;
  statement_id: string;
  transaction_date: string;
  post_date: string | null;
  description: string;
  amount: string;
  currency: string | null;
  created_at: string;
};

type TransactionListResponse = {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

type StatementListItem = {
  filename: string;
  institution: string | null;
  account_type_tags: string[];
  document_type: string | null;
};

export function TransactionsList({
  initialStatementId,
  initialFilename,
}: {
  initialStatementId?: string;
  initialFilename?: string;
}) {
  const [statementId, setStatementId] = useState(initialStatementId);
  const [documentNames, setDocumentNames] = useState<string[]>([]);
  const [documentTypes, setDocumentTypes] = useState<string[]>([]);
  const [institutions, setInstitutions] = useState<string[]>([]);
  const [accountTypeTags, setAccountTypeTags] = useState<string[]>([]);
  const [type, setType] = useState<TransactionType | "">("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [sortBy, setSortBy] = useState<TransactionSortBy>("transaction_date");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [page, setPage] = useState(1);

  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const listRequest = useApiRequest<TransactionListResponse>();

  const [statements, setStatements] = useState<StatementListItem[]>([]);
  const statementsRequest = useApiRequest<StatementListItem[]>();

  useEffect(() => {
    statementsRequest.run(statementsEndpoints.list(), APP_METHOD.GET).then((data) => {
      if (data) setStatements(data);
    });
    // statementsRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filenameOptions = useMemo(
    () => Array.from(new Set(statements.map((s) => s.filename))).sort((a, b) => a.localeCompare(b)),
    [statements],
  );
  const institutionOptions = useMemo(
    () =>
      Array.from(new Set(statements.map((s) => s.institution).filter((v): v is string => !!v))).sort(
        (a, b) => a.localeCompare(b),
      ),
    [statements],
  );
  const tagOptions = useMemo(
    () => Array.from(new Set(statements.flatMap((s) => s.account_type_tags))).sort((a, b) => a.localeCompare(b)),
    [statements],
  );

  function handleDocumentNamesChange(filenames: string[]) {
    setDocumentNames(filenames);
    setPage(1);
  }

  function handleDocumentTypesChange(values: string[]) {
    setDocumentTypes(values);
    setPage(1);
  }

  function handleInstitutionsChange(values: string[]) {
    setInstitutions(values);
    setPage(1);
  }

  function handleAccountTypeTagsChange(values: string[]) {
    setAccountTypeTags(values);
    setPage(1);
  }

  useEffect(() => {
    // The previous filter's rows staying visible until the new page arrives
    // (replacing them) is an acceptable brief "stale while loading" state.
    listRequest
      .run(
        transactionsEndpoints.list({
          statementId,
          documentNames: documentNames.length ? documentNames : undefined,
          documentTypes: documentTypes.length ? documentTypes : undefined,
          institutions: institutions.length ? institutions : undefined,
          accountTypeTags: accountTypeTags.length ? accountTypeTags : undefined,
          type: type || undefined,
          startDate: startDate || undefined,
          endDate: endDate || undefined,
          sortBy,
          sortOrder,
          page,
          pageSize: PAGE_SIZE,
        }),
        APP_METHOD.GET,
      )
      .then((data) => {
        if (!data) return;
        setTotal(data.total);
        setTotalPages(data.total_pages);
        setTransactions(data.items);
      });
    // listRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    statementId,
    documentNames,
    documentTypes,
    institutions,
    accountTypeTags,
    type,
    startDate,
    endDate,
    sortBy,
    sortOrder,
    page,
  ]);

  function clearStatementFilter() {
    setStatementId(undefined);
    setPage(1);
  }

  function toggleSortOrder() {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    setPage(1);
  }

  const hasFilters =
    documentNames.length > 0 ||
    documentTypes.length > 0 ||
    institutions.length > 0 ||
    accountTypeTags.length > 0 ||
    type ||
    startDate ||
    endDate;

  function clearAllFilters() {
    setDocumentNames([]);
    setDocumentTypes([]);
    setInstitutions([]);
    setAccountTypeTags([]);
    setType("");
    setStartDate("");
    setEndDate("");
    setPage(1);
  }

  return (
    <div className="flex flex-col gap-4">
      {statementId && (
        <div className="flex items-center justify-between gap-3 rounded-md border-2 border-black bg-zinc-50 px-4 py-2 text-sm dark:border-zinc-50 dark:bg-zinc-900">
          <span className="text-black dark:text-zinc-50">
            Filtered to{" "}
            <span className="font-medium">{initialFilename ?? "this statement"}</span>
          </span>
          <button
            type="button"
            onClick={clearStatementFilter}
            className="font-medium text-black underline dark:text-zinc-50"
          >
            Clear filter
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <MultiSelectFilter
          label="Document"
          value={documentNames}
          onChange={handleDocumentNamesChange}
          options={filenameOptions}
          placeholder="Select documents…"
          emptyMessage="No statements yet"
        />

        <MultiSelectFilter
          label="Institution"
          value={institutions}
          onChange={handleInstitutionsChange}
          options={institutionOptions}
          placeholder="Select institutions…"
          emptyMessage="No institutions yet"
        />

        <MultiSelectFilter
          label="Account type"
          value={accountTypeTags}
          onChange={handleAccountTypeTagsChange}
          options={tagOptions}
          placeholder="Select account types…"
          emptyMessage="No tags yet"
        />

        <MultiSelectFilter
          label="Document type"
          value={documentTypes}
          onChange={handleDocumentTypesChange}
          options={DOCUMENT_TYPE_OPTIONS}
          optionLabel={(v) => DOCUMENT_TYPE_LABELS[v as keyof typeof DOCUMENT_TYPE_LABELS] ?? v}
          placeholder="Select document types…"
        />

        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          Type
          <select
            value={type}
            onChange={(e) => {
              setType(e.target.value as TransactionType | "");
              setPage(1);
            }}
            className={FORM_INPUT_CLASS}
          >
            <option value="">All</option>
            <option value="credit">Credit</option>
            <option value="debit">Debit</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          From
          <input
            type="date"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              setPage(1);
            }}
            className={FORM_INPUT_CLASS}
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          To
          <input
            type="date"
            value={endDate}
            onChange={(e) => {
              setEndDate(e.target.value);
              setPage(1);
            }}
            className={FORM_INPUT_CLASS}
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          Sort by
          <select
            value={sortBy}
            onChange={(e) => {
              setSortBy(e.target.value as TransactionSortBy);
              setPage(1);
            }}
            className={FORM_INPUT_CLASS}
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={toggleSortOrder}
          title={sortOrder === "asc" ? "Ascending" : "Descending"}
          className="rounded-md border-2 border-black px-3 py-2 text-sm font-medium text-black hover:bg-black hover:text-white dark:border-zinc-50 dark:text-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black"
        >
          {sortOrder === "asc" ? "↑ Asc" : "↓ Desc"}
        </button>

        {hasFilters && (
          <button
            type="button"
            onClick={clearAllFilters}
            className="text-xs font-medium text-black underline dark:text-zinc-50"
          >
            Clear filters
          </button>
        )}
      </div>

      {(!listRequest.hasSettled || listRequest.loading) && transactions.length === 0 && (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {Array.from({ length: SKELETON_ROW_COUNT }).map((_, i) => (
            <TransactionRowSkeleton key={i} />
          ))}
        </ul>
      )}

      {listRequest.error && <ErrorText>{listRequest.error}</ErrorText>}

      {listRequest.hasSettled && !listRequest.loading && !listRequest.error && transactions.length === 0 && (
        <EmptyText>
          {statementId || hasFilters ? "No transactions match these filters." : "No transactions yet."}
        </EmptyText>
      )}

      {transactions.length > 0 && (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {transactions.map((txn) => {
            const isNegative = Number(txn.amount) < 0;
            return (
              <li key={txn.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-black dark:text-zinc-50">
                    {txn.description}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(txn.transaction_date).toLocaleDateString()}
                  </p>
                </div>
                <span
                  className={
                    isNegative
                      ? "shrink-0 text-sm font-semibold text-red-600 dark:text-red-400"
                      : "shrink-0 text-sm font-semibold text-emerald-600 dark:text-emerald-400"
                  }
                >
                  {formatSignedCurrency(txn.amount, "USD")}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-3 pt-2">
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            Page {page} of {totalPages} ({total} transactions)
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || listRequest.loading}
              className="rounded-md border-2 border-black px-3 py-1.5 text-sm font-medium text-black hover:bg-black hover:text-white disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-black dark:border-zinc-50 dark:text-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black dark:disabled:hover:text-zinc-50"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || listRequest.loading}
              className="rounded-md border-2 border-black px-3 py-1.5 text-sm font-medium text-black hover:bg-black hover:text-white disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-black dark:border-zinc-50 dark:text-zinc-50 dark:hover:bg-zinc-50 dark:hover:text-black dark:disabled:hover:text-zinc-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
