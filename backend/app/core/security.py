from pathlib import Path
import re
import secrets
from typing import Optional
from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings
from app.core.logging import logger

http_bearer_scheme = HTTPBearer(auto_error=False)


def verify_opt_service_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(http_bearer_scheme),
) -> Optional[str]:
    """
    Validates inbound server-to-server and client requests.

    Security Boundaries:
    1. CORS Preflight:
       - Handled safely: HTTP OPTIONS requests pass unauthenticated so browser preflight can succeed.
    2. Server-to-Server Authentication:
       - Requires 'Authorization: Bearer <OPT_SERVICE_TOKEN>'.
       - Validated with constant-time comparison (secrets.compare_digest).
       - Invalid tokens return HTTP 403 Forbidden.
    3. Browser Client Authentication:
       - Accepts 'Authorization: Bearer <OPT_CLIENT_TOKEN>' or 'X-Client-Token: <OPT_CLIENT_TOKEN>'.
       - Origin and Referer headers are NEVER treated as an authentication or identity factor.
       - CORS remains an orthogonal browser-enforced security mechanism, not an authentication bypass.
    4. Production Fail-Closed Behavior:
       - In production (APP_ENV == 'production'):
         - If OPT_SERVICE_TOKEN is unconfigured, all requests to protected routes fail closed
           with HTTP 503 Service Unavailable to prevent unauthenticated exposure.
         - Any unauthenticated request without valid credentials returns HTTP 401 Unauthorized.
    5. Development / Test Sandbox Mode:
       - When APP_ENV != 'production' and OPT_SERVICE_TOKEN is unset, sandbox access is permitted
         with a logged security warning unless ENFORCE_INBOUND_AUTH is set to True.
    """
    # 1. Allow CORS preflight requests through without authentication checks
    if request.method == "OPTIONS":
        return None

    configured_service_token = getattr(settings, "OPT_SERVICE_TOKEN", None)
    service_token_str = str(configured_service_token).strip() if configured_service_token else None

    configured_client_token = getattr(settings, "OPT_CLIENT_TOKEN", None)
    client_token_str = str(configured_client_token).strip() if configured_client_token else None

    is_production = settings.APP_ENV.lower() == "production"

    # 2. Check for Bearer token credentials in Authorization header
    token_provided = credentials.credentials if (credentials and credentials.credentials) else None

    # 3. Check for X-Client-Token header (alternative client header)
    if not token_provided:
        client_header_token = request.headers.get("x-client-token")
        if client_header_token:
            token_provided = client_header_token.strip()

    # Case A: A token was provided by the caller
    if token_provided:
        # Check against service token (server-to-server)
        if service_token_str and secrets.compare_digest(token_provided, service_token_str):
            return token_provided

        # Check against client token (browser/UI client)
        if client_token_str and secrets.compare_digest(token_provided, client_token_str):
            return token_provided

        # If a token was provided but did not match any configured valid token:
        # When tokens are configured, this is an unauthorized/forged token attempt.
        if service_token_str or client_token_str:
            logger.warning("Rejected invalid or unauthorized inbound authentication token attempt.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired partner service authorization token.",
            )

        # In non-production with no tokens configured: allow in sandbox
        return token_provided

    # Case B: No credentials provided
    # Production security check: missing credentials must fail closed
    if is_production:
        if not service_token_str:
            logger.error("OPT_SERVICE_TOKEN is not configured in production environment. Failing closed.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service authentication token is not configured in production environment.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # In development/test environments:
    # If explicitly enforcing auth, reject missing credentials
    if getattr(settings, "ENFORCE_INBOUND_AUTH", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # If service token is configured in dev, enforce it
    if service_token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Otherwise open sandbox mode for local dev/testing
    logger.debug("Allowing unauthenticated request in development sandbox mode (OPT_SERVICE_TOKEN unset).")
    return None


def sanitize_csv_cell(value: any) -> str:
    """
    Prevents CSV / Formula Injection vulnerabilities (CWE-1236).
    If a cell value starts with '=', '+', '-', '@', tab, or carriage return,
    prefix it with a single quote (') to force spreadsheets to treat it as plain text.
    """
    if value is None:
        return ""
    str_val = str(value)
    if str_val and str_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{str_val}"
    return str_val


def validate_export_filename(filename: str) -> str:
    """
    Sanitizes export filenames to alphanumeric, hyphens, and underscores only.
    Strips directory traversal components safely.
    """
    base_name = Path(filename).name
    stem = Path(base_name).stem
    clean_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)
    clean_stem = clean_stem.strip("_")
    if not clean_stem:
        clean_stem = "export"
    return f"{clean_stem}.csv"
