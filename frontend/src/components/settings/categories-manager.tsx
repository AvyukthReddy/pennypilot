"use client";

import { useEffect, useState, type KeyboardEvent } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { categoriesEndpoints } from "@/constants/endpoints/categories.endpoints";
import { FORM_INPUT_CLASS } from "@/constants/form.constants";
import { useApiRequest } from "@/hooks/use-api-request";
import { ErrorText } from "@/components/shared/api-status-text";
import { CategoriesSkeleton } from "@/components/shared/skeleton";

type Category = {
  id: string;
  name: string;
  parent_id: string | null;
  is_default: boolean;
  sort_order: number;
  subcategories: Category[] | null;
};

function ReorderButtons({
  disabled,
  atStart,
  atEnd,
  label,
  onMoveUp,
  onMoveDown,
}: {
  disabled: boolean;
  atStart: boolean;
  atEnd: boolean;
  label: string;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  return (
    <div className="flex flex-col leading-none">
      <button
        type="button"
        onClick={onMoveUp}
        disabled={disabled || atStart}
        aria-label={`Move ${label} up`}
        className="text-[10px] text-zinc-500 hover:text-black disabled:opacity-30 dark:text-zinc-400 dark:hover:text-zinc-50"
      >
        ▲
      </button>
      <button
        type="button"
        onClick={onMoveDown}
        disabled={disabled || atEnd}
        aria-label={`Move ${label} down`}
        className="text-[10px] text-zinc-500 hover:text-black disabled:opacity-30 dark:text-zinc-400 dark:hover:text-zinc-50"
      >
        ▼
      </button>
    </div>
  );
}

export function CategoriesManager() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [newTopLevelName, setNewTopLevelName] = useState("");
  const [addingSubcategoryFor, setAddingSubcategoryFor] = useState<string | null>(null);
  const [newSubcategoryName, setNewSubcategoryName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  const listRequest = useApiRequest<Category[]>();
  const mutationRequest = useApiRequest<unknown>();
  const busy = mutationRequest.loading;

  async function refresh() {
    const data = await listRequest.run(categoriesEndpoints.list(), APP_METHOD.GET);
    if (data) setCategories(data);
  }

  useEffect(() => {
    listRequest.run(categoriesEndpoints.list(), APP_METHOD.GET).then((data) => {
      if (data) setCategories(data);
    });
    // listRequest.run is stable (useCallback with no deps), safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createCategory(name: string, parentId: string | null) {
    const trimmed = name.trim();
    if (!trimmed) return;
    const data = await mutationRequest.run(
      categoriesEndpoints.create(),
      APP_METHOD.POST,
      JSON.stringify({ name: trimmed, parent_id: parentId }),
    );
    if (!data) return;
    if (parentId) {
      setAddingSubcategoryFor(null);
      setNewSubcategoryName("");
    } else {
      setNewTopLevelName("");
    }
    await refresh();
  }

  async function renameCategory(id: string) {
    const trimmed = editingName.trim();
    if (!trimmed) return;
    const data = await mutationRequest.run(
      categoriesEndpoints.update(id),
      APP_METHOD.PATCH,
      JSON.stringify({ name: trimmed }),
    );
    if (!data) return;
    setEditingId(null);
    await refresh();
  }

  async function deleteCategory(id: string) {
    const data = await mutationRequest.run(categoriesEndpoints.delete(id), APP_METHOD.DELETE);
    if (data) await refresh();
  }

  async function reorder(siblings: Category[], parentId: string | null, index: number, direction: -1 | 1) {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= siblings.length) return;
    const reordered = [...siblings];
    [reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]];
    const data = await mutationRequest.run(
      categoriesEndpoints.reorder(),
      APP_METHOD.PATCH,
      JSON.stringify({ parent_id: parentId, ordered_ids: reordered.map((c) => c.id) }),
    );
    if (data) await refresh();
  }

  function startEditing(category: Category) {
    setEditingId(category.id);
    setEditingName(category.name);
  }

  function handleEditKeyDown(event: KeyboardEvent<HTMLInputElement>, id: string) {
    if (event.key === "Enter") {
      event.preventDefault();
      renameCategory(id);
    } else if (event.key === "Escape") {
      setEditingId(null);
    }
  }

  if (!listRequest.hasSettled) return <CategoriesSkeleton />;

  if (listRequest.error) return <ErrorText>{listRequest.error}</ErrorText>;

  return (
    <div className="flex flex-col gap-4">
      {categories.map((category, index) => {
        const subcategories = category.subcategories ?? [];
        return (
          <div
            key={category.id}
            className="rounded-lg border border-zinc-300 p-3 dark:border-zinc-700"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ReorderButtons
                  disabled={busy}
                  atStart={index === 0}
                  atEnd={index === categories.length - 1}
                  label={category.name}
                  onMoveUp={() => reorder(categories, null, index, -1)}
                  onMoveDown={() => reorder(categories, null, index, 1)}
                />

                {editingId === category.id ? (
                  <input
                    autoFocus
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    onKeyDown={(e) => handleEditKeyDown(e, category.id)}
                    onBlur={() => setEditingId(null)}
                    className={`${FORM_INPUT_CLASS} py-1 text-sm`}
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => startEditing(category)}
                    disabled={busy}
                    className="text-sm font-medium text-black disabled:opacity-50 dark:text-zinc-50"
                  >
                    {category.name}
                  </button>
                )}
              </div>

              <button
                type="button"
                onClick={() => deleteCategory(category.id)}
                disabled={busy}
                className="text-xs font-medium text-red-600 underline disabled:opacity-50 dark:text-red-400"
              >
                Delete
              </button>
            </div>

            <div className="mt-2 flex flex-col gap-1.5 pl-7">
              {subcategories.map((sub, subIndex) => (
                <div key={sub.id} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <ReorderButtons
                      disabled={busy}
                      atStart={subIndex === 0}
                      atEnd={subIndex === subcategories.length - 1}
                      label={sub.name}
                      onMoveUp={() => reorder(subcategories, category.id, subIndex, -1)}
                      onMoveDown={() => reorder(subcategories, category.id, subIndex, 1)}
                    />

                    {editingId === sub.id ? (
                      <input
                        autoFocus
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => handleEditKeyDown(e, sub.id)}
                        onBlur={() => setEditingId(null)}
                        className={`${FORM_INPUT_CLASS} py-1 text-xs`}
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => startEditing(sub)}
                        disabled={busy}
                        className="text-xs text-zinc-700 disabled:opacity-50 dark:text-zinc-300"
                      >
                        {sub.name}
                      </button>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => deleteCategory(sub.id)}
                    disabled={busy}
                    className="text-xs font-medium text-red-600 underline disabled:opacity-50 dark:text-red-400"
                  >
                    Delete
                  </button>
                </div>
              ))}

              {addingSubcategoryFor === category.id ? (
                <input
                  autoFocus
                  value={newSubcategoryName}
                  onChange={(e) => setNewSubcategoryName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      createCategory(newSubcategoryName, category.id);
                    } else if (e.key === "Escape") {
                      setAddingSubcategoryFor(null);
                      setNewSubcategoryName("");
                    }
                  }}
                  onBlur={() => createCategory(newSubcategoryName, category.id)}
                  placeholder="Subcategory name…"
                  className={`${FORM_INPUT_CLASS} w-40 py-1 text-xs`}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setAddingSubcategoryFor(category.id)}
                  disabled={busy}
                  className="self-start text-xs text-zinc-500 underline hover:text-black disabled:opacity-50 dark:text-zinc-400 dark:hover:text-zinc-50"
                >
                  + Add subcategory
                </button>
              )}
            </div>
          </div>
        );
      })}

      <div className="flex items-center gap-2">
        <input
          value={newTopLevelName}
          onChange={(e) => setNewTopLevelName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              createCategory(newTopLevelName, null);
            }
          }}
          placeholder="New category name…"
          disabled={busy}
          className={`${FORM_INPUT_CLASS} flex-1`}
        />
        <button
          type="button"
          onClick={() => createCategory(newTopLevelName, null)}
          disabled={busy || !newTopLevelName.trim()}
          className="rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
        >
          Add
        </button>
      </div>

      {mutationRequest.error && <ErrorText>{mutationRequest.error}</ErrorText>}
    </div>
  );
}
