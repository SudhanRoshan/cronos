import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class RegisterTenantResponse(BaseModel):
    api_key: str
    hmac_secret: str

class LoginTenantResponse(BaseModel):
    access_token: str
    token_type: str

class CreateJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: uuid.UUID
    job_created_ts: datetime
    next_trigger_ts: datetime

class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: uuid.UUID
    job_description: str | None = None
    schedule: str
    job_url: HttpUrl
    retry_policy: dict
    request_config: dict
    state: str
    job_created_ts: datetime
    next_trigger_ts: datetime
    last_trigger_ts: datetime | None = None
    scheduled_trigger_ts: datetime | None = None
    attempts: int = 0

class LogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    log_id: uuid.UUID
    job_id: uuid.UUID
    attempt_number: int
    fired_at: datetime
    responded_at: datetime
    status: str
    http_response_code: int | None
    response_detail: str | None
    