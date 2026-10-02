from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_session
from app.models.request_models import LoginTenantRequest, RegisterTenantRequest
from app.models.response_models import LoginTenantResponse, RegisterTenantResponse
from app.services.auth import authenticate_tenant, create_access_token, register_tenant

router = APIRouter()

api_key_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid API key")


@router.post("/tenants", status_code=201)
def register_new_tenant(tenant: RegisterTenantRequest) -> RegisterTenantResponse:
    """
    Endpoint to register a new tenant.
    """
    return register_tenant(tenant_name=tenant.tenant_name)


@router.post("/token", status_code=200)
def login_tenant(login: LoginTenantRequest, session=Depends(get_session)) -> LoginTenantResponse:  # noqa: B008
    """
    Endpoint to login a tenant.
    """
    tenant = authenticate_tenant(incoming_api_key=login.api_key, session=session)
    if not tenant:
        raise api_key_exception
    access_token = create_access_token(data={"sub": str(tenant.tenant_id)})
    return LoginTenantResponse(access_token=access_token, token_type="bearer")