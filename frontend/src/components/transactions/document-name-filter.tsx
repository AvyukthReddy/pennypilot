"use client";

import { useEffect, useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { FORM_INPUT_CLASS } from "@/constants/form.constants";

type Statement = { filename: string };

/**
 * Text input that filters a dropdown of the caller's actual statement filenames —
 * typing narrows the list, but a filename is only added (and the parent's filter only
 * fires) once its option is clicked, so free text can never become an invalid filter.
 * Multiple filenames can be selected at once; each renders as a removable chip.
 */
export function DocumentNameFilter({
  value,
  onChange,
}: {
  value: string[];
  onChange: (filenames: string[]) => void;
}) {
  const [inputValue, setInputValue] = useState("");
  const [open, setOpen] = useState(false);
  const [filenames, setFilenames] = useState<string[]>([]);
  const listRequest = useApiRequest<Statement[]>();

  useEffect(() => {
    listRequest.run(statementsEndpoints.list(), APP_METHOD.GET).then((data) => {
      if (!data) return;
      const unique = Array.from(new Set(data.map((s) => s.filename))).sort((a, b) =>
        a.localeCompare(b),
      );
      setFilenames(unique);
    });
    // listRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const unselected = filenames.filter((name) => !value.includes(name));
  const filtered = unselected.filter((name) => name.toLowerCase().includes(inputValue.toLowerCase()));

  function addFilename(filename: string) {
    onChange([...value, filename]);
    setInputValue("");
  }

  function removeFilename(filename: string) {
    onChange(value.filter((name) => name !== filename));
  }

  function handleBlur() {
    // Delay so a click on an option (onMouseDown, below) registers before the list unmounts.
    setTimeout(() => setOpen(false), 150);
  }

  return (
    <div className="relative flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
      Document
      <div className={`${FORM_INPUT_CLASS} flex w-56 flex-wrap items-center gap-1 py-1`}>
        {value.map((filename) => (
          <span
            key={filename}
            className="flex max-w-full items-center gap-1 rounded-md bg-zinc-200 px-1.5 py-0.5 text-xs text-black dark:bg-zinc-800 dark:text-zinc-50"
          >
            <span className="max-w-[8rem] truncate">{filename}</span>
            <button
              type="button"
              onClick={() => removeFilename(filename)}
              aria-label={`Remove ${filename}`}
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
          placeholder={value.length ? "" : filenames.length ? "Select documents…" : "No statements yet"}
          disabled={filenames.length === 0}
          autoComplete="off"
          className="min-w-[6rem] flex-1 border-none bg-transparent p-0 text-sm text-black outline-none dark:text-zinc-50"
        />
      </div>
      {open && filtered.length > 0 && (
        <ul className="absolute top-full left-0 z-10 mt-1 max-h-56 w-56 overflow-y-auto rounded-md border-2 border-black bg-white text-sm shadow-lg dark:border-zinc-50 dark:bg-zinc-950">
          {filtered.map((name) => (
            <li key={name}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => addFilename(name)}
                className="w-full truncate px-3 py-1.5 text-left text-black hover:bg-zinc-100 dark:text-zinc-50 dark:hover:bg-zinc-900"
              >
                {name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
