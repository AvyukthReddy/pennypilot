"use client";

import { useEffect, useState, type ChangeEvent } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { FORM_INPUT_CLASS } from "@/constants/form.constants";

type InstitutionSource = "override" | "detected" | "default";

type StatementInstitutionResponse = {
  statement_id: string;
  institution: string | null;
  source: InstitutionSource;
  detected_institution: string | null;
};

const SOURCE_LABELS: Record<InstitutionSource, string> = {
  override: "set by you",
  detected: "auto-detected",
  default: "not set",
};

export function InstitutionEditor({ statementId }: { statementId: string }) {
  const [state, setState] = useState<StatementInstitutionResponse | null>(null);
  const [editing, setEditing] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [saving, setSaving] = useState(false);
  const getRequest = useApiRequest<StatementInstitutionResponse>();
  const updateRequest = useApiRequest<StatementInstitutionResponse>();

  useEffect(() => {
    getRequest.run(statementsEndpoints.institution(statementId), APP_METHOD.GET).then((data) => {
      if (data) setState(data);
    });
    // getRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statementId]);

  async function save(institution: string | null) {
    setSaving(true);
    const data = await updateRequest.run(
      statementsEndpoints.institution(statementId),
      APP_METHOD.PATCH,
      JSON.stringify({ institution }),
    );
    if (data) setState(data);
    setSaving(false);
    setEditing(false);
  }

  function startEditing() {
    setInputValue(state?.institution ?? "");
    setEditing(true);
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    setInputValue(event.target.value);
  }

  if (!getRequest.hasSettled) return null;

  if (editing) {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save(inputValue.trim() || null);
        }}
        className="flex items-center gap-2 text-sm"
      >
        <input
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          disabled={saving}
          autoFocus
          placeholder="Institution name"
          className={`${FORM_INPUT_CLASS} w-40`}
        />
        <button
          type="submit"
          disabled={saving}
          className="text-xs font-medium text-black underline dark:text-zinc-50"
        >
          Save
        </button>
        {state?.source === "override" && (
          <button
            type="button"
            onClick={() => save(null)}
            disabled={saving}
            className="text-xs text-zinc-500 underline hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50"
          >
            Reset to auto-detected{state.detected_institution ? ` (${state.detected_institution})` : ""}
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
      </form>
    );
  }

  return (
    <button
      type="button"
      onClick={startEditing}
      className="flex items-center gap-1.5 text-sm text-zinc-600 hover:text-black dark:text-zinc-400 dark:hover:text-zinc-50"
    >
      <span className="font-medium text-black dark:text-zinc-50">
        {state?.institution ?? "Not set"}
      </span>
      <span className="text-xs text-zinc-500 dark:text-zinc-500">
        ({SOURCE_LABELS[state?.source ?? "default"]})
      </span>
      <span className="text-xs underline">Edit</span>
    </button>
  );
}
