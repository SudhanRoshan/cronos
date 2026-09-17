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
- **Caching:** Redis — next-run lookups, avoiding hammering the DB on every scheduler tick
- **Queue / background worker:** the core scheduling loop that checks for and dispatches due jobs
- **Deployment:** Docker → AWS EC2 → Kubernetes (per roadmap Weeks 13–14)

---

## Core Backend Features (Non-AI)

### 1. Job Registration & Scheduling (MVP baseline)
- Tenants register jobs via API: webhook URL + schedule (cron-style)
- Background worker checks for due jobs and dispatches them

### 2. Idempotency via Distributed Locking
- Prevents duplicate execution if multiple scheduler workers run concurrently
- Implementation: Postgres `SELECT FOR UPDATE SKIP LOCKED` (or Redis-based lock)
- **Why it matters:** classic, frequently-asked distributed systems interview question —
  hands-on implementation experience, not just theory

### 3. Retry with Exponential Backoff + Dead-Letter Handling
- Failed webhook calls retry with increasing delays
- After N failures, job flips to a "dead" state instead of retrying forever or vanishing silently
- **Why it matters:** demonstrates designing for failure as a first-class case, not just the happy path

### 4. Webhook Signing (HMAC)
- Every dispatched webhook includes an HMAC signature (per-tenant secret)
- Receiving app can verify the request genuinely came from the scheduler
- **Why it matters:** directly extends the JWT signing-vs-encryption concept learned in
  Week 9 system design — ties learning to build

### Dashboard (demo layer, not a "core feature" but required for demoability)
- Job list per tenant
- Execution history (success / fail / retry count) per job
- Dead-letter view — jobs that exhausted retries
- Manual pause / retry controls

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

## Status (as of September 11, 11:30 AM IST)

- ✅ Project domain and idea locked in (Week 9)
- ✅ AI feature scope locked in (A, B, C committed; D, E as stretch goals)
- ⬜ Data model design (jobs, execution history, tenant secrets) — next step
- ⬜ Auth implementation (Week 9 in progress, per roadmap_v2.md)
- ⬜ Core CRUD build (Week 10)
- ⬜ Redis caching (Week 11)
- ⬜ Background jobs / queue (Week 12)
- ⬜ AWS deployment (Week 13)
- ⬜ Kubernetes (Week 14)