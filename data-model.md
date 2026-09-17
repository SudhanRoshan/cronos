Here's the complete, final data model:

**tenants**
| Column | Notes |
|---|---|
| `tenant-id` | Primary key (server-generated) |
| `tenant-name` | Tenant's display name |
| `hmac-secret` | Shared secret for webhook signing |
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
| `state` | One of: `pending`, `running`, `dead` |
| `job-created-ts` | When the job was first registered |
| `next-trigger-ts` | When this job should next fire |
| `last-trigger-ts` | When this job's most recent trigger cycle started |

**logs**
| Column | Notes |
|---|---|
| `log-id` | Primary key |
| `job-id` | Foreign key → `jobs.job-id` |
| `attempt-number` | Which retry attempt, within one trigger cycle |
| `fired-at` | Timestamp the webhook call was made |
| `responded-at` | Timestamp a response (or timeout) was received |
| `status` | One of: `success`, `failed`, `error` |
| `http-response-code` | Nullable — actual HTTP status returned, if any |
| `response-detail` | Nullable — free text: error message or notable response info |
