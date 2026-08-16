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

## Not yet wired

- `worker/` (Celery) has no task producers yet — nothing in the frontend or backend
  enqueues a job. Document the flow here once the first task is added.
- `shared/` has no code yet — document here once backend and worker share a type.
