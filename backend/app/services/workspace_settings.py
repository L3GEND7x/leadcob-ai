"""Tenant preferences, independent of billing and legacy settings."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.account_access import authorize
from app.db.models import WorkspaceSettings


def get_settings(db: Session, token: str, organization_id: int):
    principal = authorize(db, token, organization_id, 'read')
    item = db.get(WorkspaceSettings, principal.organization_id)
    if item is None:
        return dict(timezone='America/Manaus', followup_days=[3, 7, 14], default_page_size=50)
    return dict(timezone=item.timezone, followup_days=list(item.followup_days),
                default_page_size=item.default_page_size)


def update_settings(db: Session, token: str, organization_id: int, csrf: str, *,
                    timezone_name: str, followup_days: list[int], default_page_size: int):
    principal = authorize(db, token, organization_id, 'manage_members', csrf=csrf)
    if not isinstance(timezone_name, str) or len(timezone_name) > 80:
        raise ValueError('Invalid timezone')
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError('Invalid timezone') from exc
    if (not isinstance(followup_days, list) or not 1 <= len(followup_days) <= 10
            or any(type(day) is not int or not 1 <= day <= 365 for day in followup_days)
            or followup_days != sorted(set(followup_days))):
        raise ValueError('Invalid follow-up schedule')
    if type(default_page_size) is not int or not 10 <= default_page_size <= 250:
        raise ValueError('Invalid page size')
    item = db.get(WorkspaceSettings, principal.organization_id)
    if item is None:
        item = WorkspaceSettings(organization_id=principal.organization_id)
        db.add(item)
    item.timezone = timezone_name
    item.followup_days = list(followup_days)
    item.default_page_size = default_page_size
    item.updated_by = principal.user_id
    item.updated_at = datetime.now(timezone.utc)
    db.flush()
    return get_settings(db, token, organization_id)
