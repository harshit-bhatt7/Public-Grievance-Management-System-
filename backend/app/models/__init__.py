"""
SQLAlchemy models package.

Importing every model module here ensures they are registered on
`Base.metadata` before Alembic autogenerate or `create_all` runs.

Future steps will add: grievance.py, category.py, attachment.py,
audit_log.py, resolution.py, notification.py, etc. — each imported
below in the same way, without touching existing model files.
"""
from app.models.user import User          # noqa: F401
from app.models.role import Role, UserRole  # noqa: F401
from app.models.citizen_profile import CitizenProfile  # noqa: F401
from app.models.department import Department  # noqa: F401
from app.models.officer_profile import OfficerProfile  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.grievance import Grievance, GrievanceSequence  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.grievance_status_history import GrievanceStatusHistory  # noqa: F401
from app.models.privacy_access_log import PrivacyAccessLog  # noqa: F401
from app.models.identity_reveal_request import IdentityRevealRequest  # noqa: F401
from app.models.grievance_assignment import GrievanceAssignment  # noqa: F401
from app.models.officer_assignment import OfficerAssignment  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.ai_intelligence import (AIAnalysis, AIRecommendation, AIProcessingLog, AIComplaintCluster, AIClusterMember, AISLAPrediction, AIAlert, AIResponseDraft)  # noqa: F401,E402

from app.models.resolution import Resolution, ResolutionEvidence, ResolutionDispute, ResolutionFeedback  # noqa: F401

from app.models.notification import Notification, NotificationPreference, PushSubscription
from app.models.public_statistics import CivicRankingConfig  # noqa: F401
from app.models.government_project import (GovernmentProject, ProjectSequence, ProjectMilestone, ProjectUpdate, ProjectDocument, ProjectPhoto, ProjectGrievanceLink, ProjectFollower)  # noqa: F401

from app.models.existing_work import ExistingWorkMatch, ExistingWorkMatchType, ExistingWorkCitizenAction, ExistingWorkReviewState  # noqa: F401
