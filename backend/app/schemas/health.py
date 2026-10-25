from typing import Optional, List
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str
    environment: str


class IntegrationHealthResponse(BaseModel):
    status: str
    provider_mode: str
    is_mock: bool
    configured_api_base_url: str
    last_successful_request: Optional[str] = None
    feedback_delivery_status: str
    recent_errors: List[str] = []
    service_version: str
    environment: str
