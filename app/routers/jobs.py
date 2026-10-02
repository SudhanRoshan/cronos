import uuid
from typing import Literal

from croniter import CroniterBadCronError
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_tenant, get_session
from app.models.request_models import CreateJobRequest, UpdateJobRequest
from app.models.response_models import CreateJobResponse, JobResponse, LogResponse
from app.services.jobs import (
    create_new_job,
    delete_job_row,
    get_current_next_ts,
    get_job_by_id,
    list_all_jobs,
    list_jobs_by_state,
    update_job_row,
)
from app.services.logs import get_logs_row

router = APIRouter()

bad_cron_exception = HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    detail="Invalid cron schedule"
)

resource_not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Resource not found"
)

invalid_job_state_exception = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Job cannot be edited while running or dead"
)

@router.post("/jobs", status_code=201)
def create_job(job: CreateJobRequest, current_tenant=Depends(get_current_tenant), session=Depends(get_session)) -> CreateJobResponse:  # noqa: B008
    """
    Endpoint to create a new job for the current tenant.
    """
    try:
        current_ts, next_trigger_ts = get_current_next_ts(job.schedule)
    except CroniterBadCronError:
        raise bad_cron_exception
    return create_new_job(job, current_ts, next_trigger_ts, session, current_tenant.tenant_id)


@router.get("/jobs", status_code=200)
def list_jobs(current_tenant=Depends(get_current_tenant), session=Depends(get_session), state: Literal["pending", "running", "dead", "paused"] | None = None) -> list[JobResponse]:  # noqa: B008
    """
    Endpoint to list all jobs for the current tenant.
    """
    if not state:
        return list_all_jobs(session, current_tenant.tenant_id)
    else:
        return list_jobs_by_state(session, current_tenant.tenant_id, state)


@router.patch("/jobs/{job_id}", status_code=200)
def update_job(updated_job: UpdateJobRequest, job_id: uuid.UUID, current_tenant=Depends(get_current_tenant), session=Depends(get_session)) -> JobResponse:  # noqa: B008
    """
    Endpoint to update an existing job for the current tenant.
    """
    job = get_job_by_id(session, current_tenant.tenant_id, job_id, for_update=True)
    if not job:
        raise resource_not_found_exception
    if job.state not in ["paused", "pending"]:
        raise invalid_job_state_exception
    dict_with_updates = updated_job.model_dump(exclude_unset=True)
    for k, v in dict_with_updates.items():
        if v is None and k != "job_description":
            raise HTTPException(status_code=422, detail=f"{k} value cannot be null")
    if "job_url" in dict_with_updates:
        dict_with_updates["job_url"] = str(dict_with_updates["job_url"])
    if ("state" in dict_with_updates and dict_with_updates["state"] == "pending") and job.state =="paused":
        current_ts, next_trigger_ts = get_current_next_ts(job.schedule)
        dict_with_updates["next_trigger_ts"] = next_trigger_ts
    if "schedule" in dict_with_updates:
        try:
            current_ts, next_trigger_ts = get_current_next_ts(dict_with_updates["schedule"])  # noqa: RUF059
            dict_with_updates["next_trigger_ts"] = next_trigger_ts
        except CroniterBadCronError:
            raise bad_cron_exception
    return update_job_row(session, job, dict_with_updates)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: uuid.UUID, current_tenant=Depends(get_current_tenant), session=Depends(get_session)) -> None:  # noqa: B008
    """
    Endpoint to delete a job for the current tenant
    """
    job = get_job_by_id(session, current_tenant.tenant_id, job_id, for_update=True)
    if not job:
        raise resource_not_found_exception
    if job.state == "running":
        raise invalid_job_state_exception
    delete_job_row(session, job)


@router.get("/jobs/{job_id}", status_code=200)
def get_job(job_id: uuid.UUID, current_tenant=Depends(get_current_tenant), session=Depends(get_session)) -> JobResponse:  # noqa: B008
    """
    Endpoint to get a job with given job id
    """
    job = get_job_by_id(session, current_tenant.tenant_id, job_id)
    if not job:
        raise resource_not_found_exception
    return JobResponse.model_validate(job)


@router.get("/jobs/{job_id}/logs", status_code=200)
def get_job_logs(job_id: uuid.UUID, current_tenant=Depends(get_current_tenant), session=Depends(get_session)) -> list[LogResponse]:  # noqa: B008
    """
    Endpoint to get a job's logs
    """
    job = get_job_by_id(session, current_tenant.tenant_id, job_id)
    if not job:
        raise resource_not_found_exception
    else:
        return get_logs_row(session, job_id)