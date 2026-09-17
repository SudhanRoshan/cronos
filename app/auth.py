import jwt
import os
import secrets
import uuid

from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import HTTPException, status
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from app.models import Tenant

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
)

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

api_key_hasher = PasswordHash.recommended()

DUMMY_HASH = api_key_hasher.hash("dummypassword")

def generate_api_key(tenant_id):
    secret_part = secrets.token_urlsafe(16)
    return f"{tenant_id}.{secret_part}"

def get_api_key_hash(api_key):
    return api_key_hasher.hash(api_key)

def generate_hmac_secret():
    return secrets.token_hex(32)

def verify_api_key(raw_secret_part, stored_hash):
    return api_key_hasher.verify(raw_secret_part, stored_hash)

def authenticate_tenant(incoming_api_key, session):
    tenant_id_str, secret_part = incoming_api_key.split(".")
    tenant_id = uuid.UUID(tenant_id_str)
    
    # look up the tenant by tenant_id
    tenant = session.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    
    if tenant is None:
        dummy_var = verify_api_key(secret_part, DUMMY_HASH)
        return None
    
    if not verify_api_key(secret_part, tenant.api_key_hash):
        return None  # key doesn't match
    
    return tenant  # success

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_tenant(token, session):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        tenant_id = payload.get("sub")
        if tenant_id is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    tenant = session.query(Tenant).filter(Tenant.tenant_id == uuid.UUID(tenant_id)).first()
    if not tenant:
        raise credentials_exception
    else:
        return tenant
    
