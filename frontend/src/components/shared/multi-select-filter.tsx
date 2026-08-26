"use client";

import { useState } from "react";

import { FORM_INPUT_CLASS } from "@/constants/form.constants";

/**
 * Text input that filters a dropdown of caller-supplied options — typing narrows
 * the list, but a value is only added (and onChange only fires) once its option is
 * clicked, so free text can never become an invalid filter. Multiple values can be
 * selected at once; each renders as a removable chip.
 */
export function MultiSelectFilter({
  label,
  value,
  onChange,
  options,
  optionLabel,
  placeholder,
  emptyMessage,
}: {
  label: string;
  value: string[];
  onChange: (values: string[]) => void;
  options: string[];
  optionLabel?: (value: string) => string;
  placeholder?: string;
  emptyMessage?: string;
}) {
  const [inputValue, setInputValue] = useState("");
  const [open, setOpen] = useState(false);

  const display = (v: string) => optionLabel?.(v) ?? v;

  const unselected = options.filter((option) => !value.includes(option));
  const filtered = unselected.filter((option) =>
    display(option).toLowerCase().includes(inputValue.toLowerCase()),
  );

  function addValue(option: string) {
    onChange([...value, option]);
    setInputValue("");
  }

  function removeValue(option: string) {
    onChange(value.filter((v) => v !== option));
  }

  function handleBlur() {
    // Delay so a click on an option (onMouseDown, below) registers before the list unmounts.
    setTimeout(() => setOpen(false), 150);
  }

  return (
    <div className="relative flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
      {label}
      <div className={`${FORM_INPUT_CLASS} flex w-56 flex-wrap items-center gap-1 py-1`}>
        {value.map((v) => (
          <span
            key={v}
            className="flex max-w-full items-center gap-1 rounded-md bg-zinc-200 px-1.5 py-0.5 text-xs text-black dark:bg-zinc-800 dark:text-zinc-50"
          >
            <span className="max-w-[8rem] truncate">{display(v)}</span>
            <button
              type="button"
              onClick={() => removeValue(v)}
              aria-label={`Remove ${display(v)}`}
              className="text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50"
            >
              ×
            </button>
          </span>
        ))}
        <input
          type="text"
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={handleBlur}
          placeholder={value.length ? "" : options.length ? (placeholder ?? "Select…") : (emptyMessage ?? "No options yet")}
          disabled={options.length === 0}
          autoComplete="off"
          className="min-w-[6rem] flex-1 border-none bg-transparent p-0 text-sm text-black outline-none dark:text-zinc-50"
        />
      </div>
      {open && filtered.length > 0 && (
        <ul className="absolute top-full left-0 z-10 mt-1 max-h-56 w-56 overflow-y-auto rounded-md border-2 border-black bg-white text-sm shadow-lg dark:border-zinc-50 dark:bg-zinc-950">
          {filtered.map((option) => (
            <li key={option}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => addValue(option)}
                className="w-full truncate px-3 py-1.5 text-left text-black hover:bg-zinc-100 dark:text-zinc-50 dark:hover:bg-zinc-900"
              >
                {display(option)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
