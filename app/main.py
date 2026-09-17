import uuid

from app.database import SessionLocal
from app.models import Tenant
from app.auth import generate_api_key, get_api_key_hash, generate_hmac_secret

def register_tenant(tenant_name):
    tenant_id = uuid.uuid4()  # generate it yourself, in Python, right now
    
    raw_key = generate_api_key(tenant_id)
    hashed_key = get_api_key_hash(raw_key.split(".")[1])  # hash only the secret part
    
    session = SessionLocal()
    hmac_secret = generate_hmac_secret()
    new_tenant = Tenant(
        tenant_id=tenant_id,          # explicitly pass it in, instead of relying on default=
        tenant_name=tenant_name,
        hmac_secret = hmac_secret,
        api_key_hash=hashed_key
    )
    session.add(new_tenant)
    session.commit()
    session.close()
    
    return {"api-key": raw_key, "hmac-secret": hmac_secret}
