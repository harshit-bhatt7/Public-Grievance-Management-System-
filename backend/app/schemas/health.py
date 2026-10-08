"""
Response schemas for the health-check endpoints.
"""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class DetailedHealthResponse(BaseModel):
    status: str
    database: str
