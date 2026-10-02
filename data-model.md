Here's the complete, final data model:

**tenants**
| Column | Notes |
|---|---|
| `tenant-id` | Primary key (server-generated) |
| `tenant-name` | Tenant's display name |
| `hmac-secret` | Shared secret for webhook signing (HMAC-SHA256, sent as `X-Signature: sha256=<hex>`) |
| `api-key-hash` | Hashed API key that we sent to client |

**jobs**
| Column | Notes |
|---|---|
| `job-id` | Primary key (server-generated) |
| `tenant-id` | Foreign key → `tenants.tenant-id` |
| `job-description` | Human-readable description, from tenant |
| `schedule` | Cron syntax, from tenant |
| `job-url` | Webhook URL to call, from tenant |
| `retry-policy` | JSON — max attempts, backoff strategy |
| `request-config` | JSON — `method`, `payload`, `headers` (Content-Type is always auto-set to `application/json` by the scheduler, not stored here) |
| `state` | One of: `pending`, `running`, `dead`, `paused`. Plain string column; allowed values enforced in the API layer, not the database. Tenants may set only `pending`/`paused`; the scheduler sets `running`/`dead`. |
| `job-created-ts` | When the job was first registered |
| `next-trigger-ts` | When this job should next fire (recomputed from `scheduled-trigger-ts` on success/dead; set to a short retry delay while a trigger cycle is mid-retry) |
| `last-trigger-ts` | When this job's most recent dispatch attempt actually fired (updates on every attempt, including retries — tenant-facing "when did this last actually run") |
| `scheduled-trigger-ts` | **(Week 12)** The original scheduled fire time for the current trigger cycle, frozen on the cycle's first attempt (`attempts == 0`) and left untouched through any retries. Used as the anchor for computing the next cycle's `next-trigger-ts` on success or dead, so retries never drift the schedule later than it should be. |
| `attempts` | **(Week 12)** Integer, default `0`. Number of dispatch attempts made so far in the current trigger cycle. Incremented before each dispatch; reset to `0` on success or once a job goes `dead`. Compared against `retry-policy.max_attempts` to decide retry vs. dead-letter. |

**logs**
| Column | Notes |
|---|---|
| `log-id` | Primary key |
| `job-id` | Foreign key → `jobs.job-id`, `ON DELETE CASCADE` (deleting a job removes its logs) |
| `attempt-number` | Which retry attempt, within one trigger cycle (1-indexed; same value as the job's `attempts` column at the time of this dispatch) |
| `fired-at` | Timestamp the webhook call was made (matches the job's `last-trigger-ts` for that attempt) |
| `responded-at` | Timestamp a response (or timeout) was received; set on every path, including the broad exception branch |
| `status` | One of: `success`, `failed`, `error` |
| `http-response-code` | Nullable — actual HTTP status returned, if any |
| `response-detail` | Nullable — free text: error message or notable response info. A bad status code with no error message is currently stored as an empty string `""` rather than `null`. |

**Notes**
- `logs` has no `tenant-id` column. Tenant ownership of a log is established through its job:
  the API looks up the job with the tenant-scoped `get_job_by_id` before querying logs.