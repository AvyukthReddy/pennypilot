# Decisions

Append-only log of meaningful decisions and the reasoning behind them. Code shows what
changed; this shows why. New entries go at the top. Don't edit or delete past entries
when a decision is later reversed — add a new entry that supersedes it and link back.

## 2026-08-26, Transactions list gets filters, sorting, and page-based pagination

`GET /api/transactions` (`backend/app/api/transactions.py`) gained `document_name`
(icontains against `Statement.filename`, joined in only when the filter is present),
`type` (`credit`/`debit`, mapped to `amount > 0`/`amount < 0` — the extraction pipeline
already stores debit negative/credit positive, see `worker/worker/transaction_schema.py`),
`start_date`/`end_date` (inclusive range on `transaction_date`), and `sort_by`
(`transaction_date`/`amount`/`description`/`created_at`) + `sort_order` (`asc`/`desc`,
`transaction_date desc` stays the default). `TransactionListRead` switched from
`limit`/`offset` to `page`/`page_size`/`total_pages` (`total_pages = ceil(total /
page_size)`, `0` when there are no results) — a breaking response-shape change, but
nothing outside this codebase consumed the old shape yet.

**Why page-based instead of keeping offset-based "load more":** the ask was explicit
UI pagination (page numbers / Previous-Next), which reads far more naturally off
`page`/`total_pages` than off raw `offset`. `frontend/src/components/transactions/
transactions-list.tsx` (the standalone `/transactions` page) now renders filter inputs
(document name, type, from/to date), a sort-by dropdown + direction toggle, and
Previous/Next controls with a "Page X of Y" label instead of the old accumulate-in-place
"Load more" button — changing any filter/sort resets to page 1. The two other
`transactionsEndpoints.list` callers (`components/dashboard/recent-activity.tsx`,
`components/statements/analysis/transactions-view.tsx`) don't need the new filters —
they just moved from `limit` to `page: 1, pageSize: N`.

**How to apply**: any future transaction-list consumer should read `page`/`page_size`/
`total_pages`, not `limit`/`offset`. If another entity ever needs the same list-with-
filters shape, `document_name`'s join-only-when-needed pattern (join added to both the
`select` and the `count` query only if that filter is actually set) is the template —
avoids paying a join cost when nobody asked to filter by it.

The document-name filter itself is a multi-select combobox
(`components/transactions/document-name-filter.tsx`), not free text: it fetches the
caller's statements via the existing `GET /api/statements` (already returns
`filename`, so no new endpoint), dedupes/sorts the filenames, and lets typing narrow
a dropdown of not-yet-selected filenames — but a filename is only added (as a
removable chip) when its option is actually clicked, and multiple can be picked
before closing the dropdown. **Why**: the ask was explicitly that users pick from
real filenames rather than type arbitrary text, then that they be able to pick more
than one. Because selection is now exact-match-from-a-known-list rather than partial
text, `GET /api/transactions`'s `document_name` query param became repeatable
(`list[str] | None = Query(None)` in `backend/app/api/transactions.py`) and the
filter switched from `Statement.filename.ilike(...)` to `Statement.filename.in_(...)`
— exact match, not substring, since every value now comes from a real filename the
user clicked rather than typed text that might only partially match.

## 2026-08-25, Frontend folder-structure refactor (feature grouping, no functional change)

`frontend/src/components/` had grown to 20 flat files spanning 5 unrelated feature
domains (landing page, dashboard, settings, statements, transactions), several
duplications had crept in, and a few components (`statements-list.tsx` 314 lines,
`profile-form.tsx` 280 lines, `pipeline-progress.tsx` 201 lines) mixed fetch/upload/
polling logic with rendering in one file. This was a pure reorganization + light
extraction pass — no behavior or UI changes, no new dependencies.

**No `features/` tree.** At ~40 files, a `features/<name>/{components,hooks,api,types}`
layout would leave most subfolders holding 0-1 files. Instead, feature grouping was
added only inside `components/` (the one folder with an actual scale problem):
`components/{shared,landing,dashboard,settings,statements,transactions}/`, with
`components/statements/analysis/` nested under `statements/` to mirror the
`/statements/analysis` route. `hooks/`, `services/`, `constants/`, `lib/` stayed flat —
each was already small and single-purpose. `compress-image.ts`/`countries.ts` moved
from `lib/` into `components/settings/` since each had exactly one consumer
(`profile-form.tsx`); `lib/` now holds only genuinely cross-cutting code. No barrel/
index files were added — the codebase had zero before, and the one plausible candidate
(`components/statements/analysis/`, 11 files) has a single consumer whose explicit
imports document what that page composes.

Eight duplications were extracted rather than just relocated: `formatAmount`
(byte-identical in `recent-activity.tsx`/`transactions-list.tsx`) now calls
`lib/format-currency.ts`'s `formatSignedCurrency`; the view-in-new-tab logic shared by
`statement-view-button.tsx` and `statements-list.tsx`'s inline copy now lives in
`components/statements/use-signed-url-view.ts` — both call the same hook rather than
one delegating to the other's rendered component, since `statement-view-button.tsx`
never surfaced its fetch error and `statements-list.tsx` did, so collapsing them into
one shared component instance would have silently dropped that error message;
`NON_TERMINAL_STATUSES` is now `components/statements/statement-status.ts`; the
five-page auth-gate boilerplate (`createClient` + `getUser()` + `redirect("/login")`)
is now `lib/require-user.ts`'s `requireUser()`; the password length/match check
duplicated in `settings/actions.ts`/`reset-password/actions.ts` is now
`lib/validate-password.ts`'s `validatePasswordInput()` (each action kept its own
`redirect()` target, since those differ); the loading/error/empty triptych repeated
across ~13 components is now `components/shared/api-status-text.tsx`'s
`ErrorText`/`EmptyText` (deliberately small leaf components, not a generic
state-machine wrapper, since loading skeletons stayed bespoke per component); the
repeated form-input Tailwind class is now `constants/form.constants.ts`'s
`FORM_INPUT_CLASS`. `statements/analysis` and `transactions` pages also switched to the
`PageProps<"/route">` convention `login`/`signup`/`settings` already used, dropping
their hand-rolled `SearchParams` type.

Verified clean after every incremental step: `npx tsc --noEmit`, `npx eslint src/`,
`npm run build` (no test runner exists in this repo — none added).

## 2026-08-25, Live pipeline progress (GitHub-Actions-style stepper)

Before this, `Statement.status` only had coarse values (`uploaded`/`queued`/`processing`/
`ingested`/`failed`), and `worker/worker/tasks.py`'s `parse_statement` committed every
phase's output (document analysis, transaction regions, schema, verification, financial
validation, confidence) in one single commit at the very end, after everything had
already run in memory. So a statement stuck in `processing` for a while gave a user
zero visibility into what was actually happening, and the analysis page's "Text blocks"
link was gated on `status === "ingested"`, hiding it from view entirely.

New `Statement.processing_stage`/`processing_detail` (both nullable, migration
`cf872bc680da`) are committed progressively via a `_set_stage(session, stmt, stage,
detail=None)` helper called at the top of each phase's existing guard, before its
try/except, so a stage reads as "reached" even if the AI call inside it goes on to
fail. Seven stages (`ingesting`, `understanding`, `detecting_regions`,
`discovering_schema`, `extracting`, `validating`, `scoring_confidence`) map onto the
*actual* control flow rather than an artificial 1:1 "Phase N" numbering: `extracting`
covers the whole per-region extract-then-verify loop (with `processing_detail` set to
`"Region N of M"` per iteration), and `validating` covers both `validate_transactions`
and the conditional `attempt_recovery` sub-step, since recovery isn't a separately
visible phase in the existing UI either.

A guard that evaluates false simply never calls `_set_stage` for that phase, so the
next guard that passes is what the frontend sees next. This means a stepper can
"jump forward" over stages that never ran (e.g. if region detection itself fails, the
frontend will show `detecting_regions` then `scoring_confidence` with nothing in
between), rather than each stage being individually marked done/skipped/failed.
Accepted as a deliberate v1 simplification: every guard between two adjacent stages is
a cheap in-memory boolean check with no I/O in between, so this window is never
actually observable at a 30-second poll cadence. `processing_stage`/`processing_detail`
are never reset on success (harmless, the frontend hides the stepper once
`status === "ingested"`) and are left exactly where they were on failure, so a failed
run's last-reached stage plus `parse_error` together show where it died.

New `GET /api/statements/{id}/progress` (same ownership pattern as the currency
endpoint) returns `{statement_id, status, processing_stage, processing_detail,
parse_error}` cheaply, no JSONB blobs. `frontend/src/components/pipeline-progress.tsx`
polls it every 30 seconds (the same shared `POLL_INTERVAL_MS` the statements list
already used, now hoisted to `constants/app.constants.ts`) while `status` is
non-terminal, rendering a step list (checkmark done / spinner current / dim pending /
red X on the failed stage). `statements-list.tsx`'s "Text blocks" link now also shows
while `status === "processing"` (relabeled "View progress"), not only once `ingested`,
so a user can actually reach the page while a statement is still running.

## 2026-08-25, Statement currency (user override + consistent formatting)

Every amount on `/statements/analysis` was rendering as a bare number
(transaction rows even hardcoded a "$" regardless of the statement's
actual currency), and there was no way to correct a wrong or missing
AI-detected currency. New `Statement.currency` (`String(3)`, nullable,
migration `c9d0e1f2a3b4`) is a separate user override column, deliberately
not overwriting `document_analysis.currency` (the AI's own read of the
document): overwriting would lose the "what did the model actually see"
signal and complicate any future re-analysis.

`GET/PATCH /api/statements/{id}/currency` resolves one effective value:
override, then AI-detected, then a `"USD"` default, returning which of the
three it picked as `source` so the frontend can distinguish "you set this"
from "we guessed" from "nothing was known." `PATCH` with `{"currency":
null}` clears the override and reverts to auto-detect, rather than a
separate delete endpoint, since it's the same resolution logic either way.

Frontend: `lib/format-currency.ts` centralizes the amount-plus-unit
formatting (a symbol for common codes, `"<code> <amount>"` for the rest,
so the unit is never dropped) instead of leaving each view to format
independently. `components/currency-context.tsx`'s `CurrencyProvider`
fetches the effective currency once per page load and shares it via
context across every section that displays an amount, so an edit in one
place is immediately reflected everywhere instead of only the section that
made the change. The editor is a dropdown sourced from a fixed
`SUPPORTED_CURRENCIES` list, not a free-text field, so a save can never
persist a value that isn't a real currency code.

## 2026-08-24, Phase 10: confidence (deterministic composite score)

Phases 6-9 each produce their own diagnostic signal, but nothing combined
them into one answer to "how much should I trust this statement's
extracted transactions?" New `worker/worker/confidence.py`'s
`compute_confidence(...)`, a plain Python function, no AI call, matching
`financial_validation.py`'s shape (schema + function together, nothing to
inject), combines five equally-weighted (`0.2` each) components into one
score: **extraction** (fraction of detected regions successfully
extracted), **verification** (fraction of extracted regions whose *first*
Phase-7 verification passed clean, before any corrective retry; a
corrected region still counts as less clean than one that was right the
first time), **financial validation** (penalizes non-`balance_mismatch`
`FinancialValidationIssue`s), **balance reconciliation** (full credit if
reconciled with no recovery needed, partial credit, `0.8`, if reconciled
only after Phase 9's `recovery_attempts` kicked in, `0.0` if never
reconciled), and **structural consistency** (fraction of pages
`document_analysis` flagged as `"transactions"` that actually got a
detected region, the one component that catches a Phase-3 to Phase-4 gap
none of the other four would surface, since they all operate on regions
that *did* get detected). Equal weighting is a deliberate, transparent
default (not reverse-engineered from a target number), named constants,
trivially retunable.

**Missing/inapplicable data is neutral (`1.0`), not penalized.** No stated
balance means nothing to reconcile, matching this pipeline's philosophy
everywhere else. **Gated on the same condition as region detection**
(`document_analysis` exists and flagged a `"transactions"` section): a
scanned PDF or unclassified statement gets `confidence = null`, not a
misleadingly perfect score for having nothing to complain about. Zero
detected regions despite a flagged section isn't specially cased, it
naturally falls out as a `0.0` structural-consistency score with a warning.

**`status` (`validated` / `needs_review` / `unreliable`, thresholds `0.9`/
`0.7`) deliberately doesn't reuse `"failed"`**, which already means
something specific on `Statement.status` (pipeline *execution* state, not
data quality). Confidence is a read-only overlay, same as
`financial_validation`, and never touches `Statement.status` itself.

**The persisted shape doesn't duplicate `transactions` into the JSONB
blob.** The user's example JSON (`{status, transactions, confidence,
warnings}`) is the conceptual final answer, but this codebase already has
a `transactions` table + `GET /api/transactions` for that; duplicating
rows into `Statement.confidence` would be pure redundancy. Persisted as
`{score, status, warnings, breakdown}` (new `Statement.confidence` `JSONB`,
migration `b8c9d0e1f2a3`), exposed via a new
`GET /api/statements/{id}/confidence`, and shown as the **first** section
on `/statements/analysis` (`components/confidence-view.tsx`, a colored
status pill + score + warnings + breakdown), the headline verdict for the
statement, not just another item in the pipeline's sequential order.

## 2026-08-24 — Phase 9: recovery (targeted re-extraction on balance mismatch)

Phase 8 only reported a `balance_mismatch` — nothing acted on it. New
`worker/worker/recovery.py`'s `attempt_recovery(...)` re-extracts one region
at a time and re-validates after each, stopping as soon as the statement
reconciles, instead of leaving a known-bad result alone or reprocessing
everything. **Scoped to `balance_mismatch` specifically** — the other four
`FinancialValidationIssue` types already point at a specific transaction via
their own description, so there's nothing ambiguous to "determine the
reason" for; `balance_mismatch` ("the total is off by $X, but which row?")
is the one genuinely ambiguous case, and it's exactly the user's own worked
example (`Balance mismatch → Page 7 probably contains missing transaction →
Re-run Page 7 → ... → PASS`).

**Candidate ordering reuses a signal already collected, rather than
inventing a new heuristic**: regions with no successful Phase-7 verification
record (extraction failed outright, or verification flagged `valid=false`)
are tried first; cleanly-verified regions after, in page order. Each region
is tried at most once; recovery stops on the first re-extraction that makes
the statement reconcile — bounding the cost to "usually one extra AI call,
at most one per region," matching "much cheaper than reprocessing the
entire document."

**Only re-extracts, doesn't re-verify (Phase 7).** Matches the user's own
diagram exactly — no verify step shown between "Re-run Page 7" and
"Validate." Phase 8's `validate_transactions`, re-run after each candidate,
is the sole pass/fail signal.

**`TransactionExtractionService.extract` gained a third, independent
correction pathway**: `recovery_hint: str | None`, alongside the existing
`previous_attempt`/`verification_issues` pair from Phase 7. Doesn't require
`previous_attempt` — recovery must also work for a region whose *original*
extraction failed outright and therefore has no prior attempt to show the
model at all.

**New `worker/worker/recovery.py`, not inlined into `tasks.py`.** The
candidate-ordering/try/validate/stop-or-continue branching is substantial
enough to warrant its own file, tested in isolation (fake extraction service
+ a plain `validate` callback) rather than only reachable through the full
task-pipeline mocks in `test_tasks.py`. Its `extraction_service` parameter
is always passed explicitly from `tasks.py` (not left to its own internal
default) — the two live in different modules with separate imports of
`TransactionExtractionService`, so monkeypatching `tasks.py`'s reference
alone doesn't reach a default constructed inside `recovery.py` (caught by a
real `openai.RateLimitError` escaping in a test before this fix).

**`tasks.py`'s per-region loop now keys its results by page**
(`extraction_by_page`/`verification_by_page` dicts) instead of flattening
straight into a rows list — recovery needs to replace one region's
contribution and rebuild the row list, which isn't possible once everything
is already flattened. Row-building became a small local closure
(`_rows_from_extractions`), called once normally and again for each
recovery candidate via `recovery.py`'s `validate` callback.

**`FinancialValidation` gains `recovery_attempts: list[RecoveryAttempt]`**
(`page`, `succeeded`) for observability — empty when recovery wasn't
triggered. No new migration: a new key inside the existing
`Statement.financial_validation` JSONB blob, so the backend route reads it
with `.get("recovery_attempts", [])` to stay compatible with statements
ingested before this phase. Surfaced on `/statements/analysis` via a short
note in `financial-validation-view.tsx` ("Recovery: re-extracted page 7 —
resolved" or "Recovery attempted on pages 3, 7 — still unresolved").

## 2026-08-24 — Phase 8: deterministic financial validation

Phases 6-7 extract and AI-verify transactions, but nothing checks the
*numbers* against each other — that's arithmetic, not something an LLM call
is needed for. New `worker/worker/financial_validation.py`'s
`validate_transactions(document_analysis, transactions) ->
FinancialValidation` is a plain Python function (no `AIProvider`, no
schema/service-file split like every other phase — there's nothing to
inject or mock) that runs once per statement over the *final* transaction
list, after the per-region extract/verify/correct loop completes (duplicate
detection and balance reconciliation are inherently statement-wide, not
per-region).

Checks: `post_date < transaction_date` or a `transaction_date.year` outside
a generous static `[1990, 2100]` (deliberately not compared against
`date.today()`, to keep the validator fully deterministic and
time-mock-free); `transaction_date` outside the statement period (only when
known); a zero amount or more than 2 decimal places (`TransactionRow.amount`
is `Numeric(12,2)` and would otherwise silently round/truncate on insert);
duplicate `(transaction_date, description, amount)` tuples; and — when the
statement states a beginning/ending balance — `beginning_balance + sum(all
signed amounts) == ending_balance` within a $0.01 tolerance (amounts are
already signed per Phase 6's convention, so this is exactly `beginning + net
== ending`, no separate credit/debit summing needed).

**Nothing extracted beginning/ending balance before this.** `DocumentAnalysis`
(Phase 3, `worker/worker/document_analysis.py`) gains
`beginning_balance`/`ending_balance: Decimal | None` — a natural, low-risk
extension of the same document-level-facts extraction that already pulls
`currency`/`statement_start`/`statement_end` from the same account-summary
text, rather than a new AI phase. `document_understanding.py`'s prompt gets
one added sentence asking for them when visible.

**Purely diagnostic, matching the user's own framing** ("now you know
extraction is wrong," not "now go fix it") — doesn't gate persistence,
doesn't trigger re-extraction, doesn't touch `status`. Skipped entirely when
there are no transactions to check. Wrapped in its own try/except in
`tasks.py` for defensive consistency with the rest of the pipeline, though a
pure function raising is very unlikely.

**Persisted as `Statement.financial_validation`** (nullable `JSONB`,
migration `a7b8c9d0e1f2`) — issues carry `type` + free-text `description`
only, no `page` (unlike `VerificationIssue`), since a duplicate or balance
mismatch isn't naturally one-page-scoped. Exposed via a new
`GET /api/statements/{id}/financial-validation` and a new section on
`/statements/analysis`; the existing document-analysis summary card also
now shows beginning/ending balance when present.

## 2026-08-24 — Phase 7: transaction verification (self-correcting extraction)

Phase 6 extracted every region's transactions and persisted them immediately
— nothing checked the extraction against the region it came from. Phase 7
adds a second AI pass per region: `worker/worker/transaction_verification.py`'s
`TransactionVerificationService.verify(document, region, extraction) ->
TransactionVerification` is given the same region content extraction saw
(text blocks + optional image, via `_regions.py`'s new `_region_content`,
factored out of `transaction_extraction.py`'s old `_render_region`) plus the
extraction's own JSON, and checks for six things: missing transactions,
duplicates, wrong dates, wrong amounts, wrong debit/credit signs, and
multi-line rows that were split or merged. New closed schema
(`worker/worker/verification_issues.py`): `VerificationIssue` (`type` — a
`Literal` of those six categories plus `other` as a catch-all — `page`,
`description`) and `TransactionVerification` (`valid: bool`, `issues:
list[VerificationIssue]`).

**When invalid, extraction is retried once with the issues as correction
feedback — the retry's output is trusted and persisted regardless of
whether it's still flagged (no re-verification loop).** This was an
explicit scoping choice (over "persist anyway, just flag" or "drop the
region entirely") — self-correction was worth the extra AI call per flagged
region over either silently keeping known-bad data or discarding
otherwise-good data over one issue.
`TransactionExtractionService.extract` gained two optional keyword-only
params, `previous_attempt`/`verification_issues`; when both are given, the
prior JSON answer and the issues (plus a "fix these" instruction) are
appended to the message list before the existing self-repair retry loop
runs — a different kind of retry (content correctness) than that loop's
(JSON validity), sharing the same call shape.

**Layered best-effort, matching the rest of this pipeline**: extraction
failing skips the region entirely (unchanged from Phase 6); verification
failing skips the retry and keeps the original extraction (no verdict, so
nothing to correct against); the corrective retry itself failing falls back
to the original extraction rather than losing the region's data. Nothing
here can fail the statement.

**Persisted as `Statement.transaction_verification`** (nullable `JSONB`,
migration `f6a7b8c9d0e1`) — the aggregate of every region's *first*
verification pass (`valid` = AND across regions, `issues` = concatenated,
each already carrying its own `page`). The retry outcome itself isn't
separately recorded — the report reflects what was initially found; the
correction is only visible via the `transactions` rows it produced.
Exposed via a new `GET /api/statements/{id}/transaction-verification`
(`backend/app/api/statements.py`, same ownership pattern as
`/transaction-schema`) and a new section on `/statements/analysis`
(`frontend/src/components/transaction-verification-view.tsx`), consistent
with every other phase's debug/observability surface in this pipeline.

## 2026-08-24 — Phase 6 follow-up: multimodal (image + text) input for region detection and extraction

Every AI service up to this point read purely from `page.text_blocks` —
coordinate-tagged text, no visual signal. `Page` (`worker/worker/document.py`)
gains `image: bytes | None` (a rendered PNG of the whole page, `None` if
rendering failed for that page) — `worker/worker/pdf_analysis.py`'s
`analyze_pdf` renders it via `pdfplumber`'s own `page.to_image(resolution=
PAGE_IMAGE_RESOLUTION).original` (100 DPI; Pillow/pypdfium2 were already
pdfplumber's own transitive deps, now also declared directly since
`worker/worker/_regions.py` imports `PIL.Image` itself). Rendering is
best-effort per page (try/except, logged, `image=None` on failure) — matches
the existing "a bonus-input problem, not core-ingestion" philosophy, doesn't
touch the "corrupt PDF ⇒ fail ingestion" path.

**Only wired into region detection (Phase 4) and extraction (Phase 6)** —
confirmed with the user as the two steps where seeing the actual layout most
plausibly helps (drawing a bounding box; reading exact row values off a table
whose text extraction might garble alignment/merged cells). Classification
(Phase 3) and column-mapping (Phase 5) stay text-only — more
structural/semantic, an image mainly adds payload cost there.

**`AIProvider.complete` needed zero changes** — it already forwards
`messages` straight to the OpenAI SDK, which already accepts `content` as
either a string or a list of parts (text + `image_url`). New
`worker/worker/_multimodal.py` (`text_part`/`image_part`) builds those parts;
new `_image_for_region` in `worker/worker/_regions.py` (alongside the
existing `_blocks_in_region`) crops `page.image` to a region's pixel bbox,
converting PDF points → pixels via `PAGE_IMAGE_RESOLUTION`.

`TransactionRegionDetectionService` now sends **one user message per
candidate page** (text blocks + that page's image, when available) instead
of one combined text blob — still one LLM call per document, just multiple
per-page messages within it, so an image stays unambiguously attached to its
own page. `TransactionExtractionService` sends the region **cropped** to its
own bounding box, matching what the text side already shows.

**Not persisted.** `Statement.pages` JSONB already backs the
`/statements/analysis` debug viewer — embedding a base64 PNG per page there
would bloat the DB row and every read of it for no reader. `image` is
stripped from the dict before `tasks.py` assigns `stmt.pages`; it lives only
in-memory for the duration of the Celery task. No backend/frontend changes.

**`Document.data` (raw PDF bytes) stays as-is** — explicitly out of scope
this pass; a `Document{metadata, pages}` restructuring was floated but
deferred, not requested yet.

**Sets up (doesn't build) the eventual OCR path.** The architectural
principle for when OCR gets built: it should produce the same `Page` shape
(`text`, `text_blocks`, `image`) as `analyze_pdf` does today, so downstream
AI services stay origin-agnostic between digital and scanned PDFs. `Page.image`
existing now means OCR will just be a second populator of an already-defined
field, not a new concept. `needs_ocr` itself is unchanged.

## 2026-08-24 — Phase 6: transaction extraction (real transaction-line parser)

Closes the loop Phases 3-5 set up: Phase 3 flags which pages hold a
`"transactions"` section, Phase 4 narrows each to an exact bounding region,
Phase 5 discovers which column in that region means which field. Phase 6
actually reads the rows. New `worker/worker/extracted_transactions.py`:
`ExtractedTransaction` (`transaction_date`, `post_date`, `description`,
`amount`, `currency` — exactly `Transaction`'s own columns, no `category`, no
extras) and `TransactionExtraction` (`transactions: list[...]`).

**One AI call per detected region, not one per document** — the first phase to
break from Phases 4/5's "batch everything into one call" pattern, per the
user's explicit spec: each flagged page's region is extracted independently
(`Page 2 region → AI call → transactions 1-42`, `Page 3 region → AI call →
transactions 43-91`, ...). New `worker/worker/transaction_extraction.py`'s
`TransactionExtractionService.extract(document, region, transaction_fields) ->
TransactionExtraction` takes one `TransactionRegion` at a time, plus the Phase
5 `TransactionFields` mapping for the whole document — the model is told which
column means what instead of re-deriving it per page. Same `AIProvider`,
closed-schema + one self-repair retry, and "schema describes the answer's
shape, it's not the answer" prompt wording as every other AI service in this
pipeline.

**`_blocks_in_region` moved out of `transaction_schema_discovery.py` into new
`worker/worker/_regions.py`** (mirrors the `_ai_json.py` shared-helper
convention) — Phase 6 needs the identical center-point crop per region, so a
second copy would just be duplication. Behavior unchanged; only the import
site moved.

**Per-region try/except in `tasks.py`, not one around the whole loop.** One
page's extraction failing after retries (bad JSON, network blip) must not
discard transactions already extracted from other pages — this is the first
phase operating over a *list* of regions rather than one document-level
answer, so the granularity of "best-effort" moved from per-document to
per-region.

**Currency falls back to `document_analysis.currency`** when a row's own
`currency` comes back `null` — the document-level currency Phase 3 already
classified is a reasonable default for a statement where every transaction
shares one currency.

**Guarded on `transaction_schema` being present** (need the column mapping to
extract meaningfully) — inherits the "no regions" skip for free, since
`transaction_schema` is itself only ever set when `transaction_regions` is
non-empty.

**No new backend or frontend work.** `GET /api/transactions`
(`backend/app/api/transactions.py`) already filters by `statement_id` and
paginates; `frontend/src/app/transactions/` already renders whatever's in the
table. `TransactionRow` (`worker/worker/models.py`) already has every field
this phase needs — this is the first phase to actually `session.add_all(...)`
rows into it rather than just mutating the `Statement` row.

**Deliberately out of scope**: no dedup/idempotency guard on reprocessing a
statement (re-running `parse_statement` on an already-ingested statement will
insert duplicate transaction rows — same "reprocessing overwrites" model the
JSONB columns already have, just not yet extended to a normal table);
`raw_row` stays unpopulated (not part of the user's strict schema);
`Statement.status` stays `"ingested"`, no new `"parsed"` status introduced;
`INGESTION_VERSION` stays unchanged (wasn't bumped for Phases 3-5 either).

`worker/worker/tasks.py`'s `# TODO(phase 6)` marker is gone — this was the
seam it named.

## 2026-08-23 — Phase 5: transaction schema discovery

Phase 4's `TransactionRegionDetection` already narrows each transaction-flagged
page down to an exact bounding region. Phase 5 answers the next question before
any real line-item extraction: **what does a transaction look like in *this*
document?** Different banks lay out wildly different tables (`Date | Description
| Amount` vs. `Transaction Date | Posting Date | Description | Debit | Credit |
Balance` vs. something never seen before) — instead of `if bank == "Chase":
...`, new `worker/worker/transaction_schema.py`'s `TransactionSchemaDiscovery`
asks the model to map whatever columns this document actually has onto
`Transaction`'s fixed fields (`backend/app/models/transaction.py`):
`transaction_date`, `post_date`, `description`, `amount`, `currency`.

**`amount` is `list[FieldSource]`, not a single one.** A table with separate
Debit/Credit columns can't source one target field from one column — it needs
two `FieldSource` entries, each tagged `semantics: "debit"`/`"credit"`, so a
later real parser can combine them (subtract/sign) instead of losing a column.
`transaction_date`/`description` stay single required fields; `post_date`/
`currency` are optional singles, matching `Transaction`'s own nullability.

**`source` is a positional label (`"column_N"`) the model assigns itself**, left
to right from the coordinate-tagged text blocks it's shown — same approach as
Phase 4 (reason over `[x, y, width, height]` blocks directly, no pre-computed
column-clustering heuristic on our side).

**Feeds text blocks cropped to the *detected region*, not the whole flagged
page** — new `_blocks_in_region` helper
(`worker/worker/transaction_schema_discovery.py`) filters a page's
`text_blocks` to those whose center point falls inside its Phase-4-detected
region box (center-point test, not strict containment, so a block that
slightly straddles the boundary isn't dropped). This is the actual payoff of
Phase 4's narrowing — Phase 4 itself still fed whole-page blocks since it
didn't know the region yet.

**Reuses Phase 3/4's pattern wholesale** — same `AIProvider`, same
closed-schema + self-repair-retry (`worker/worker/_ai_json.py`), same
best-effort/non-fatal handling (a failure leaves `transaction_schema` as
`null`, never fails the statement), same "schema describes the answer's shape,
it's not the answer" prompt clarification from the previous commit. Skipped
entirely when `transaction_regions` is empty/`null` — inherits the skip chain
from Phases 3+4 for free. Persisted as `Statement.transaction_schema`
(nullable `JSONB`, migration `e5f6a7b8c9d0`), exposed via a new
`GET /api/statements/{id}/transaction-schema`, and shown as a fourth section
on `/statements/analysis`.

`worker/worker/tasks.py`'s TODO marker moved from `phase 5` to `phase 6` — the
still-unbuilt transaction-line parser now has `document`, `document_analysis`,
`transaction_regions`, *and* `transaction_schema` to work with.

## 2026-08-19 — Phase 4: transaction region detection

Phase 3's `DocumentAnalysis.sections` already says *which pages* hold what (e.g.
`{"type": "transactions", "pages": [2, 3, 4]}`). Phase 4 narrows further: for just
those flagged pages, find the exact bounding box that holds the transaction table
itself — excluding headers, footers, logos, and margins — before any real line-item
extraction has to touch the page. New `worker/worker/transaction_regions.py`:
`TransactionRegion` (`page: int`, `region: tuple[float, float, float, float]` —
`[x0, y0, x1, y1]` in the same points-from-top-left space `Page`/`TextBlock`
already use) and `TransactionRegionDetection` (`transaction_regions: list[...]`) —
matches the user's spec exactly, closed schema, no arbitrary JSON.

**Reuses Phase 3's pattern wholesale, no new provider work.** New
`worker/worker/transaction_region_detection.py`'s
`TransactionRegionDetectionService.detect(document, document_analysis) ->
TransactionRegionDetection` takes an `AIProvider` (same config-driven
`AI_BASE_URL`/`MODEL_API_KEY`/`AI_MODEL`, no code change to swap models), same
prompt-JSON-plus-one-self-repair-retry approach, same best-effort/non-fatal
philosophy (missing key, network error, or invalid JSON just leaves
`transaction_regions` as `null`, never fails the statement). The markdown-fence
stripper both services need was pulled out to `worker/worker/_ai_json.py` rather
than duplicated a second time.

**Depends on Phase 3's output, doesn't redo it.** Only pages already flagged
`"transactions"` are examined — `_candidate_pages` filters `document.pages` down
to that set before building the prompt, which is the actual "expensive extraction
reduction" the user described: Phase 3 narrows pages, Phase 4 narrows further
within them. Detection is skipped entirely (no LLM call made) when there's no
`document_analysis` at all or no `"transactions"` section in it — nothing to
narrow.

**One LLM call per document, not per page**, and **feeds `text_blocks` with
coordinates, not just `text`** — unlike Phase 3 (pure classification, layout
doesn't matter), naming a bounding region is inherently coordinate-based, so the
model needs to see where things sit on the flagged pages, batched into a single
prompt/response covering all of them at once.

**Persisted as `Statement.transaction_regions`** (nullable `JSONB`, migration
`d4e5f6a7b8c9`), same pattern as `document_analysis`/`pages` — exposed via a new
`GET /api/statements/{id}/transaction-regions` (same ownership check as `/pages`/
`/analysis`) and shown as a compact page/region table on the existing
`/statements/analysis` page, below the document-analysis summary.

`worker/worker/tasks.py`'s TODO marker moved from `phase 4` to `phase 5` — the
still-unbuilt transaction-line parser is the next (and now better-scoped) seam:
it gets `document`, `document_analysis`, *and* `transaction_regions` to work with.

## 2026-08-19 — Phase 3: document understanding (AIProvider abstraction, Qwen2.5-VL-7B via Hugging Face by default, supersedes pydantic removal)

Answers "what is this document?" — not a transaction extraction. New
`worker/worker/document_understanding.py`'s `DocumentUnderstandingService.analyze
(document) -> DocumentAnalysis` feeds each page's already-extracted `text` (from
Phase 2, not `text_blocks`/coordinates — classification doesn't need layout) to an
LLM and gets back a **closed Pydantic schema**
(`worker/worker/document_analysis.py`): `document_type` (a `Literal`), institution,
account type/last4, currency, statement period, and `sections` (page ranges by
content type, `type` also a closed `Literal`) — never arbitrary JSON.

**No hard-coded model or provider.** `worker/worker/ai_provider.py`'s `AIProvider`
wraps any OpenAI-compatible chat completions endpoint — `base_url`/`api_key`/
`model` all come from `AIProviderConfig`, built from three env vars
(`AI_BASE_URL`/`MODEL_API_KEY`/`AI_MODEL`, `worker.config.default_ai_provider_config`).
`DocumentUnderstandingService` takes an `AIProvider` (constructor-injected,
defaulting to the configured one) rather than building a model client itself —
benchmarking or swapping models/providers is an env change, never a code change to
`document_understanding.py`'s extraction pipeline. The `openai` Python package is
used purely as the OpenAI-compatible HTTP client; no OpenAI account involved.

**Default: Qwen2.5-VL-7B-Instruct via Hugging Face's Inference Providers router**
(`AI_BASE_URL=https://router.huggingface.co/v1`, `AI_MODEL=Qwen/Qwen2.5-VL-7B-
Instruct:featherless-ai`, needs `MODEL_API_KEY` — a free Hugging Face access token
with "Make calls to Inference Providers" permission) — the user's explicit choice,
prioritizing $0 inference cost. OpenRouter was tried first but has no free-tier
Qwen model at all (confirmed against its live `/api/v1/models` catalog — the 7B VL
variant isn't even listed anymore, and no other Qwen model there has a `:free`
tier); Hugging Face's own router does serve this exact model, through the
`featherless-ai` provider (confirmed via
`https://huggingface.co/api/models/Qwen/Qwen2.5-VL-7B-Instruct?expand[]=inferenceProviderMapping`).
The `:featherless-ai` suffix pins that provider explicitly rather than HF's default
`:fastest` auto-selection. This is only the _default_ — any of the three env vars
can be overridden independently to point at a different provider/model entirely.

**Prompt-based JSON + Pydantic validation with one self-repair retry**, not native
structured-output/tool-calling. A free 7B model behind a routing layer isn't
guaranteed to honor `response_format`/forced tool-use as reliably as a frontier
model. On invalid JSON (or a response wrapped in a ` ```json ` fence, which small
models commonly do despite instructions not to), the service re-prompts once with
the validation error and asks for a corrected response before raising
`DocumentUnderstandingError`.

**Best-effort, non-fatal.** By the time this runs, ingestion and Phase 2 analysis
have already succeeded — a classification failure (missing API key, network error,
model never returns valid JSON) must not flip `Statement.status` to `"failed"`; it
just leaves `document_analysis` as `null`, same philosophy as `needs_ocr` detection.
Skipped entirely (not even attempted) when `needs_ocr=true` or a PDF has no
extracted pages — feeding near-empty text would just produce garbage; understanding
a scanned statement waits for the eventual OCR/vision pass, still unbuilt.

**Persisted as `Statement.document_analysis`** (nullable `JSONB`, migration
`c3f4a5b6d7e8`), same pattern as `pages` — exposed via a new
`GET /api/statements/{id}/analysis` (not folded into `StatementRead`, same
reasoning as `/pages`) and shown as a summary card on the existing
`/statements/analysis` page, above the text-blocks viewer that page already had.

**Supersedes the 2026-08-18 entry that removed `pydantic` from `worker/`** (dropped
along with `pypdf`/`shared/` when parsing was rescoped to Phase 1, on the grounds
that nothing used it). This feature genuinely needs schema validation for LLM
output — the removal predates that need. `worker/worker/document_analysis.py`
defines its own copy of the schema rather than reviving a `shared/` dependency or
importing from `backend/`, same decoupling precedent as `worker/worker/models.py`
hand-mirroring the backend's SQLAlchemy models.

## 2026-08-19 — Fix empty-state flash: move `hasFetchedOnce` into `useApiRequest` as `hasSettled`

The `hasFetchedOnce` pattern each list component hand-rolled (`statements-list.tsx`,
`transactions-list.tsx`, `recent-activity.tsx`, `statement-pages-view.tsx`) was meant
to stop "No X found" from flashing before the first fetch resolves — but it still
flashed. Root cause: React Strict Mode double-invokes effects on mount in dev (by
design, to catch exactly this class of bug), which fires the data-fetch effect twice.
`services/app.service.ts`'s `getResponseAsync` aborts the first in-flight request once
the second one starts (same dedup key) — but `useApiRequest.run()`'s
`finally { setLoading(false) }` and each caller's `.then(() => setHasFetchedOnce(true))`
fired **unconditionally**, even for that now-superseded first call. Its `.then()` ran
with `data` still `undefined`, setting `hasFetchedOnce=true` while `statements`/
`transactions`/`pages` were still empty — showing the empty-state message before the
real (second) request had even resolved.

Fixed at the root: `useApiRequest` (`frontend/src/hooks/use-api-request.ts`) now tracks
a `latestCallId` ref, bumped on every `run()` call. A call only touches `loading`/
`error`/`status`/the new `hasSettled` state if it's still the latest call when it
finishes — a superseded call (any call that isn't currently the latest) returns
`undefined` without touching any of them. `hasSettled` replaces every component's local
`hasFetchedOnce`: true once a non-superseded call has settled (success or failure) at
least once. This is a general correctness fix, not dev-only — the same clobbering could
happen in production from any rapid re-fetch (fast filter changes, quick re-navigation),
Strict Mode's double-invoke just makes it reliably reproducible on every single page
load in dev.

## 2026-08-19 — Persist `Statement.pages` (supersedes "pages stay in-memory only")

The 2026-08-19 Phase 2 entry below originally kept `Document.pages` in-memory only,
reasoning nothing downstream consumed it yet. The user wanted to actually inspect
extraction quality against real statements, and asked for it to be visible in the UI
— a real consumer now exists (a person, checking the analysis worked), so that
reasoning no longer holds. `statements.pages` is now a nullable `JSONB` column
(migration `b2e3d4f5a6c7`), populated in `worker/worker/tasks.py` via
`[dataclasses.asdict(page) for page in pages]` right alongside `needs_ocr`/
`page_count`. CSVs get `pages=[]`, same as before.

Exposed via a new `GET /api/statements/{id}/pages` (`backend/app/api/statements.py`,
same ownership check as `/view`) — deliberately **not** folded into `StatementRead`
(used by the statements list), since a multi-page PDF's full text-block list is much
larger than the rest of that response and the list view has no use for it. Frontend:
`frontend/src/components/statement-pages-view.tsx`, reachable via a new "Text blocks"
link per statement row (shown only for `status === "ingested"` PDFs — CSVs have no
pages, and unfinished/failed statements have nothing to show), rendered at
`/statements/analysis?statement_id=...`. Each page is a collapsible `<details>`
section with page dimensions/counts as the summary and a table of `text_blocks`
(`x`/`y`/`width`/`height`/`text`) — first page open by default, rest collapsed, since
a real statement can run into hundreds of blocks across many pages.

`images` (bounding boxes) are persisted too, since they're already part of the `Page`
dataclass, but nothing in the UI surfaces them yet — no consumer for those specifically.

## 2026-08-19 — Phase 2: PDF document analysis (pdfplumber, in-memory Document IR, needs_ocr detection)

Phase 1 left `worker/worker/document.py`'s `Document` as a flat bytes blob — nothing
looked at what was actually on the page. Phase 2 fills that in: `worker/worker/
pdf_analysis.py`'s `analyze_pdf()` opens each PDF with **pdfplumber** and returns a
`list[Page]` (`worker/worker/document.py`) — per page, `width`/`height`, full `text`,
line-grouped `text_blocks` (via `extract_text_lines()`, which already returns
`x0`/`x1`/`top`/`bottom` per line — no hand-rolled word-clustering needed), and
`images` (bounding boxes only, from `page.images` — no pixel bytes extracted, nothing
consumes them yet). `pypdf` is retired; pdfplumber's own page count replaces
`count_pdf_pages`, so the worker carries one PDF library instead of two.

**pdfplumber over PyMuPDF**: PyMuPDF's `get_text("blocks")` is a closer one-line match
for the requested shape and is faster, but it's AGPL-licensed — for a hosted app that
serves users over a network, AGPL's copyleft trigger is a real legal question, not
one to default into silently. pdfplumber (MIT, via pdfminer.six) avoids that, and this
project's earlier — since-deleted — parser attempts already used it, so the extraction
patterns aren't new territory.

**Scanned-PDF detection, not OCR**: `is_scanned()` flags a PDF as `needs_ocr` when its
average extracted characters-per-page falls below a small threshold
(`SCANNED_TEXT_THRESHOLD` in `pdf_analysis.py`) — a cheap, good-enough signal that a
page has no real text layer. Actual OCR/vision is explicitly **not** built this pass;
the user's own framing was that OCR is an "eventually" step once both text and scanned
PDFs need to feed the same downstream `Document` shape. `needs_ocr` is the one new bit
persisted on `Statement` (migration `a1f2c3d4e5b6`, mirrored in `worker/worker/
models.py` per that file's hand-sync convention) — it's a real, useful signal now
(e.g. future UI: "this statement needs OCR, coming soon"), unlike full page/text-block
data, which has no consumer yet.

**`Document.pages` stays in-memory only** — not persisted as JSONB or any new table.
Same reasoning as Phase 1: nothing downstream reads it yet (no parser exists), so
there's nothing to gain from durability beyond what `needs_ocr`/`page_count` already
capture. Add persistence when a real consumer (Phase 3's parser, or a debugging UI)
actually needs to re-read page-level data without re-running analysis.

`INGESTION_VERSION` bumped `"1"` → `"2"` — the analysis logic materially changed, per
the constant's own existing convention (`worker/worker/tasks.py`'s TODO marker moved
from "phase 2" to "phase 3" accordingly).

## 2026-08-18 — Statement parsing scoped down to Phase 1: ingestion only, no parser yet

Two full parsing-pipeline implementations were built and then deleted in the same
session, neither ever committed. The user made a deliberate call to stop iterating on
parser heuristics bank-by-bank and instead scratch all of it, rebuilding from a clean,
explicitly-scoped Phase 1: document **ingestion** only, no parsing. All parsing code
(`worker/worker/parsing/` and its tests/fixtures) was deleted in full.

`worker.parse_statement` now does exactly this: download the file via a short-lived
Supabase signed URL passed as a task argument (never a service-role key — same
caller's-own-JWT trust model as everywhere else, see the avatar-upload entry below;
the worker holds zero standing Supabase credentials) — unchanged, never modified — →
for PDFs, count pages (`pypdf`) → build a `Document` dataclass
(`worker/worker/document.py`) bundling the bytes plus `file_hash`/`size_bytes`/
`page_count`/`parser_version` — the explicit handoff object a future parser will
consume — → persist `page_count`/`parser_version` on the `Statement` row → status
becomes `"ingested"`. `INGESTION_VERSION` is a bumped constant recording which version
of _this_ pipeline touched a document, so a later, smarter ingestion pass can identify
what needs redoing. Worker DB access (`worker/worker/models.py`) is a separate,
hand-mirrored SQLAlchemy mapping, not an import of `backend/app/models` — backend +
Alembic remain the sole schema authority, this trades a small hand-sync burden for
keeping the two services' dependency graphs fully decoupled.

`shared/`'s Poetry path dependency and the Docker repo-root build context that existed
solely to reach it were both reverted — nothing in the worker imports
`shared.schemas.transaction` anymore. `shared/shared/schemas/transaction.py` itself is
left in place (untouched, unused) as a plausible starting point for whatever contract
the next parser needs.

**Deliberately kept, not scratched**: the `transactions` table/model, the
`GET/POST /api/statements` and `GET /api/transactions` APIs, and the frontend
Transactions/statements-list UI. None of that is "a parser" — it's the sink a future
parser will populate. It currently just stays empty, which is honest, not broken.

**How to apply**: the next parsing pass is a clean slate — no obligation to preserve
any part of a prior implementation's module shapes.

## 2026-08-18 — Worker auto-loads root `.env`; `REDIS_URL` there is Docker-network-only

Discovered while trying to run the Celery worker locally (outside Docker) to verify
the parsing pipeline end-to-end: `.env`'s `REDIS_URL=redis://redis:6379/0` uses the
Docker Compose service hostname, which only resolves inside Docker's network —
confirmed via a direct `send_task` call from a local (non-Docker) backend process,
which failed with `getaddrinfo failed` for host `redis`. Every statement uploaded
locally since the parsing feature landed had been silently failing to enqueue (caught
by `upload_statement_file`'s `except Exception: pass`), leaving statements stuck at
`"uploaded"`.

Backend already avoids the analogous `DATABASE_URL` friction because pydantic-settings
loads the root `.env` directly — worker didn't have that, so after making
`DATABASE_URL` a hard-required env var (see the same day's earlier fix, prompted by a
different review comment about the module having a hardcoded fallback connection
string), running the worker locally required manually exporting both `DATABASE_URL`
_and_ `REDIS_URL` every session, which is exactly the kind of friction that gets
skipped and silently breaks things.

Fixed by having `worker/worker/config.py` call `python-dotenv`'s `load_dotenv()` on
the repo-root `.env` (file-path-relative, not cwd-relative, so it works regardless of
where `celery`/`pytest` is invoked from) with the library's default
non-overriding behavior — an already-set shell env var always wins. `REDIS_URL` is
centralized into `config.py` too (`celery_app.py` now imports it from there instead of
its own separate `os.environ.get`), keeping a `redis://localhost:6379/0` fallback
default since that's a reasonable default for genuinely local (no-Docker-at-all) use,
unlike `DATABASE_URL`, which has no sensible generic default.

**Net effect**: `DATABASE_URL` now just works locally with zero setup. `REDIS_URL`
still requires a manual `$env:REDIS_URL = "redis://localhost:6379/0"` override before
starting a local (non-Docker) backend or worker process — that part is inherent to
running some services in Docker and others on the host, not something env-loading can
paper over. Documented in `docs/HANDOVER.md`.

## 2026-08-18 — Enabled Postgres RLS on users/statements/transactions (Supabase Security Advisor finding)

Supabase's Security Advisor flagged `public.users`, `public.statements`,
`public.transactions`, and `public.alembic_version` as "RLS Disabled in Public" —
these tables were exposed via Supabase's auto-generated PostgREST API with no Row
Level Security, while the app's actual access control lived entirely in FastAPI
(JWT verification + `user_id`-scoped queries). Since the frontend ships a public
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, anyone could have called
`https://<project>.supabase.co/rest/v1/<table>` directly with that key and read/
written every user's rows, completely bypassing FastAPI's auth checks — RLS was the
only thing that could have stopped that, and it was off.

Fixed by enabling RLS and adding an `auth.uid() = user_id` owner policy on `users`
(policy compares against `user_id`, that table's actual PK column — not `id`),
`statements`, and `transactions` (mirrors the pattern already used for the `avatars`/
`statements` Storage buckets — `avatars_owner_write`, `statements_owner_all`). Ran as
a one-off script (`backend/scratch_enable_rls.py`, run once via the backend's
superuser-role `DATABASE_URL` which bypasses RLS, then deleted — same "ad hoc SQL for
Supabase-managed/security config, not tracked by Alembic" approach as the Storage
bucket policies). `alembic_version` just got RLS enabled with no policy, since it's
Alembic's internal migration-tracking table and has no legitimate reason to be
queried via the API at all — enabling RLS with zero policies blocks all PostgREST
access to it outright.

**Why this didn't break the backend**: FastAPI connects via a direct Postgres
connection using a role with RLS-bypass privileges (Supabase's `postgres` role), so
none of this affects backend queries — RLS only constrains access through
PostgREST/the Supabase client libraries using the anon/publishable key, which is
exactly the gap being closed.

**How to apply**: any new table holding per-user data must get RLS enabled + an
owner policy in the same migration/provisioning pass that creates it — don't let this
gap reopen for the next table.

## 2026-08-18 — Statement upload: exact-file dedup via SHA-256; added a `queued` status

`upload_statement_file` (`backend/app/api/statements.py`) now hashes each upload
(SHA-256) and rejects an exact repeat for the same user with `409` before any Storage/
DB write — cheap (reuses bytes already read into memory), prevents wasted storage from
re-uploading the identical file. Deliberately no fuzzy or content-level dedup, just
exact-file matching.

`Statement.status` also gained a `queued` value, inserted between `uploaded` and
`processing`. Before this, a failed Celery enqueue left `status="uploaded"`
permanently and indistinguishably from "just uploaded, about to be queued." Now
`queued` means the enqueue itself succeeded, so `uploaded` unambiguously means "stored,
but the background job was never successfully queued" (no automatic retry exists yet).

## 2026-08-17 — Statement upload: scoped to upload/list/delete only, private bucket (unlike avatars' public one)

`POST/GET/DELETE /api/statements` (`backend/app/api/statements.py`) store uploaded
bank/credit-card statements (PDF or CSV, 20MB max) in a new `statements` table
(`backend/app/models/statement.py`, migration `684dfcb36717`) and a new private
Supabase Storage bucket (`statements`, `public=false`), following the same
caller's-own-JWT + folder-scoped-RLS pattern as the `avatars` bucket
(`statements_owner_all` policy, `for all` rather than avatars' insert-only policy,
since statements also need delete). `upload_statement`/`delete_statement` were added to
the existing `backend/app/services/storage.py` rather than a new module — one file for
all Supabase Storage interactions was simpler than splitting per bucket at this size.
Parsing the uploaded file into transactions was deliberately **not** built in this
pass — `Statement.status` defaults to `"uploaded"` and exists specifically so a future
parsing pipeline (likely the still-unused Celery `worker/`) has somewhere to record
progress without a schema change.

**Why**: (1) Avatars are meant to be publicly displayable; bank statements are
sensitive financial documents, so the bucket is private and no public URL is ever
generated or stored — only the internal `storage_path`, which `StatementRead` does not
expose. (2) Scoping to upload/list/delete (no parsing) was a deliberate choice made
with the user up front, to keep this session's change small and defer the bigger
architectural decision (sync parse in FastAPI vs. async via the Celery worker, and what
`shared/` types that would need) to when it's actually needed.

**How to apply**: when parsing is built, add a `parsed_at`/error columns or a separate
`transactions` table rather than overloading `status` with parse-result data, and
revisit whether `worker/` should get its first real task then.

## 2026-08-15 — Profile image upload: backend-proxied to Supabase Storage, bucket/RLS created via direct SQL

`POST /api/profile/image` takes a multipart upload, validates it in
`backend/app/services/storage.py` (JPEG/PNG/WebP only, 5MB max), and forwards it to
Supabase Storage's REST API using the _caller's own JWT_ (added `token` to
`CurrentUser` in `backend/app/core/security.py` to make this possible) — not a
service-role key. The `avatars` bucket and its RLS policy
(`avatars_owner_write`, scoped to `(storage.foldername(name))[1] = auth.uid()::text`)
were created by running raw SQL against `storage.buckets`/`storage.objects` over the
same Postgres connection Alembic uses, not through the Supabase dashboard.

**Why**: (1) Proxying through FastAPI instead of uploading straight from the browser to
Supabase Storage keeps "all business logic through FastAPI" intact (see the Server
Actions/FastAPI split decision below) and lets us enforce file type/size server-side
before it ever reaches Storage. (2) Using the user's own JWT rather than a service-role
key means the backend never needs a new admin secret — Storage RLS does the same
per-user authorization Postgres RLS would. (3) `storage.buckets`/`storage.objects` are
just Postgres tables, and this project already has a working superuser-ish connection
to them (the Alembic session-pooler URL) — creating the bucket that way was faster than
setting up dashboard/Management-API access, and is reversible (`delete from
storage.buckets where id = 'avatars'` + `drop policy`). This is a one-time
infra-provisioning step, not part of the Alembic-tracked `public` schema history —
Supabase owns the `storage` schema, so it's deliberately not folded into a migration.

**How to apply**: any future bucket needs the same two things — a `storage.buckets` row
and an owner-scoped RLS policy on `storage.objects` — done directly via SQL against the
project's Postgres connection, then referenced from a backend service module the same
way `storage.py` does. Don't introduce a Supabase service-role key for this unless a
feature genuinely needs cross-user access Storage RLS can't express.

## 2026-08-15 — Renamed `profiles` table to `users`; kept `/api/profile` route and schema names as-is

Migration `f63aac5142d7` renames `public.profiles` to `public.users` and adds
`created_at`, `updated_at` (both `server_default=now()`, `updated_at` also has
`onupdate=func.now()` so ORM-driven updates bump it), and `profile_image`
(nullable `VARCHAR(500)`, no upload endpoint yet — just a column for a future image
URL). The SQLAlchemy model moved from `app/models/profile.py` (`Profile`) to
`app/models/user.py` (`User`) to match the table it maps to.

The API route (`/api/profile`), Pydantic schema names (`ProfileRead`/`ProfileUpdate`,
`app/schemas/profile.py`), and router file (`app/api/profile.py`) were deliberately
**not** renamed.

**Why**: "profile" is the settings-page feature/contract the frontend already depends
on; "users" is what the underlying table should be called now that it's gaining
account-level fields (timestamps, avatar) beyond pure profile data. Renaming the route
too would touch the frontend (`frontend/src/constants/endpoints/settings.endpoints.ts`)
for no functional gain and wasn't part of the request.

**How to apply**: if this table grows further into a general "account" concept, revisit
whether `/api/profile` should become `/api/account` or `/api/user` — but don't rename
routes speculatively; only when a concrete new feature forces the question.

## 2026-08-11 — API architecture split: Server Actions for auth only, FastAPI for everything else

Next.js Server Actions (`frontend/src/app/**/actions.ts`) are scoped to Supabase auth
flows only (login, signup, logout, password reset, email confirm). Every other piece of
business logic — profile, and anything that follows — lives in FastAPI (`backend/`) and
is called from the frontend through the shared API service layer
(`services/app.service.ts` + `hooks/use-api-request.ts`).

**Why**: keeps a single source of truth for business logic and data access (FastAPI +
SQLAlchemy/Alembic against Supabase Postgres), instead of splitting it across two
runtimes. Auth stays in Server Actions because Supabase's SSR auth helpers are built
around Next.js's cookie/session handling.

**How to apply**: when adding a new feature, default to a FastAPI endpoint, not a new
Server Action, unless it's literally an auth operation.

## 2026-08-11 — Migrated `profiles` table to Supabase Postgres via SQLAlchemy + Alembic

Introduced SQLAlchemy models and Alembic migrations (`backend/app/models/`,
`backend/app/core/db.py`) instead of hand-written SQL or relying on Supabase's
auto-generated REST API for the `profiles` table.

**Why**: gives FastAPI direct, typed, migration-tracked control over schema evolution as
more tables get added, rather than depending on Supabase's PostgREST layer for
everything.

**How to apply**: new tables follow the same pattern — SQLAlchemy model + Alembic
migration + Pydantic schema in `backend/app/schemas/`.
