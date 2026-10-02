import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError

from app.config import ALGORITHM, SECRET_KEY
from app.database import SessionLocal
from app.models.database_models import Tenant

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def get_current_tenant(token=Depends(oauth2_scheme), session=Depends(get_session)):  # noqa: B008
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