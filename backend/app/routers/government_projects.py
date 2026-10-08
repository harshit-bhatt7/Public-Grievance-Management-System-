from datetime import date
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.user import User
from app.models.government_project import *
from app.schemas.government_project import *
from app.services import government_project_service as svc
from app.services.audit_service import record_audit_event
from app.models.audit_log import AuditAction, AuditEntityType
from app.utils.file_storage import save_project_file, get_upload_root
from fastapi.responses import FileResponse
from pathlib import Path

router=APIRouter(tags=['government-projects'])
admin= require_role('admin')
manager=require_role('admin','officer')

def out(db,p,user=None):
    d=svc.get(db,p.id,public=False).department
    return ProjectOut.model_validate({**{c.name:getattr(p,c.name) for c in p.__table__.columns},'department_name':d.name if d else None,'schedule_state':svc._schedule(p),'remaining_amount':((p.revised_cost if p.revised_cost is not None else p.approved_cost)-p.amount_spent) if (p.revised_cost is not None or p.approved_cost is not None) and p.amount_spent is not None else None})

def detail(db,p,user=None):
    x=out(db,p,user).model_dump(); x.update({'milestones':[MilestoneOut.model_validate(m).model_dump() for m in p.milestones], 'timeline':svc.timeline(db,p), 'documents':[{'id':str(d.id),'file_name':d.file_name,'document_type':d.document_type,'created_at':d.created_at} for d in p.documents if d.is_public], 'photos':[{'id':str(ph.id),'file_name':ph.file_name,'caption':ph.caption,'photo_date':ph.photo_date,'location_label':ph.location_label,'created_at':ph.created_at} for ph in p.photos if ph.is_public], 'grievance_summary':svc.grievance_summary(db,p), 'is_following': bool(user and db.query(ProjectFollower).filter_by(project_id=p.id,user_id=user.id).first())})
    return x

@router.get('/api/public/projects', response_model=list[ProjectOut])
def public_projects(q:Optional[str]=None,category:Optional[str]=None,department_id:Optional[UUID]=None,state:Optional[str]=None,district:Optional[str]=None,taluka:Optional[str]=None,village:Optional[str]=None,status:Optional[str]=None,start_from:Optional[date]=None,start_to:Optional[date]=None,completion_from:Optional[date]=None,completion_to:Optional[date]=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    rows=svc.list_projects(db,locals(),True); return [out(db,p) for p in rows]

@router.get('/api/public/projects/categories')
def public_project_categories(): return {'items':CATEGORIES}
@router.get('/api/public/projects/departments')
def public_project_departments(db:Session=Depends(get_db)):
    from app.models.department import Department
    return {'items':[{'id':str(d.id),'name':d.name} for d in db.query(Department).filter(Department.is_active.is_(True)).order_by(Department.name).all()]}
@router.get('/api/public/projects/statistics')
def public_project_stats(db:Session=Depends(get_db)): return svc.stats(db)
@router.get('/api/public/projects/performance')
def public_project_performance(db:Session=Depends(get_db)): return svc.performance(db)
@router.get('/api/public/projects/{project_id}',response_model=ProjectDetail)
def public_project_detail(project_id:UUID,db:Session=Depends(get_db)): return detail(db,svc.get(db,project_id,True))
@router.get('/api/public/projects/{project_id}/documents/{document_id}')
def public_document(project_id:UUID,document_id:UUID,db:Session=Depends(get_db)):
    from fastapi import HTTPException
    p=svc.get(db,project_id,True); d=db.query(ProjectDocument).filter_by(id=document_id,project_id=p.id,is_public=True).first()
    if not d: raise HTTPException(404,'Document not found.')
    root=get_upload_root().resolve(); path=(root/d.file_path).resolve()
    if root not in path.parents or not path.is_file(): raise HTTPException(404,'Document not found.')
    return FileResponse(path,media_type=d.file_type,filename=d.file_name)

@router.get('/api/public/projects/{project_id}/photos/{photo_id}')
def public_photo(project_id:UUID,photo_id:UUID,db:Session=Depends(get_db)):
    from fastapi import HTTPException
    p=svc.get(db,project_id,True); ph=db.query(ProjectPhoto).filter_by(id=photo_id,project_id=p.id,is_public=True).first()
    if not ph: raise HTTPException(404,'Photo not found.')
    root=get_upload_root().resolve(); path=(root/ph.file_path).resolve()
    if root not in path.parents or not path.is_file(): raise HTTPException(404,'Photo not found.')
    return FileResponse(path,media_type=ph.file_type,filename=ph.file_name)

@router.get('/api/public/projects/{project_id}/timeline')
def public_project_timeline(project_id:UUID,db:Session=Depends(get_db)): return {'items':svc.timeline(db,svc.get(db,project_id,True))}
@router.get('/api/public/projects/{project_id}/grievances')
def public_project_grievances(project_id:UUID,db:Session=Depends(get_db)): return svc.grievance_summary(db,svc.get(db,project_id,True))

@router.post('/api/projects/{project_id}/follow')
def follow(project_id:UUID,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    if user.user_type.value!='citizen': from fastapi import HTTPException; raise HTTPException(403,'Only citizens can follow public projects.')
    return {'following':svc.follow(db,user,project_id)}
@router.delete('/api/projects/{project_id}/follow')
def unfollow(project_id:UUID,db:Session=Depends(get_db),user:User=Depends(get_current_user)): return {'following':svc.unfollow(db,user,project_id)}
@router.get('/api/projects/following')
def following(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    rows=db.query(GovernmentProject).join(ProjectFollower,ProjectFollower.project_id==GovernmentProject.id).filter(ProjectFollower.user_id==user.id,GovernmentProject.is_public.is_(True)).all(); return [out(db,p,user) for p in rows]

@router.get('/api/admin/projects',response_model=list[ProjectOut])
def admin_projects(db:Session=Depends(get_db),user:User=Depends(admin)): return [out(db,p,user) for p in svc.list_projects(db,{},False)]
@router.post('/api/admin/projects',response_model=ProjectOut,status_code=201)
def admin_create(payload:ProjectCreate,db:Session=Depends(get_db),user:User=Depends(admin)): return out(db,svc.create(db,user,payload),user)
@router.get('/api/admin/projects/{project_id}',response_model=ProjectDetail)
def admin_detail(project_id:UUID,db:Session=Depends(get_db),user:User=Depends(admin)): return detail(db,svc.get(db,project_id,False),user)
@router.patch('/api/admin/projects/{project_id}',response_model=ProjectOut)
def admin_update(project_id:UUID,payload:ProjectUpdateIn,db:Session=Depends(get_db),user:User=Depends(admin)): return out(db,svc.update(db,user,svc.get(db,project_id,False),payload),user)

@router.post('/api/admin/projects/{project_id}/milestones',response_model=MilestoneOut,status_code=201)
def add_milestone(project_id:UUID,payload:MilestoneIn,db:Session=Depends(get_db),user:User=Depends(admin)):
    p=svc.get(db,project_id,False); m=ProjectMilestone(project_id=p.id,**payload.model_dump()); db.add(m); db.flush(); record_audit_event(db,action=AuditAction.PROJECT_MILESTONE_UPDATED,entity_type=AuditEntityType.GOVERNMENT_PROJECT,actor_id=user.id,entity_id=p.id,new_value={'milestone_id':str(m.id),'title':m.title}); db.commit(); db.refresh(m); return m
@router.patch('/api/admin/projects/{project_id}/milestones/{milestone_id}',response_model=MilestoneOut)
def edit_milestone(project_id:UUID,milestone_id:UUID,payload:MilestoneIn,db:Session=Depends(get_db),user:User=Depends(admin)):
    m=db.query(ProjectMilestone).filter_by(id=milestone_id,project_id=project_id).first()
    from fastapi import HTTPException
    if not m: raise HTTPException(404,'Milestone not found.')
    for k,v in payload.model_dump().items(): setattr(m,k,v)
    record_audit_event(db,action=AuditAction.PROJECT_MILESTONE_UPDATED,entity_type=AuditEntityType.GOVERNMENT_PROJECT,actor_id=user.id,entity_id=project_id,new_value={'milestone_id':str(m.id),'status':m.status.value}); db.commit(); db.refresh(m); return m

@router.post('/api/admin/projects/{project_id}/documents',status_code=201)
def add_document(project_id:UUID,file:UploadFile=File(...),document_type:Optional[str]=None,is_public:bool=True,db:Session=Depends(get_db),user:User=Depends(admin)):
    p=svc.get(db,project_id,False); meta=save_project_file(str(p.id),file); d=ProjectDocument(project_id=p.id,uploaded_by=user.id,document_type=document_type,is_public=is_public,**meta); db.add(d); record_audit_event(db,action=AuditAction.PROJECT_DOCUMENT_ADDED,entity_type=AuditEntityType.GOVERNMENT_PROJECT,actor_id=user.id,entity_id=p.id,new_value={'document_id':str(d.id),'public':is_public}); db.commit(); return {'id':str(d.id),'file_name':d.file_name,'is_public':d.is_public}
@router.post('/api/admin/projects/{project_id}/photos',status_code=201)
def add_photo(project_id:UUID,file:UploadFile=File(...),caption:Optional[str]=None,photo_date:Optional[date]=None,milestone_id:Optional[UUID]=None,location_label:Optional[str]=None,is_public:bool=True,db:Session=Depends(get_db),user:User=Depends(admin)):
    p=svc.get(db,project_id,False); meta=save_project_file(str(p.id),file,images_only=True); ph=ProjectPhoto(project_id=p.id,uploaded_by=user.id,caption=caption,photo_date=photo_date,milestone_id=milestone_id,location_label=location_label,is_public=is_public,**meta); db.add(ph); record_audit_event(db,action=AuditAction.PROJECT_PHOTO_ADDED,entity_type=AuditEntityType.GOVERNMENT_PROJECT,actor_id=user.id,entity_id=p.id,new_value={'photo_id':str(ph.id),'public':is_public}); db.commit(); return {'id':str(ph.id),'file_name':ph.file_name,'is_public':ph.is_public}

@router.post('/api/admin/projects/{project_id}/grievances')
def link_grievance(project_id:UUID,grievance_id:UUID,db:Session=Depends(get_db),user:User=Depends(admin)):
    from fastapi import HTTPException
    p=svc.get(db,project_id,False); g=db.query(__import__('app.models.grievance',fromlist=['Grievance']).Grievance).filter_by(id=grievance_id).first()
    if not g: raise HTTPException(404,'Grievance not found.')
    if db.query(ProjectGrievanceLink).filter_by(project_id=p.id,grievance_id=g.id).first(): return {'linked':True,'created':False}
    db.add(ProjectGrievanceLink(project_id=p.id,grievance_id=g.id,linked_by=user.id)); record_audit_event(db,action=AuditAction.PROJECT_LINKED_TO_GRIEVANCE,entity_type=AuditEntityType.GOVERNMENT_PROJECT,actor_id=user.id,entity_id=p.id,new_value={'grievance_id':str(g.id)}); db.commit(); return {'linked':True,'created':True}
