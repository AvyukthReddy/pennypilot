"use client";

import { useState, type ChangeEvent } from "react";

import { useCurrency } from "@/components/currency-context";
import { SUPPORTED_CURRENCIES } from "@/lib/format-currency";

const SOURCE_LABELS = {
  override: "set by you",
  detected: "auto-detected",
  default: "default, nothing detected",
} as const;

export function CurrencyEditor() {
  const { currency, source, detectedCurrency, loading, setCurrency } = useCurrency();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleChange(event: ChangeEvent<HTMLSelectElement>) {
    setSaving(true);
    await setCurrency(event.target.value);
    setSaving(false);
    setEditing(false);
  }

  async function handleResetToDetected() {
    setSaving(true);
    await setCurrency(null);
    setSaving(false);
    setEditing(false);
  }

  if (loading) return null;

  if (editing) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <select
          defaultValue={currency}
          onChange={handleChange}
          disabled={saving}
          aria-label="Currency"
          className="rounded-md border-2 border-black bg-white px-2 py-1 font-mono text-black dark:border-zinc-50 dark:bg-zinc-950 dark:text-zinc-50"
        >
          {SUPPORTED_CURRENCIES.map(({ code, name }) => (
            <option key={code} value={code}>
              {code}: {name}
            </option>
          ))}
        </select>
        {source === "override" && (
          <button
            type="button"
            onClick={handleResetToDetected}
            disabled={saving}
            className="text-xs text-zinc-500 underline hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50"
          >
            Reset to auto-detected{detectedCurrency ? ` (${detectedCurrency})` : ""}
          </button>
        )}
        <button
          type="button"
          onClick={() => setEditing(false)}
          disabled={saving}
          className="text-xs text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="flex items-center gap-1.5 text-sm text-zinc-600 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50"
    >
      <span className="font-mono font-semibold text-black dark:text-zinc-50">{currency}</span>
      <span className="text-xs text-zinc-500 dark:text-zinc-500">({SOURCE_LABELS[source]})</span>
      <span className="text-xs underline">Edit</span>
    </button>
  );
}
