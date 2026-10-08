"""Step 14 government project transparency tests."""
import uuid
from datetime import date, timedelta
from app.core.deps import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models.department import Department
from app.models.government_project import GovernmentProject, ProjectFollower, ProjectStatus
from app.models.user import User, UserType
from app.routers import government_projects


def _admin(db):
    u=User(name='Project Admin',email=f'pa-{uuid.uuid4()}@example.com',password_hash=hash_password('Admin12345'),user_type=UserType.ADMIN,is_active=True);db.add(u);db.commit();return u

def _citizen(db):
    u=User(name='Citizen',email=f'cit-{uuid.uuid4()}@example.com',password_hash=hash_password('Citizen12345'),user_type=UserType.CITIZEN,is_active=True);db.add(u);db.commit();return u

def _override_admin(admin): app.dependency_overrides[government_projects.admin]=lambda:admin

def test_public_project_listing_requires_no_login(client,db_session):
    a=_admin(db_session);_override_admin(a)
    r=client.post('/api/admin/projects',json={'name':'Village Road','description':'Road improvement','category':'Roads & Potholes','status':'IN_PROGRESS','progress_percent':40})
    assert r.status_code==201
    app.dependency_overrides.clear()
    r=client.get('/api/public/projects');assert r.status_code==200;assert r.json()[0]['project_number'].startswith('PRJ-')

def test_project_status_transition_and_delay_are_server_side(client,db_session):
    a=_admin(db_session);_override_admin(a)
    r=client.post('/api/admin/projects',json={'name':'Delayed Road','description':'Road','category':'Roads & Potholes','status':'IN_PROGRESS','progress_percent':40,'start_date':str(date.today()-timedelta(days=60)),'expected_completion_date':str(date.today()-timedelta(days=1))})
    assert r.status_code==201; p=r.json(); assert p['schedule_state']=='DELAYED'
    bad=client.patch(f"/api/admin/projects/{p['id']}",json={'status':'PLANNED'});assert bad.status_code==409
    app.dependency_overrides.clear()

def test_project_grievance_link_is_explicit(client,db_session):
    a=_admin(db_session);_override_admin(a)
    p=client.post('/api/admin/projects',json={'name':'Water Project','description':'Water','category':'Water Supply'}).json()
    from app.models.category import Category
    from app.models.grievance import Grievance
    cat=db_session.query(Category).filter(Category.name=='Water Supply').first(); c=_citizen(db_session)
    g=Grievance(grievance_number=f'GRV-TEST-{uuid.uuid4().hex[:8]}',citizen_id=c.id,category_id=cat.id,title='Water issue',description='Issue')
    db_session.add(g);db_session.commit()
    r=client.post(f"/api/admin/projects/{p['id']}/grievances?grievance_id={g.id}");assert r.status_code==200
    public=client.get(f"/api/public/projects/{p['id']}/grievances");assert public.status_code==200;assert public.json()['total']==1
    app.dependency_overrides.clear()

def test_project_following_is_private_and_unique(client,db_session):
    a=_admin(db_session);c=_citizen(db_session);_override_admin(a)
    p=client.post('/api/admin/projects',json={'name':'Follow Me','description':'Public','category':'Environment'}).json();app.dependency_overrides.clear()
    app.dependency_overrides[government_projects.get_current_user]=lambda:c
    r=client.post(f"/api/projects/{p['id']}/follow");assert r.status_code==200 and r.json()['following'] is True
    r=client.post(f"/api/projects/{p['id']}/follow");assert r.status_code==200 and r.json()['following'] is True
    assert db_session.query(ProjectFollower).count()==1
    r=client.get('/api/projects/following');assert r.status_code==200 and len(r.json())==1
    app.dependency_overrides.clear()

def test_citizen_cannot_create_project(client,db_session):
    c=_citizen(db_session);app.dependency_overrides[government_projects.admin]=lambda: c
    r=client.post('/api/admin/projects',json={'name':'Nope','description':'Nope','category':'Other'});assert r.status_code==403
    app.dependency_overrides.clear()
