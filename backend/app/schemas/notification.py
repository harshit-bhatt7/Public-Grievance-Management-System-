import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    notification_type: str
    title: str
    message: str
    grievance_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    read_at: datetime | None = None
    created_at: datetime
    link_path: str | None = None

class NotificationPreferencesOut(BaseModel):
    email_enabled: bool
    browser_enabled: bool

class NotificationPreferencesUpdate(BaseModel):
    email_enabled: bool | None = None
    browser_enabled: bool | None = None

class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(min_length=1, max_length=4000)
    p256dh: str = Field(min_length=1, max_length=1000)
    auth: str = Field(min_length=1, max_length=1000)
