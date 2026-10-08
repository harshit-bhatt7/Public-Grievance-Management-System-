import enum, uuid
from sqlalchemy import Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class ProjectStatus(str, enum.Enum):
    UPCOMING='UPCOMING'; PLANNED='PLANNED'; APPROVED='APPROVED'; IN_PROGRESS='IN_PROGRESS'; ON_HOLD='ON_HOLD'; COMPLETED='COMPLETED'; CANCELLED='CANCELLED'; DELAYED='DELAYED'
class ProjectScheduleState(str, enum.Enum):
    ON_SCHEDULE='ON_SCHEDULE'; AT_RISK='AT_RISK'; DELAYED='DELAYED'; COMPLETED='COMPLETED'
class MilestoneStatus(str, enum.Enum):
    PENDING='PENDING'; IN_PROGRESS='IN_PROGRESS'; COMPLETED='COMPLETED'; SKIPPED='SKIPPED'

class ProjectSequence(Base):
    __tablename__='project_sequences'
    id=Column(Integer, primary_key=True, autoincrement=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class GovernmentProject(Base):
    __tablename__='government_projects'
    id=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_number=Column(String(30), nullable=False, unique=True, index=True)
    name=Column(String(250), nullable=False, index=True)
    description=Column(Text, nullable=False)
    category=Column(String(100), nullable=False, index=True)
    department_id=Column(UUID(as_uuid=True), ForeignKey('departments.id', ondelete='SET NULL'), nullable=True, index=True)
    state=Column(String(100), nullable=True, index=True)
    district=Column(String(100), nullable=True, index=True)
    taluka=Column(String(100), nullable=True, index=True)
    village=Column(String(100), nullable=True, index=True)
    latitude=Column(Float, nullable=True); longitude=Column(Float, nullable=True)
    status=Column(Enum(ProjectStatus, name='project_status_enum', values_callable=lambda e:[x.value for x in e]), nullable=False, default=ProjectStatus.PLANNED, index=True)
    start_date=Column(Date, nullable=True, index=True)
    expected_completion_date=Column(Date, nullable=True, index=True)
    original_completion_date=Column(Date, nullable=True)
    actual_completion_date=Column(Date, nullable=True)
    estimated_cost=Column(Float, nullable=True); approved_cost=Column(Float, nullable=True); revised_cost=Column(Float, nullable=True); amount_spent=Column(Float, nullable=True)
    funding_source=Column(String(200), nullable=True)
    project_manager_name=Column(String(150), nullable=True); project_manager_designation=Column(String(100), nullable=True)
    responsible_team=Column(String(200), nullable=True); responsible_personnel_count=Column(Integer, nullable=True)
    progress_percent=Column(Float, nullable=False, default=0)
    current_stage=Column(String(250), nullable=True); next_milestone=Column(String(250), nullable=True)
    is_public=Column(Boolean, nullable=False, default=True, index=True)
    created_by=Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    department=relationship('Department')
    creator=relationship('User')
    milestones=relationship('ProjectMilestone', back_populates='project', cascade='all, delete-orphan', order_by='ProjectMilestone.planned_date, ProjectMilestone.created_at')
    updates=relationship('ProjectUpdate', back_populates='project', cascade='all, delete-orphan', order_by='ProjectUpdate.created_at')
    documents=relationship('ProjectDocument', back_populates='project', cascade='all, delete-orphan', order_by='ProjectDocument.created_at')
    photos=relationship('ProjectPhoto', back_populates='project', cascade='all, delete-orphan', order_by='ProjectPhoto.photo_date, ProjectPhoto.created_at')
    grievance_links=relationship('ProjectGrievanceLink', back_populates='project', cascade='all, delete-orphan')
    followers=relationship('ProjectFollower', back_populates='project', cascade='all, delete-orphan')

class ProjectMilestone(Base):
    __tablename__='project_milestones'
    id=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id=Column(UUID(as_uuid=True), ForeignKey('government_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    title=Column(String(250), nullable=False); description=Column(Text, nullable=True)
    planned_date=Column(Date, nullable=True, index=True); actual_date=Column(Date, nullable=True)
    status=Column(Enum(MilestoneStatus, name='project_milestone_status_enum', values_callable=lambda e:[x.value for x in e]), nullable=False, default=MilestoneStatus.PENDING)
    completion_percent=Column(Float, nullable=False, default=0); evidence=Column(Text, nullable=True)
    updated_at=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False); created_at=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    project=relationship('GovernmentProject', back_populates='milestones')

class ProjectUpdate(Base):
    __tablename__='project_updates'
    id=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id=Column(UUID(as_uuid=True), ForeignKey('government_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    kind=Column(String(80), nullable=False); title=Column(String(250), nullable=False); description=Column(Text, nullable=True)
    old_value=Column(Text, nullable=True); new_value=Column(Text, nullable=True)
    updated_by=Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    project=relationship('GovernmentProject', back_populates='updates'); actor=relationship('User')

class ProjectDocument(Base):
    __tablename__='project_documents'
    id=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id=Column(UUID(as_uuid=True), ForeignKey('government_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    uploaded_by=Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    file_name=Column(String(255), nullable=False); file_type=Column(String(100), nullable=False); file_size=Column(Integer, nullable=False); file_path=Column(String(500), nullable=False); file_hash=Column(String(64), nullable=False)
    document_type=Column(String(100), nullable=True); is_public=Column(Boolean, nullable=False, default=True, index=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    project=relationship('GovernmentProject', back_populates='documents'); uploader=relationship('User')

class ProjectPhoto(Base):
    __tablename__='project_photos'
    id=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id=Column(UUID(as_uuid=True), ForeignKey('government_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    uploaded_by=Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    file_name=Column(String(255), nullable=False); file_type=Column(String(100), nullable=False); file_size=Column(Integer, nullable=False); file_path=Column(String(500), nullable=False); file_hash=Column(String(64), nullable=False)
    photo_date=Column(Date, nullable=True, index=True); milestone_id=Column(UUID(as_uuid=True), ForeignKey('project_milestones.id', ondelete='SET NULL'), nullable=True); caption=Column(String(500), nullable=True); location_label=Column(String(250), nullable=True)
    is_public=Column(Boolean, nullable=False, default=True, index=True); created_at=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    project=relationship('GovernmentProject', back_populates='photos'); uploader=relationship('User'); milestone=relationship('ProjectMilestone')

class ProjectGrievanceLink(Base):
    __tablename__='project_grievance_links'
    id=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id=Column(UUID(as_uuid=True), ForeignKey('government_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    grievance_id=Column(UUID(as_uuid=True), ForeignKey('grievances.id', ondelete='CASCADE'), nullable=False, index=True)
    linked_by=Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    project=relationship('GovernmentProject', back_populates='grievance_links'); grievance=relationship('Grievance'); linker=relationship('User')
    __table_args__=(UniqueConstraint('project_id','grievance_id',name='uq_project_grievance_link'),)

class ProjectFollower(Base):
    __tablename__='project_followers'
    id=Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id=Column(UUID(as_uuid=True), ForeignKey('government_projects.id',ondelete='CASCADE'), nullable=False, index=True)
    user_id=Column(UUID(as_uuid=True), ForeignKey('users.id',ondelete='CASCADE'), nullable=False, index=True)
    created_at=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    project=relationship('GovernmentProject', back_populates='followers'); user=relationship('User')
    __table_args__=(UniqueConstraint('project_id','user_id',name='uq_project_follower'),)
