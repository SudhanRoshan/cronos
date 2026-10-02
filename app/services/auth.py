import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import ALGORITHM, SECRET_KEY
from app.database import SessionLocal
from app.models.database_models import Tenant

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
    try:
        tenant_id_str, secret_part = incoming_api_key.split(".")
        tenant_id = uuid.UUID(tenant_id_str)
    except ValueError:
        return None
    
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

def register_tenant(tenant_name):
    tenant_id = uuid.uuid4()  # generate it yourself, in Python, right now

    raw_key = generate_api_key(tenant_id)
    hashed_key = get_api_key_hash(raw_key.split(".")[1])  # hash only the secret part

    session = SessionLocal()
    hmac_secret = generate_hmac_secret()
    new_tenant = Tenant(
        tenant_id=tenant_id,  # explicitly pass it in, instead of relying on default=
        tenant_name=tenant_name,
        hmac_secret=hmac_secret,
        api_key_hash=hashed_key,
    )
    try:
        session.add(new_tenant)
        session.commit()
    finally:
        session.close()

    return {"api_key": raw_key, "hmac_secret": hmac_secret}