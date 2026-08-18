# Flow

How execution actually travels between files, functions, and modules for each major
path. Update the relevant section whenever you touch a file on that path — bugs live in
the gaps between files, so this only earns its keep if it stays accurate.

## Auth (login / signup / logout / password reset)

1. Browser hits a page under `frontend/src/app/{login,signup,forgot-password,reset-password}/`.
2. Form submits to that route's Server Action in the sibling `actions.ts`
   (e.g. `frontend/src/app/login/actions.ts`).
3. Action calls the Supabase client from `frontend/src/lib/supabase/server.ts`.
4. `frontend/src/proxy.ts` + `frontend/src/lib/supabase/middleware.ts` run on every
   request to refresh/validate the Supabase session cookie and gate protected routes.
5. Email-based flows (confirm, callback) land on `frontend/src/app/auth/callback/route.ts`
   or `frontend/src/app/auth/confirm/route.ts`, which exchange the code/token with
   Supabase and redirect into the app.

## Profile read/write (settings page)

1. `frontend/src/app/settings/page.tsx` renders `components/profile-form.tsx`.
2. The form calls `hooks/use-api-request.ts`, which goes through
   `services/app.service.ts` to hit the FastAPI backend at the URL/paths defined in
   `constants/endpoints/settings.endpoints.ts`.
3. Request carries the Supabase JWT (from the client-side Supabase session); FastAPI
   verifies it in `backend/app/core/security.py` before the route handler runs.
4. `backend/app/api/profile.py` (`GET/PUT /api/profile`) reads/writes through the
   `User` SQLAlchemy model in `backend/app/models/user.py` (maps to the `users` table)
   (schema validated by `backend/app/schemas/profile.py`) against Supabase Postgres via
   `backend/app/core/db.py`.
5. CORS is configured in `backend/app/main.py` to allow the frontend origin.

## Profile image upload (settings page)

1. `components/profile-form.tsx`'s avatar button opens a hidden file input; on change,
   files over 5MB are downscaled (max 1024px long edge) and re-encoded as JPEG in
   `lib/compress-image.ts` (canvas-based, quality stepped down until it fits) before
   upload — files already under 5MB are sent as-is. The result POSTs as `FormData` to
   `settingsEndpoints.profileImage()` via `use-api-request.ts` (which already skips the
   JSON `Content-Type` header for `FormData` bodies, so the browser sets the multipart
   boundary).
2. `backend/app/api/profile.py`'s `upload_profile_image` reads the file, validates it
   (JPEG/PNG/WebP, 5MB max) in `backend/app/services/storage.py`, then uploads it to the
   Supabase Storage `avatars` bucket using the same user JWT that authenticated the
   request — Storage RLS (policy `avatars_owner_write`) restricts writes to the caller's
   own `{user_id}/` folder.
3. The returned public URL (cache-busted with `?v=<timestamp>`) is written to
   `users.profile_image` and the updated `ProfileRead` is returned, so the frontend
   updates the avatar immediately.

## Statement upload (statements page)

1. `frontend/src/app/statements/page.tsx` renders `components/statements-list.tsx`,
   reachable via the "Statements" link in `components/navbar.tsx`.
2. On mount, the component GETs `settingsEndpoints`-style
   `constants/endpoints/statements.endpoints.ts` → `/api/statements` through
   `hooks/use-api-request.ts` to list the signed-in user's statements.
3. Choosing a file (PDF/CSV, ≤20MB, checked client-side first) POSTs it as `FormData`
   to the same `/api/statements` path.
4. `backend/app/api/statements.py`'s `upload_statement_file` reads the file and calls
   `upload_statement` in `backend/app/services/storage.py`, which validates
   type/size server-side and uploads to the private Supabase Storage `statements`
   bucket under `{user_id}/{statement_id}.{ext}`, using the caller's own JWT — Storage
   RLS (`statements_owner_all`) restricts access to the caller's own folder.
5. A `Statement` row (`backend/app/models/statement.py`) is written via SQLAlchemy
   with `status="uploaded"`, and the `StatementRead` schema (no `storage_path` field)
   is returned so the frontend can show the new entry immediately.
6. Clicking "View" GETs `/api/statements/{id}/view`, which checks ownership (shared
   `_get_owned_statement` helper) and calls `get_statement_view_url` in `storage.py` to
   mint a short-lived (120s) Supabase Storage signed URL — the bucket is private, so
   there's no standing public URL to hand back. The frontend opens a blank tab
   synchronously on click (to dodge popup blockers), then redirects it to the signed
   URL once the response arrives.
7. Removing a statement DELETEs `/api/statements/{id}`, which checks the row belongs to
   the caller (same `_get_owned_statement` helper), deletes the Storage object via
   `delete_statement`, then deletes the row.

## Not yet wired

- Statement parsing: uploaded files are stored as-is; nothing reads their contents into
  transactions yet. `Statement.status` stays `"uploaded"` forever until that's built.

- `worker/` (Celery) has no task producers yet — nothing in the frontend or backend
  enqueues a job. Document the flow here once the first task is added.
- `shared/` has no code yet — document here once backend and worker share a type.
