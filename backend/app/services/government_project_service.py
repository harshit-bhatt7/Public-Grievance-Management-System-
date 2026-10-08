from datetime import date, datetime, timezone
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.models.government_project import *
from app.models.department import Department
from app.models.grievance import Grievance, GrievanceStatus
from app.models.resolution import ResolutionDispute
from app.models.user import User
from app.models.notification import Notification, NotificationType
from app.services.audit_service import record_audit_event
from app.models.audit_log import AuditAction, AuditEntityType
from app.services import notification_service

CATEGORIES={'Roads & Potholes','Drainage & Sewage','Water Supply','Electricity','Street Lights','Garbage & Waste','Public Transport','Public Safety','Government Services','Healthcare','Education','Housing','Environment','Other'}
VALID_TRANSITIONS={
 'UPCOMING':{'PLANNED','APPROVED','CANCELLED'}, 'PLANNED':{'APPROVED','IN_PROGRESS','ON_HOLD','CANCELLED'}, 'APPROVED':{'IN_PROGRESS','ON_HOLD','CANCELLED'},
 'IN_PROGRESS':{'ON_HOLD','COMPLETED','DELAYED','CANCELLED'}, 'ON_HOLD':{'IN_PROGRESS','CANCELLED'}, 'DELAYED':{'IN_PROGRESS','COMPLETED','ON_HOLD','CANCELLED'}, 'COMPLETED':set(), 'CANCELLED':set()
}

def _schedule(p, today=None):
    today=today or date.today()
    if p.actual_completion_date or p.status == ProjectStatus.COMPLETED: return ProjectScheduleState.COMPLETED.value
    if p.expected_completion_date and today>p.expected_completion_date: return ProjectScheduleState.DELAYED.value
    if p.expected_completion_date and p.start_date and today>=p.start_date:
        total=max((p.expected_completion_date-p.start_date).days,1); elapsed=max((today-p.start_date).days,0); expected=min(100,elapsed*100/total)
        if p.progress_percent+15 < expected: return ProjectScheduleState.AT_RISK.value
    return ProjectScheduleState.ON_SCHEDULE.value

def _validate_status(old,new):
    if old==new:return
    if new not in VALID_TRANSITIONS.get(old,set()): raise HTTPException(409,f'Invalid project status transition: {old} -> {new}')

def _next_number(db):
    row=ProjectSequence(); db.add(row); db.flush(); return f'PRJ-{datetime.now(timezone.utc).year}-{row.id:06d}'

def create(db,user,data):
    if data.category not in CATEGORIES: raise HTTPException(400,'Unsupported project category.')
    if data.department_id and not db.query(Department).filter(Department.id==data.department_id,Department.is_active.is_(True)).first(): raise HTTPException(400,'Invalid or inactive department.')
    p=GovernmentProject(project_number=_next_number(db),created_by=user.id,**data.model_dump())
    p.original_completion_date=p.expected_completion_date
    db.add(p); db.flush()
    record_audit_event(db,action=AuditAction.PROJECT_CREATED,entity_type=AuditEntityType.GOVERNMENT_PROJECT,actor_id=user.id,entity_id=p.id,new_value={'project_number':p.project_number,'status':p.status.value,'name':p.name})
    db.commit(); db.refresh(p); return p

def update(db,user,p,data):
    values=data.model_dump(exclude_unset=True)
    if 'category' in values and values['category'] not in CATEGORIES: raise HTTPException(400,'Unsupported project category.')
    if 'department_id' in values and values['department_id'] and not db.query(Department).filter(Department.id==values['department_id'],Department.is_active.is_(True)).first(): raise HTTPException(400,'Invalid or inactive department.')
    if 'status' in values:
        new=values['status']; old=p.status.value; _validate_status(old,new)
        if new=='COMPLETED' and p.progress_percent<100: raise HTTPException(409,'A project cannot be marked completed until progress is 100%.')
    changes={}
    for k,v in values.items():
        if v is not None or k in ('department_id','actual_completion_date','is_public'):
            old=getattr(p,k); oldv=getattr(old,'value',old); newv=getattr(v,'value',v)
            if oldv!=newv: changes[k]=(oldv,newv); setattr(p,k,v)
    if 'expected_completion_date' in changes and p.original_completion_date is None: p.original_completion_date=changes['expected_completion_date'][0]
    if p.status==ProjectStatus.COMPLETED and p.actual_completion_date is None: p.actual_completion_date=date.today()
    if changes:
        db.add(ProjectUpdate(project_id=p.id,kind='PROJECT_UPDATED',title='Project updated',description='Authoritative project information changed.',old_value=str({k:v[0] for k,v in changes.items()}),new_value=str({k:v[1] for k,v in changes.items()}),updated_by=user.id))
        if 'status' in changes and changes['status'][1] == 'COMPLETED': action=AuditAction.PROJECT_COMPLETED
        elif 'status' in changes: action=AuditAction.PROJECT_STATUS_CHANGED
        elif 'progress_percent' in changes: action=AuditAction.PROJECT_PROGRESS_UPDATED
        elif 'department_id' in changes: action=AuditAction.PROJECT_DEPARTMENT_CHANGED
        else: action=AuditAction.PROJECT_UPDATED
        record_audit_event(db,action=action,entity_type=AuditEntityType.GOVERNMENT_PROJECT,actor_id=user.id,entity_id=p.id,old_value={k:v[0] for k,v in changes.items()},new_value={k:v[1] for k,v in changes.items()})
    db.commit(); db.refresh(p)
    if changes:
        try:
            from app.services.notification_service import notify_project_followers
            notify_project_followers(p.id, 'Government project updated', f'{p.name} has a new public project update.', 'updated')
        except Exception:
            pass
    return p

def get(db,pid,public=True):
    q=db.query(GovernmentProject).options(joinedload(GovernmentProject.department)).filter(GovernmentProject.id==pid)
    if public:q=q.filter(GovernmentProject.is_public.is_(True))
    p=q.first()
    if not p: raise HTTPException(404,'Project not found.')
    return p

def list_projects(db,params,public=True):
    q=db.query(GovernmentProject).options(joinedload(GovernmentProject.department))
    if public:q=q.filter(GovernmentProject.is_public.is_(True))
    if params.get('q'): term=f"%{params['q']}%"; q=q.filter(or_(GovernmentProject.name.ilike(term),GovernmentProject.project_number.ilike(term)))
    for key in ('category','state','district','taluka','village'):
        if params.get(key): q=q.filter(getattr(GovernmentProject,key)==params[key])
    if params.get('department_id'): q=q.filter(GovernmentProject.department_id==params['department_id'])
    if params.get('status'): q=q.filter(GovernmentProject.status==params['status'])
    if params.get('start_from'): q=q.filter(GovernmentProject.start_date>=params['start_from'])
    if params.get('start_to'): q=q.filter(GovernmentProject.start_date<=params['start_to'])
    if params.get('completion_from'): q=q.filter(GovernmentProject.expected_completion_date>=params['completion_from'])
    if params.get('completion_to'): q=q.filter(GovernmentProject.expected_completion_date<=params['completion_to'])
    return q.order_by(GovernmentProject.updated_at.desc()).limit(min(int(params.get('limit',50)),100)).offset(max(int(params.get('offset',0)),0)).all()

def timeline(db,p):
    items=[]
    if p.start_date: items.append({'date':p.start_date.isoformat(),'title':'Project start','kind':'PROJECT_START'})
    for m in p.milestones:
        d=m.actual_date or m.planned_date
        if d: items.append({'date':d.isoformat(),'title':m.title,'description':m.description,'status':m.status.value,'completion_percent':m.completion_percent,'kind':'MILESTONE'})
    for u in p.updates: items.append({'date':u.created_at.date().isoformat(),'title':u.title,'description':u.description,'kind':u.kind})
    if p.expected_completion_date: items.append({'date':p.expected_completion_date.isoformat(),'title':'Expected completion','kind':'EXPECTED_COMPLETION'})
    if p.actual_completion_date: items.append({'date':p.actual_completion_date.isoformat(),'title':'Project completed','kind':'COMPLETED'})
    return sorted(items,key=lambda x:x['date'])

def grievance_summary(db,p):
    ids=[x.grievance_id for x in p.grievance_links]
    if not ids:return {'total':0,'resolved':0,'ongoing':0,'pending':0,'disputed':0,'categories':[],'trend':[]}
    rows=db.query(Grievance.status,func.count(Grievance.id)).filter(Grievance.id.in_(ids)).group_by(Grievance.status).all(); counts={getattr(s,'value',s):int(c) for s,c in rows}
    resolved=counts.get('RESOLVED',0)+counts.get('CLOSED',0); ongoing=counts.get('IN_PROGRESS',0); pending=sum(counts.get(x,0) for x in ('SUBMITTED','UNDER_REVIEW','ASSIGNED')); disputed=db.query(func.count(ResolutionDispute.id)).filter(ResolutionDispute.grievance_id.in_(ids)).scalar() or 0
    return {'total':len(ids),'resolved':resolved,'ongoing':ongoing,'pending':pending,'disputed':disputed,'categories':[],'trend':[]}

def stats(db):
    projects=db.query(GovernmentProject).filter(GovernmentProject.is_public.is_(True)).all(); total=len(projects); states={p.project_number:_schedule(p) for p in projects}
    active=sum(1 for p in projects if p.status in (ProjectStatus.IN_PROGRESS,ProjectStatus.ON_HOLD,ProjectStatus.DELAYED)); completed=sum(1 for p in projects if states[p.project_number]=='COMPLETED'); delayed=sum(1 for p in projects if states[p.project_number]=='DELAYED'); upcoming=sum(1 for p in projects if p.status in (ProjectStatus.UPCOMING,ProjectStatus.PLANNED,ProjectStatus.APPROVED))
    def grouped(key, label='name'):
        d={}
        for p in projects:
            value=getattr(p,key) or 'Not specified'; d.setdefault(value,{'name':value,'total':0,'completed':0,'delayed':0})
            d[value]['total']+=1; d[value]['completed']+=int(states[p.project_number]=='COMPLETED'); d[value]['delayed']+=int(states[p.project_number]=='DELAYED')
        return sorted(d.values(),key=lambda x:x['total'],reverse=True)
    dep={d.id:d.name for d in db.query(Department).all()}
    by_department=[]
    for p in projects:
        name=dep.get(p.department_id,'Not specified'); row=next((x for x in by_department if x['name']==name),None)
        if not row: row={'name':name,'total':0,'completed':0,'delayed':0}; by_department.append(row)
        row['total']+=1; row['completed']+=int(states[p.project_number]=='COMPLETED'); row['delayed']+=int(states[p.project_number]=='DELAYED')
    return {'total_projects':total,'upcoming_projects':upcoming,'active_projects':active,'completed_projects':completed,'delayed_projects':delayed,'by_department':sorted(by_department,key=lambda x:x['total'],reverse=True),'by_category':grouped('category'),'by_state':grouped('state')}

def performance(db):
    ps=db.query(GovernmentProject).filter(GovernmentProject.is_public.is_(True)).all(); finished=[p for p in ps if p.actual_completion_date and p.start_date]
    ontime=[p for p in finished if p.expected_completion_date and p.actual_completion_date<=p.expected_completion_date]; delays=[(p.actual_completion_date-p.expected_completion_date).days for p in finished if p.expected_completion_date and p.actual_completion_date>p.expected_completion_date]
    return {'on_time_completion_rate':round(len(ontime)*100/len(finished),2) if finished else None,'delayed_project_rate':round(sum(_schedule(p)=='DELAYED' for p in ps)*100/len(ps),2) if ps else None,'average_delay_days':round(sum(delays)/len(delays),2) if delays else 0,'average_completion_duration_days':round(sum((p.actual_completion_date-p.start_date).days for p in finished)/len(finished),2) if finished else None,'average_progress':round(sum(p.progress_percent for p in ps)/len(ps),2) if ps else 0}

def follow(db,user,pid):
    if not get(db,pid,True): raise HTTPException(404,'Project not found.')
    row=db.query(ProjectFollower).filter_by(project_id=pid,user_id=user.id).first()
    if row:return True
    db.add(ProjectFollower(project_id=pid,user_id=user.id)); db.commit(); return True

def unfollow(db,user,pid):
    row=db.query(ProjectFollower).filter_by(project_id=pid,user_id=user.id).first()
    if not row:return False
    db.delete(row); db.commit(); return True
