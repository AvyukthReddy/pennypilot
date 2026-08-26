export type DocumentType = "bank_statement" | "credit_card_statement" | "unknown";

export const DOCUMENT_TYPE_OPTIONS: DocumentType[] = [
  "bank_statement",
  "credit_card_statement",
  "unknown",
];

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  bank_statement: "Bank statement",
  credit_card_statement: "Credit card statement",
  unknown: "Unknown document",
};
