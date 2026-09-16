"""Import every model here so Base.metadata knows about all tables
(Alembic autogenerate and Base.metadata.create_all both rely on this)."""

from app.models.base import Base, utcnow
from app.models.blocker import BLOCKER_SEVERITIES, Blocker
from app.models.client import CLIENT_SEGMENTS, Client, ClientStageHistory
from app.models.meeting import Meeting, meeting_attendees
from app.models.milestone import MILESTONE_STATUSES, Milestone
from app.models.note import Note
from app.models.stage import PIPELINE_STAGES, Stage
from app.models.user import USER_ROLES, User

__all__ = [
    "BLOCKER_SEVERITIES",
    "CLIENT_SEGMENTS",
    "MILESTONE_STATUSES",
    "PIPELINE_STAGES",
    "USER_ROLES",
    "Base",
    "Blocker",
    "Client",
    "ClientStageHistory",
    "Meeting",
    "Milestone",
    "Note",
    "Stage",
    "User",
    "meeting_attendees",
    "utcnow",
]
