import json
import uuid
from datetime import datetime, timezone

from croniter import croniter
from redis.exceptions import RedisError

from app.cache import r
from app.models.database_models import Job
from app.models.response_models import CreateJobResponse, JobResponse


def get_current_next_ts(schedule: str):
    current_time = datetime.now(timezone.utc)
    cron_iter = croniter(schedule, current_time)
    return current_time, cron_iter.get_next(datetime)

def get_next_triger_ts(schedule: str, prev_next_trigger: datetime):
    cron_iter = croniter(schedule, prev_next_trigger)
    return cron_iter.get_next(datetime)

def create_new_job(job, current_ts: datetime, next_trigger_ts: datetime, session, tenant_id: uuid.UUID):
    job_dict = {
        "job_id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "job_description": job.job_description,
        "schedule": job.schedule,
        "job_url": str(job.job_url),
        "request_config": job.request_config,
        "job_created_ts": current_ts,
        "next_trigger_ts": next_trigger_ts
    }
    if job.retry_policy:
        job_dict["retry_policy"] = job.retry_policy
    new_job = Job(**job_dict)
    session.add(new_job)
    session.commit()
    try:
        r.delete(f"jobs:tenant:{tenant_id}")
    except RedisError:
        pass
    return CreateJobResponse.model_validate(new_job)

def list_all_jobs(session, tenant_id: uuid.UUID):
    cache_hit = False
    try:
        jobs = r.get(f"jobs:tenant:{tenant_id}")
        if jobs:
            cache_hit = True
            # convert json string into dict
            jobs = json.loads(jobs)
    # catch redis crash if happens and
    # fallback to postgres db lookup
    except RedisError:
        pass
    # db lookup for cache miss
    if not cache_hit:
        jobs = session.query(Job).filter(Job.tenant_id == tenant_id).order_by(Job.job_created_ts.desc()).all()
        
        jobs = [JobResponse.model_validate(job).model_dump(mode="json") for job in jobs]
        try:
            r.set(f"jobs:tenant:{tenant_id}", json.dumps(jobs), ex=86400)
        except RedisError:
            pass
    return jobs

def get_job_by_id(session, tenant_id: uuid.UUID, job_id: uuid.UUID, for_update: bool = False):
    query = session.query(Job).filter(Job.tenant_id == tenant_id, Job.job_id == job_id)
    if for_update:
        query = query.with_for_update()
    return query.first()

def update_job_row(session, job: Job, updates: dict):
    for k, v in updates.items():
        setattr(job, k, v)
    session.commit()
    try:
        r.delete(f"jobs:tenant:{job.tenant_id}")
    except RedisError:
        pass
    return JobResponse.model_validate(job)

def delete_job_row(session, job: Job):
    session.delete(job)
    session.commit()
    try:
        r.delete(f"jobs:tenant:{job.tenant_id}")
    except RedisError:
        pass

def list_jobs_by_state(session, tenant_id: uuid.UUID, state: str):
    jobs = session.query(Job).filter(Job.tenant_id == tenant_id, Job.state == state).order_by(Job.job_created_ts.desc()).all()
    return [JobResponse.model_validate(job) for job in jobs]