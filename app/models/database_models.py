import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"
    
    tenant_id = Column(UUID(as_uuid=True), default = uuid.uuid4, primary_key=True)
    tenant_name = Column(String, nullable=False)
    hmac_secret = Column(String, nullable=False)
    api_key_hash = Column(String, nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    job_description = Column(String)
    schedule = Column(String, nullable=False)
    job_url = Column(String, nullable=False)
    retry_policy = Column(JSON, nullable=False, default=lambda: {"max_attempts": 3, "backoff": "exponential"})
    request_config = Column(JSON, nullable=False)
    state = Column(String, nullable=False, default="pending")
    job_created_ts = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    next_trigger_ts = Column(DateTime(timezone=True), nullable=False)
    last_trigger_ts = Column(DateTime(timezone=True))
    scheduled_trigger_ts = Column(DateTime(timezone=True))
    attempts = Column(Integer, nullable=False, default=0)


class Log(Base):
    __tablename__ = "logs"

    log_id = Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    fired_at = Column(DateTime(timezone=True), nullable=False)
    responded_at = Column(DateTime(timezone=True))
    status = Column(String, nullable=False)
    http_response_code = Column(Integer)
    response_detail = Column(String)