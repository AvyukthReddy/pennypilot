# Statement upload flow

**Type**: feature
**Status**: done
**Started**: 2026-08-17

## What & why

User asked to build the "statement upload flow" — the first step toward PennyPilot
being able to ingest bank/credit-card statements. No `statements` (or `transactions`)
table existed before this.

Scoped with the user up front via two questions:

1. **Scope**: upload + store only (not parse-into-transactions). Chosen over the fuller
   pipeline to keep this session focused — parsing is a separate future feature that
   needs its own architecture call (sync in FastAPI vs. the still-unused Celery
   `worker/`).
2. **File types**: PDF and CSV (not OFX/QFX).

Follow-up in the same session: user asked for the ability to view uploaded files too.
Since the bucket is private (see below), this needed a signed-URL endpoint rather than
a stored public link.

## Tried

- Followed the existing avatar-upload pattern (`backend/app/api/profile.py` +
  `backend/app/services/storage.py`'s `upload_avatar`) as the template for
  `upload_statement`/`delete_statement`, migration style, and RLS provisioning.
- Initially made `DELETE /api/statements/{id}` return `204 No Content`, matching REST
  convention. Caught in verification (not in the browser — by reading
  `frontend/src/services/app.service.ts`) that the shared `getResponseAsync` always
  calls `response.json()` on a successful response; a 204 has no body and would throw,
  surfacing as a false "error" in the UI. Changed the endpoint to return `200` with
  `{"id": ...}` instead, rather than special-casing empty bodies in the shared service
  layer (touches every other call site, higher risk for a one-endpoint problem).
- Bucket/RLS provisioning: wrote a one-off script
  (`backend/scratch_create_statements_bucket.py`), ran it once against the DB, then
  deleted it — same "not tracked by Alembic, ad hoc SQL" approach as the `avatars`
  bucket (see docs/DECISIONS.md). The script itself is gone; if the bucket/policy ever
  need to be recreated, the SQL is preserved in the DECISIONS.md entry and in this
  file's git history for `scratch_create_statements_bucket.py`.
- Attempted live browser verification (sign up a throwaway test user, click through
  upload/list/delete) using the Chrome extension. `tabs_context_mcp` timed out 3
  times in a row ("Chrome extension is connected but the page may be loading,
  unresponsive, or waiting on a permission prompt"). Stopped after 3 attempts per the
  "avoid rabbit holes" guidance rather than continuing to retry blind.
- The dev backend on port 8000 became stuck (orphaned process from an earlier session
  task, unkillable via `Stop-Process`/`taskkill` from any tool tried, with or without
  sandbox restrictions lifted) and stopped picking up code changes, including the new
  `/view` route. Worked around by running a second backend instance on port 8001 and
  pointing `frontend/.env.local`'s `NEXT_PUBLIC_API_URL` at it instead of fighting
  process cleanup further. **The repo's dev default is still port 8000** — this 8001
  redirect is local-machine state in `.env.local` (gitignored), not a code change, so
  it doesn't affect other environments. Revert `.env.local` to `:8000` once that
  original process is confirmed gone (e.g. after a machine restart).
- User reported the "View" button opened a new tab that redirected but always landed
  on `about:blank` even though the API response had the correct signed URL. Root
  cause: `window.open("", "_blank", "noopener,noreferrer")` returns `null` when either
  the `noopener` or `noreferrer` flag is set (both strip the window reference), so the
  later `viewerTab.location.href = data.url` assignment never ran. Fixed by dropping
  those flags from `window.open` (we control the URL we navigate to — it's a
  same-request Supabase signed URL, not user-controlled input) and instead nulling
  `viewerTab.opener = null` right after getting the handle, which gives the same
  reverse-tabnabbing protection without losing the ability to redirect the tab.

## What worked

- **Backend**: `backend/app/models/statement.py` (`Statement`, table `statements`,
  migration `684dfcb36717`) · `backend/app/schemas/statement.py` (`StatementRead`) ·
  `backend/app/services/storage.py` (added `upload_statement`/`delete_statement`/
  `get_statement_view_url`, `STATEMENT_BUCKET`/`MAX_STATEMENT_BYTES`/
  `ALLOWED_STATEMENT_TYPES`) · `backend/app/api/statements.py` (`GET/POST
  /api/statements`, `GET /api/statements/{id}/view`, `DELETE /api/statements/{id}`,
  shared `_get_owned_statement` ownership-check helper) · registered in
  `backend/app/main.py`.
- Private Supabase Storage bucket `statements` (`public=false`, unlike `avatars`) with
  RLS policy `statements_owner_all` (`for all`, folder-scoped to `auth.uid()`).
- **Frontend**: `frontend/src/app/statements/page.tsx` ·
  `frontend/src/components/statements-list.tsx` (View button opens a blank tab
  synchronously on click, then redirects it once the signed URL resolves, to avoid
  popup blockers) · `frontend/src/constants/endpoints/statements.endpoints.ts` ·
  navbar link added in `frontend/src/components/navbar.tsx`.
- Full rationale in docs/DECISIONS.md's 2026-08-17 entry; request/response path in
  docs/FLOW.md's "Statement upload" section.

## Verification

- `backend`: `pytest -q` → 24 passed (13 pre-existing + 11 new across
  `tests/test_statements.py` and additions to `tests/test_storage.py`). Covers:
  auth-required on all four routes, upload creates a row, list returns the caller's
  statements, view rejects another user's statement (404) and returns the signed URL
  for the caller's own, delete rejects another user's statement (404) and removes the
  caller's own, and `upload_statement`'s content-type/size validation.
- `frontend`: `npx tsc --noEmit` clean; `npx eslint` clean on the new/changed files.
- **Live browser click-through**: confirmed by the user directly (not via the Chrome
  extension, which stayed unresponsive) — upload, list, view (after the `window.open`
  fix above), and the rest of the flow work against the port-8001 backend instance.

Nothing left to resume here. If parsing statements into transactions becomes the next
feature, start a new file in this directory rather than reopening this one.
