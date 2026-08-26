"use client";

import { useEffect, useState, type KeyboardEvent } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { FORM_INPUT_CLASS } from "@/constants/form.constants";

type AccountTypeTagsSource = "override" | "detected" | "default";

type StatementAccountTypeTagsResponse = {
  statement_id: string;
  account_type_tags: string[];
  source: AccountTypeTagsSource;
  detected_account_type_tags: string[];
};

const SOURCE_LABELS: Record<AccountTypeTagsSource, string> = {
  override: "set by you",
  detected: "auto-detected",
  default: "not set",
};

export function AccountTypeTagsEditor({ statementId }: { statementId: string }) {
  const [state, setState] = useState<StatementAccountTypeTagsResponse | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [saving, setSaving] = useState(false);
  const getRequest = useApiRequest<StatementAccountTypeTagsResponse>();
  const updateRequest = useApiRequest<StatementAccountTypeTagsResponse>();

  useEffect(() => {
    getRequest
      .run(statementsEndpoints.accountTypeTags(statementId), APP_METHOD.GET)
      .then((data) => {
        if (data) setState(data);
      });
    // getRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  async function save(tags: string[] | null) {
    setSaving(true);
    const data = await updateRequest.run(
      statementsEndpoints.accountTypeTags(statementId),
      APP_METHOD.PATCH,
      JSON.stringify({ account_type_tags: tags }),
    );
    if (data) setState(data);
    setSaving(false);
  }

  function addTag() {
    const tag = inputValue.trim();
    if (!tag) return;
    const current = state?.account_type_tags ?? [];
    if (!current.includes(tag.toLowerCase())) {
      save([...current, tag]);
    }
    setInputValue("");
  }

  function removeTag(tag: string) {
    const current = state?.account_type_tags ?? [];
    save(current.filter((t) => t !== tag));
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addTag();
    }
  }

  if (!getRequest.hasSettled) return null;

  const tags = state?.account_type_tags ?? [];

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {tags.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 rounded-md bg-zinc-200 px-1.5 py-0.5 text-xs text-black dark:bg-zinc-800 dark:text-zinc-50"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(tag)}
              disabled={saving}
              aria-label={`Remove ${tag}`}
              className="text-zinc-500 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50"
            >
              ×
            </button>
          </span>
        ))}
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={addTag}
          disabled={saving}
          placeholder="Add tag…"
          className={`${FORM_INPUT_CLASS} w-28 py-1 text-xs`}
        />
      </div>
      <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-500">
        <span>({SOURCE_LABELS[state?.source ?? "default"]})</span>
        {state?.source === "override" && (
          <button
            type="button"
            onClick={() => save(null)}
            disabled={saving}
            className="underline hover:text-black dark:hover:text-zinc-50"
          >
            Reset to auto-detected
            {state.detected_account_type_tags.length
              ? ` (${state.detected_account_type_tags.join(", ")})`
              : ""}
          </button>
        )}
      </div>
    </div>
  );
}
