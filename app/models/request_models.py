from typing import Literal

from pydantic import BaseModel, HttpUrl


class RegisterTenantRequest(BaseModel):
    tenant_name: str

class LoginTenantRequest(BaseModel):
    api_key: str

class CreateJobRequest(BaseModel):
    job_description: str | None = None
    schedule: str
    job_url: HttpUrl
    retry_policy: dict | None = None
    request_config: dict

class UpdateJobRequest(BaseModel):
    job_description: str | None = None
    schedule: str | None = None
    job_url: HttpUrl | None = None
    retry_policy: dict | None = None
    request_config: dict | None = None
    state: Literal["paused", "pending"] | None = None
    