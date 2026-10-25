import json
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.audit_event import AuditEvent


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            details_json=json.dumps(details or {}),
        )
        self.db.add(event)
        self.db.commit()
        return event
