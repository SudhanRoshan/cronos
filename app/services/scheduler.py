import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from redis.exceptions import RedisError

from app.cache import r
from app.config import SLEEP_SECONDS
from app.database import SessionLocal
from app.models.database_models import Job, Log, Tenant
from app.services.jobs import get_next_triger_ts


async def scheduler_loop():
    while True:
        session = SessionLocal()
        try:
            due_jobs = (
                session.query(Job)
                .filter(
                    Job.next_trigger_ts <= datetime.now(timezone.utc),
                    Job.state == "pending",
                )
                .with_for_update(skip_locked=True)
                .all()
            )
            async with httpx.AsyncClient() as client:
                tenant_ids = set()
                for due_job in due_jobs:
                    due_job.state = "running"
                    tenant_ids.add(due_job.tenant_id)
                session.commit()
                for tenant_id in tenant_ids:
                    try:
                        r.delete(f"jobs:tenant:{tenant_id}")
                    except RedisError:
                        pass
                for due_job in due_jobs:
                    headers = due_job.request_config.get("headers", {})
                    method = due_job.request_config["method"]
                    payload = due_job.request_config.get("payload", {})
                    max_attempts = due_job.retry_policy.get("max_attempts", 3)
                    if due_job.attempts == 0:
                        due_job.scheduled_trigger_ts = due_job.next_trigger_ts
                    fired_at = datetime.now(timezone.utc)
                    due_job.attempts += 1
                    attempt_number = due_job.attempts
                    try:
                        tenant = session.query(Tenant).filter(Tenant.tenant_id == due_job.tenant_id).first()
                        body = json.dumps(payload).encode()
                        signature = hmac.new(tenant.hmac_secret.encode(), body, hashlib.sha256).hexdigest()
                        headers = {**headers, "Content-Type": "application/json", "X-Signature": f"sha256={signature}"}
                        response = await client.request(method, due_job.job_url, content=body, headers=headers, timeout=30)
                        if response.is_success:
                            due_job.state = "pending"
                            due_job.next_trigger_ts = get_next_triger_ts(due_job.schedule, due_job.scheduled_trigger_ts)
                            due_job.attempts = 0
                            status = "success"
                            response_detail = None
                        else:
                            status = "failed"
                            response_detail = response.text[:500]
                        http_response_code = response.status_code
                    except Exception as e:  # noqa: BLE001
                        status = "error"
                        http_response_code = None
                        response_detail = f"{type(e).__name__}: {e}"
                    if status != "success":
                        if due_job.attempts >= max_attempts:
                            due_job.state = "dead"
                            due_job.attempts = 0
                            due_job.next_trigger_ts = get_next_triger_ts(due_job.schedule, due_job.scheduled_trigger_ts)
                        else:
                            due_job.state = "pending"
                            n = 2**(due_job.attempts - 1)
                            due_job.next_trigger_ts = datetime.now(timezone.utc) + timedelta(minutes=n)
                    responded_at = datetime.now(timezone.utc)
                    due_job.last_trigger_ts = fired_at
                    log = Log(
                        log_id = uuid.uuid4(),
                        job_id = due_job.job_id,
                        attempt_number = attempt_number,
                        fired_at = fired_at,
                        responded_at = responded_at,
                        status = status,
                        http_response_code = http_response_code,
                        response_detail = response_detail
                    )
                    session.add(log)
                    session.commit()
                    try:
                        r.delete(f"jobs:tenant:{due_job.tenant_id}")
                    except RedisError:
                        pass
        finally:
            session.close()
        await asyncio.sleep(SLEEP_SECONDS)
