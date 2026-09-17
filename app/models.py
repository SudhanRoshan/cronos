import uuid

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"
    
    tenant_id = Column(UUID(as_uuid=True), default = uuid.uuid4, primary_key=True)
    tenant_name = Column(String, nullable=False)
    hmac_secret = Column(String, nullable=False)
    api_key_hash = Column(String, nullable=False)