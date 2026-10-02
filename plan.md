# Project: Multi-Tenant Job Scheduler-as-a-Service

> Working titles: "Cronos" / "ScheduleForge" / plain "Job Scheduler-as-a-Service"
> Locked in: Week 9, Sept 2026 (Phase 2 of the 6-month roadmap, Weeks 9–17)

## Overview

A multi-tenant backend service where other applications ("tenants") register scheduled
jobs via an API — "hit this webhook URL on this schedule" — and the system reliably
triggers them, tracks execution history, and handles failures gracefully. Conceptually
similar in spirit to services like AWS EventBridge Scheduler, Temporal, or cron-job.org,
scoped down to something buildable solo in ~11 hrs/week.

**Domain classification:** Primarily **backend / distributed systems**, with cloud as
the deployment target (not the core subject) and AI as a Phase 3 add-on layer — not a
FinOps/cloud-cost tool, which was deliberately ruled out due to overlap with employer's
product domain.

**One-line resume pitch:**
> Job Scheduler-as-a-Service — a multi-tenant, distributed cron/webhook scheduling
> platform with retry resilience, idempotent job execution, signed webhook delivery,
> and an AI-assisted ops layer.

**Narrative arc for interviews:** correctness under concurrency → resilience under
failure → security by design → AI-assisted operations.

---

## Core Architecture

- **Users/Tenants:** multi-tenant from day one — each tenant has their own jobs,
  secrets, and dashboard view (data isolation designed in from the start, not retrofitted)
- **Database:** PostgreSQL — jobs table, execution/attempt history, tenant secrets
- **Caching:** Redis — cache-aside on `GET /jobs` (key `jobs:tenant:{id}`), avoiding hammering the DB
- **Queue / background worker:** the core scheduling loop that checks for and dispatches due jobs
- **Deployment:** Docker → AWS EC2 → Kubernetes (per roadmap Weeks 13–14)
- **Code structure:** `routers/` (HTTP only) → `services/` (logic and DB work, no HTTP
  knowledge) → `models/` (SQLAlchemy models plus Pydantic request/response models)

---

## Code Conventions

- **Type hints, docstrings, and inline comments on every function:** all parameters and the
  return type annotated, a docstring on each function, plus inline comments where they aid
  understanding. This is **not mandatory while building**, since the focus is on getting
  features working. It must be fully in place before the project is closed at the
  **Week 17 checkpoint** (see below).
- **Plain SQLAlchemy** (not SQLModel).
- **Response models** are built from ORM objects with Pydantic `from_attributes`
  (`Model.model_validate(obj)`), not by copying fields by hand.

---

## Core Backend Features (Non-AI)

### 1. Job Registration & Scheduling (MVP baseline)
- Tenants register jobs via API: webhook URL + schedule (cron-style)
- Background worker checks for due jobs and dispatches them

### 2. Idempotency via Distributed Locking (Week 12) — DONE
- Prevents duplicate execution if multiple scheduler workers run concurrently
- Implementation: Postgres `SELECT FOR UPDATE SKIP LOCKED` (`.with_for_update(skip_locked=True)`)
- **Why it matters:** classic, frequently-asked distributed systems interview question —
  hands-on implementation experience, not just theory

### 3. Retry with Exponential Backoff + Dead-Letter Handling (Week 12) — DONE
- Failed webhook calls retry with increasing delays; after `retry_policy.max_attempts`
  failures, the job flips to `dead` instead of retrying forever or vanishing silently
- **Why it matters:** demonstrates designing for failure as a first-class case, not just the
  happy path; a scheduler that retries immediately with no backoff risks a "retry storm" —
  piling more load onto a target that's already struggling, right when it has the least
  capacity to handle it
- **Why not block-and-sleep in the loop:** retries are **not** implemented as `await
  asyncio.sleep(N)` inside the dispatch loop — that would stall every other due job in the
  same batch behind one job's retry delay, since the loop is single-threaded/sequential, not
  one `asyncio.Task` per job. Instead, a retry is just scheduled as a future poll cycle, same
  as any normal job: shorten `next_trigger_ts` to "now + N minutes" and let the existing
  poller pick it up naturally next cycle. No blocking, no special retry machinery needed.
- **Columns** (see `data-model.md`): `Job.attempts` (int, default `0`) and
  `Job.scheduled_trigger_ts` (datetime), both in the model, live DB, and `JobResponse`
- **Full design, per dispatch attempt (implemented in `services/scheduler.py`):**
  - Before dispatch: if `due_job.attempts == 0` (first attempt of a fresh cycle), freeze
    `due_job.scheduled_trigger_ts = due_job.next_trigger_ts` — this preserves the original
    scheduled time across however many retries follow, since `next_trigger_ts` itself gets
    overwritten with short retry delays as attempts progress
  - Increment `due_job.attempts` by 1; this value is also used as `Log.attempt_number` for
    this dispatch
  - `due_job.last_trigger_ts = fired_at` updates on **every** attempt, including retries —
    this is tenant-facing "when did this job last actually fire," independent of the
    scheduling math, so it stays live the whole cycle rather than freezing at attempt 1
  - **On success:** `attempts` → `0`; `state` → `pending`; `next_trigger_ts` →
    `get_next_triger_ts(schedule, scheduled_trigger_ts)` — anchored on the frozen original
    scheduled time, never on the actual (possibly-delayed-by-retries) fire time, so the
    schedule never drifts later
  - **On failure/error, `attempts < max_attempts`:** `state` returns to `pending`;
    `next_trigger_ts` → now + `2 ** (attempts - 1)` minutes (1 min after attempt 1 fails,
    2 min after attempt 2 fails, etc.)
  - **On failure/error, `attempts >= max_attempts`:** `state` → `dead`; `attempts` reset to
    `0` (clean slate for if the job is ever manually revived — reviving should resume normal
    cadence, not replay a stale retry timestamp); `next_trigger_ts` →
    `get_next_triger_ts(schedule, scheduled_trigger_ts)`, same anchor as the success case, so
    a revived job already sits at a sensible next normal occurrence
- **Verified end to end (Oct 2):** a job with `max_attempts: 1` pointed at
  `https://httpbin.org/status/500` went `dead` after one attempt: `attempts` back to `0`,
  `scheduled_trigger_ts` frozen at the cron time, `next_trigger_ts` at the next cron
  occurrence, `last_trigger_ts` at the real fire time, and one `Log` row (`failed`, 500).
- `paused` is purely tenant-controlled (via PATCH), never set by the scheduler. The earlier
  `paused` placeholder for failed dispatches has been removed.

### 4. Webhook Signing (HMAC) (Week 12) — DONE
- Every dispatched webhook carries an HMAC-SHA256 signature using the tenant's `hmac_secret`
- **Header format:** `X-Signature: sha256=<hex digest>`
- **Sign the exact bytes sent:** the payload is serialized once with
  `json.dumps(payload).encode()`, those bytes are signed, and the same bytes are sent via
  httpx `content=` with `Content-Type: application/json`. Letting the HTTP client serialize
  the payload separately could produce different bytes (spacing, key order) and break
  verification on the receiver's side.
- **No job stuck in `running`:** tenant lookup and signing live inside the dispatch `try`, and
  a broad `except Exception` records `f"{type(e).__name__}: {e}"` in the log. A failure
  anywhere in dispatch (not only the HTTP call) therefore still resolves the job through
  the retry/dead-letter logic instead of leaving it `running` forever.
- Verified against `httpbin.org/anything`.
- **Why it matters:** directly extends the JWT signing-vs-encryption concept learned in
  Week 9 system design — ties learning to build

### Dashboard (demo layer, not a "core feature" but required for demoability)
- Job list per tenant
- Execution history (success / fail / retry count) per job
- Dead-letter view — jobs that exhausted retries
- Manual pause / retry controls
- **Scope decision deferred to the Week 17 checkpoint**, based on time available at that point

---

## Job Management API (Week 9–12)

Authentication flow: a tenant registers once (`POST /tenants`) and receives an API key and
HMAC secret. The API key is exchanged for a short-lived JWT (`POST /token`, 15-minute
expiry). Every `/jobs` route requires that JWT as `Authorization: Bearer <token>`.

| Method | Path | Auth | Status |
|---|---|---|---|
| POST | `/tenants` | none (open registration) | Done |
| POST | `/token` | API key (JSON body) | Done |
| POST | `/jobs` | JWT | Done |
| GET | `/jobs` | JWT | Done — cached (Redis cache-aside) when no `state` param |
| GET | `/jobs?state=<state>` | JWT | Done (Week 12) — optional `state` filter, typed `Literal["pending", "running", "dead", "paused"]` so a typo like `?state=ded` gets a 422; `?state=dead` is the dead-letter view. **Bypasses Redis** and queries Postgres directly. |
| GET | `/jobs/{id}` | JWT | Done (Week 12) — single job as `JobResponse`; 404 if missing or not the tenant's; plain read, **no row lock** |
| GET | `/jobs/{id}/logs` | JWT | Done (Week 12) — execution history as `list[LogResponse]`, oldest-first by `fired_at`; ownership checked via `get_job_by_id` first (404 if not the tenant's); a job with no logs yet returns `200 []` |
| PATCH | `/jobs/{id}` | JWT | Done (Week 10) — edits schedule, description, job_url, retry_policy, request_config, and pauses/un-pauses; returns the full updated job; row-locked as of Week 12 |
| DELETE | `/jobs/{id}` | JWT | Done (Week 10) — 204 No Content; 404 if missing or not the tenant's; **409 on a `running` job (Week 12)**; row-locked; logs cascade-delete |

**Design decisions:**
- **Tenant isolation:** every jobs query is filtered by the `tenant_id` derived from the
  JWT, never from the URL, query params, or request body. A job that belongs to another
  tenant is treated as not found. `logs` has no `tenant_id` column, so the logs route proves
  ownership by calling `get_job_by_id` (tenant-scoped) before querying `Log` by `job_id`.
- **Tenant-settable job state:** a tenant may set `state` only to `pending` (un-pause) or
  `paused`. `running` and `dead` are set by the scheduler only. `state` is stored as a plain
  string column; the allowed values are enforced in the API layer (a `Literal` type on the
  request model and on the `?state=` query param), not the database.
- **Job creation:** the client sends `job_description` (optional), `schedule`, `job_url`,
  `retry_policy` (optional), and `request_config`. The server generates `job_id`,
  `tenant_id` (from the JWT), `state` (starts as `pending`), `job_created_ts`, and
  `next_trigger_ts`; `last_trigger_ts` stays empty until the job first fires. The response
  returns only `job_id`, `job_created_ts`, and `next_trigger_ts`.
- **Retry policy default:** if the tenant omits `retry_policy`, the column default
  (`{"max_attempts": 3, "backoff": "exponential"}`) is applied. `None` is never stored.
- **Cron handling:** schedules are parsed with `croniter`. `next_trigger_ts` is computed
  from the same timestamp used for `job_created_ts`. An invalid cron string returns 422
  from the router; the service layer just raises.
- **Validation:** `job_url` must be a valid http(s) URL (Pydantic `HttpUrl`, stored as a
  plain string).
- **List response:** `GET /jobs` returns every job field except `tenant_id`, newest
  `job_created_ts` first. The `?state=` path uses the same ordering and the same
  `JobResponse`.
- **Filtered list bypasses the cache:** the Redis key `jobs:tenant:{id}` holds the tenant's
  full list and has no `state` in it. Routing `?state=` requests to a separate service
  function (`list_jobs_by_state`) that never touches Redis means a filtered request can
  neither be served the cached full list nor write a filtered list into the cache. One
  function serves every state.

**`get_job_by_id` and when it locks (Week 12):**
- Signature: `get_job_by_id(session, tenant_id, job_id, for_update=False)`. It builds the
  tenant-scoped query in a variable and adds plain `.with_for_update()` only when
  `for_update` is true.
- **PATCH and DELETE pass `for_update=True`.** The state check and the commit aren't atomic,
  and once the scheduler exists it could flip a job to `running` in that gap. The row lock
  makes the check-then-write safe. The lock is released by `commit()` inside the update, or
  by the session close in `get_session`'s `finally` on early exits (409/422).
- **Plain `.with_for_update()`, not `skip_locked`:** PATCH/DELETE should *wait* for the lock
  rather than skip the row, because skipping would return a false 404 for a job that exists.
  The scheduler is the opposite: it uses `skip_locked=True` because skipping a busy row is
  exactly what it wants.
- **GET routes must not lock.** A read lock would make the scheduler's `skip_locked` poll
  skip the job for no reason. `GET /jobs/{id}` and the logs ownership check use the default
  `for_update=False`.
- **Verified** with a two-terminal psql test: PATCH blocked on the held lock, then returned
  409 once the other transaction set the job to `running` and committed.

**PATCH `/jobs/{id}` rules:**
- **Partial updates:** every field in the body is optional, and only the fields the tenant
  actually sent are applied. `job_id` comes from the URL path, never the body.
- **Nulls:** an explicit `null` is rejected with 422 (naming the field) for every field
  except `job_description`, which a tenant may clear.
- **State guard:** a job can be edited only while its current state is `pending` or
  `paused`. A `running` or `dead` job returns 409 Conflict.
- **Schedule change:** the new cron string is validated (invalid → 422) and
  `next_trigger_ts` is recomputed from now. `job_created_ts` never changes.
- **Un-pause (`paused` → `pending`):** `next_trigger_ts` is recomputed from now using the
  job's stored schedule, so a job paused for days doesn't fire immediately on a stale time.
  If a new schedule is sent in the same request, the new schedule's value wins.
- **Pause:** `next_trigger_ts` is left untouched. The scheduler only picks up `pending`
  jobs, so a paused job is skipped regardless of its stored time.
- **Response:** the full updated job, using the same `JobResponse` as `GET /jobs`.

**DELETE `/jobs/{id}` rules:**
- Tenant-scoped, row-locked lookup by `job_id` and JWT `tenant_id`; 404 if not found or not
  the tenant's (so a job in another tenant is indistinguishable from a missing one).
- **409 if the job is `running`** — blocked to avoid deleting a job out from under a
  mid-execution dispatch. (Reuses the PATCH exception, whose message says "edited"; a
  delete-specific message is optional polish.)
- Success returns 204 with an empty body; a repeat call returns 404.
- **Cascade delete:** `Log.job_id` has `ondelete="CASCADE"` (model and live DB), so deleting
  a job removes its logs.

**Manual retry of a dead job:** not yet built; **decision on whether/how to add it is
deferred to the Week 17 checkpoint.**

---

## MVP Simplifications (known, deliberate)

- No UNIQUE constraint on `tenant_name`.
- Registration (`POST /tenants`) is open and unauthenticated. Abuse / rate limiting is
  parked as an open question.
- The `/docs` "Authorize" button doesn't work: login takes a JSON `api_key`, not the
  standard OAuth2 username/password form. Testing is done with curl.
- `state` isn't enforced at the database level (plain string column).
- A `dead` job can't be edited through PATCH; reviving one is left to the manual-retry
  decision at Week 17.
- No recovery for a job left in `running` if the process dies mid-dispatch (e.g. a
  `uvicorn --reload` during a dispatch); the poller only picks up `pending`. Known, not
  scheduled.

---

## Week 12 — Background Jobs / Queue

- **Scheduler loop:** `lifespan` startup hook in `app/main.py` runs
  `asyncio.create_task(scheduler_loop())`, continuously in the same process as the FastAPI
  app (not `BackgroundTasks`, which is tied to a single request/response cycle; not Redis
  pub/sub, ruled out as fire-and-forget with no benefit over polling for a single-loop design)
  - Polling query: find jobs where `state = 'pending'` and due
  - Dispatch: async HTTP client (`httpx.AsyncClient`, not `requests`) calls the webhook, so
    a slow/hanging call doesn't stall the event loop
  - State transitions: mark `running` before dispatch (committed immediately, closing the
    concurrency gap for the whole batch at once); after dispatch, state / `next_trigger_ts` /
    `attempts` / `scheduled_trigger_ts` follow the retry/dead-letter design in section 3
  - Logging: a `Log` row per attempt
  - Implemented as two passes over `due_jobs`, not one combined loop: pass 1 marks every due
    job `running` and commits once (batch-wide concurrency protection); pass 2 dispatches
    each job one at a time. A single combined loop (mark → commit → dispatch, job by job)
    was considered and rejected — it would leave every *other* due job in the batch exposed
    as `pending` (and grabbable by a concurrent worker) for as long as the current job's
    dispatch takes
- **Scheduler cache invalidation:** after the commits in both passes, the scheduler deletes
  the Redis key `jobs:tenant:{id}`, wrapped in `try/except RedisError`, so scheduler-driven
  state changes don't leave `GET /jobs` serving stale data and a Redis outage can't break
  the scheduler.
- **`get_current_tenant` fix (done):** changed from `async def` to plain `def` so FastAPI
  runs its blocking `session.query(...)` in the thread pool instead of on the event loop
- **Idempotency via distributed locking (done):** `.with_for_update(skip_locked=True)` on the
  polling query so a concurrent scheduler worker's identical query skips any row this one
  has already locked. The lock only needs to protect the narrow window between the query and
  the immediate `running`-state commit — it is not held through dispatch, because by then
  every job's `running` state is committed and a second worker's `state == "pending"`
  filter excludes them
- **Retry with exponential backoff + dead-letter handling (done):** see section 3
- **Webhook Signing (HMAC) (done):** see section 4
- **`Log` model (done):** per `data-model.md`; a row per dispatch attempt; `job_id` FK with
  cascade delete
- **PATCH/commit race condition fix (done):** row locking via `get_job_by_id(...,
  for_update=True)`; see "`get_job_by_id` and when it locks" above
- **DELETE on a `running` job (done):** blocked with 409
- **`register_tenant()` try/finally (done):** `SessionLocal()` above the `try`;
  `session.add` and `session.commit()` inside it; `session.close()` in `finally`
- **New routes (done):** `GET /jobs/{id}`, `GET /jobs/{id}/logs`, `GET /jobs?state=`,
  all verified with curl (own job, missing job, other tenant's job, bad `state` value)

**Deferred to Week 17 (not Week 12):**
- Manual retry of a dead job — whether/how to add it
- Dashboard scope — build or skip, decided based on time remaining

---

## AI Features (Phase 3, Weeks 18–22)

### Locked in now:

**A. Natural-Language Job Creation** (Week 18)
- Tenant types plain English ("run this every weekday at 9am, retry twice") →
  LLM call parses this into the structured job schema (cron expression + retry policy)

**B. Failure Diagnosis / Root-Cause Summarization** (Weeks 19–20, RAG)
- When a job is dead-lettered, retrieve its failure history (error messages, response
  codes, timing patterns) and generate a plain-English root-cause summary
  (e.g. "This job has failed 5 times, always with a 504 timeout between 2–3am —
  the target server may be under load during that window.")
- This is the natural home for the RAG requirement — retrieving/summarizing structured
  failure logs, rather than a forced-fit RAG use case

**C. Conversational Ops Assistant** (Week 21, agent/tool-calling)
- Chat interface where you can ask things like "which tenant has the most failed jobs
  this week?" or "pause all jobs failing more than 3 times"
- Agent calls internal APIs as tools and responds conversationally
- Most demoable AI feature of the project — strong live screen-share moment for interviews

### If time allows (next priority, not committed):

**D. Anomaly Detection on Scheduling Patterns**
- Flag unusual behavior — a job that normally takes 200ms suddenly taking 8s, or a
  tenant's job volume spiking 10x overnight
- Can be LLM-based or a lighter statistical/heuristic version

**E. Smart Retry Policy Suggestions**
- Based on a job's failure history, suggest a tuned retry strategy (e.g., shorter
  backoff for fast-recovering endpoints, longer backoff for consistently slow ones)
- Extends naturally alongside the Week 21 agent work

---

## Week 17 Checkpoint (non-negotiable before Phase 3)

Project live, documented, tested, deployable — AND you can walk through every major design
decision in it (auth, caching, queue, deployment) out loud, unscripted, in under 5 minutes
total.

**Code audit as part of this checkpoint:** verify that every function in the codebase has
type hints on all parameters and its return type, a docstring, and inline comments for
clarity — and fix any that don't. Known gaps to fix: `for_update: bool = False` and
`-> Job | None` on `get_job_by_id`; `session` and return annotations on the new service
functions (`get_logs_row`, `list_jobs_by_state`).

**Decisions made at this checkpoint:**
- Manual retry of a dead job — whether/how to add it
- Dashboard — build or skip, based on time remaining
- DSA volume — whether ~75-90 problems is enough or needs extending (per `roadmap_v2.md`)

---

## Status (as of October 3, 2026 — Day 79)

- ✅ Project domain and idea locked in (Week 9)
- ✅ AI feature scope locked in (A, B, C committed; D, E as stretch goals)
- ✅ Data model design (see data-model.md)
- ✅ Auth implementation: tenant registration, API key → JWT login, JWT-protected routes (Weeks 9–10)
- ✅ `POST /jobs` and `GET /jobs` (Week 10)
- ✅ `PATCH /jobs/{id}` and `DELETE /jobs/{id}` (Week 10)
- ✅ Redis caching (Week 11) — cache-aside on `GET /jobs`, verified end-to-end
- ✅ Background jobs / queue (Week 12) — code and routes complete:
  - ✅ `get_current_tenant` fixed to plain `def`
  - ✅ `Log` model (cascade delete on `job_id`)
  - ✅ Scheduler loop (lifespan hook, two-pass claim/dispatch, `httpx.AsyncClient`, `Log` writes)
  - ✅ Idempotency locking (`with_for_update(skip_locked=True)`)
  - ✅ Retry/backoff + dead-letter, coded and verified end to end
  - ✅ HMAC signing
  - ✅ Scheduler Redis cache invalidation
  - ✅ PATCH race fix and DELETE-blocked-on-`running` (via `for_update` flag)
  - ✅ `register_tenant()` try/finally
  - ✅ `GET /jobs/{id}`, `GET /jobs/{id}/logs`, `GET /jobs?state=`
  - ⬜ Week 12 DSA (Graphs intro, BFS/DFS, 3 problems) — weekend only
- ⬜ AWS deployment (Week 13)
- ⬜ Kubernetes (Week 14)
- ⬜ Type hints + docstrings + inline comments audit, part of the Week 17 checkpoint
- ⬜ Manual retry of a dead job — decision deferred to Week 17
- ⬜ Dashboard — decision deferred to Week 17