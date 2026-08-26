const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  CAD: "$",
  AUD: "$",
  NZD: "$",
  SGD: "$",
  HKD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CNY: "¥",
  INR: "₹",
  KRW: "₩",
};

/** Fixed list backing the currency picker, so users choose a real code
 * instead of typing one in free-form. */
export const SUPPORTED_CURRENCIES: { code: string; name: string }[] = [
  { code: "USD", name: "US Dollar" },
  { code: "EUR", name: "Euro" },
  { code: "GBP", name: "British Pound" },
  { code: "INR", name: "Indian Rupee" },
  { code: "JPY", name: "Japanese Yen" },
  { code: "CNY", name: "Chinese Yuan" },
  { code: "CAD", name: "Canadian Dollar" },
  { code: "AUD", name: "Australian Dollar" },
  { code: "NZD", name: "New Zealand Dollar" },
  { code: "SGD", name: "Singapore Dollar" },
  { code: "HKD", name: "Hong Kong Dollar" },
  { code: "KRW", name: "South Korean Won" },
  { code: "CHF", name: "Swiss Franc" },
  { code: "SEK", name: "Swedish Krona" },
  { code: "NOK", name: "Norwegian Krone" },
  { code: "DKK", name: "Danish Krone" },
  { code: "MXN", name: "Mexican Peso" },
  { code: "BRL", name: "Brazilian Real" },
  { code: "ZAR", name: "South African Rand" },
  { code: "AED", name: "UAE Dirham" },
];

/** Formats an amount with its currency unit, falling back to "<code> <amount>"
 * for currencies with no known symbol so the unit is never dropped. */
export function formatCurrency(amount: number | string, currencyCode: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  const formatted = Math.abs(value).toFixed(2);
  const sign = value < 0 ? "-" : "";
  const symbol = CURRENCY_SYMBOLS[currencyCode];
  return symbol ? `${sign}${symbol}${formatted}` : `${sign}${formatted} ${currencyCode}`;
}

/** Same as formatCurrency, but prefixes a "+" for non-negative amounts, for
 * tables where inflow/outflow direction matters (e.g. transaction rows). */
export function formatSignedCurrency(amount: number | string, currencyCode: string): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  const formatted = formatCurrency(value, currencyCode);
  return value >= 0 ? `+${formatted}` : formatted;
}
