"""Step 13 unauthenticated, aggregate-only public statistics API."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services import public_statistics_service as svc
router=APIRouter(prefix="/api/public/statistics",tags=["public-statistics"])

def _valid_uuid(name, value):
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(400, f"Invalid {name}")
    return value

def filters(state=None,district=None,taluka=None,village=None,category_id=None,department_id=None):
    if category_id: _valid_uuid("category_id", category_id)
    if department_id: _valid_uuid("department_id", department_id)
    return {k:v for k,v in locals().items() if v}

@router.get("")
@router.get("/summary")
def get_summary(state:str|None=None,district:str|None=None,taluka:str|None=None,village:str|None=None,category_id:str|None=None,department_id:str|None=None,db:Session=Depends(get_db)):
    return svc.summary(db,filters(state,district,taluka,village,category_id,department_id))
@router.get("/categories")
def categories(state:str|None=None,district:str|None=None,taluka:str|None=None,village:str|None=None,db:Session=Depends(get_db)): return svc.breakdown(db,filters(state,district,taluka,village),"category")
@router.get("/departments")
def departments(state:str|None=None,district:str|None=None,taluka:str|None=None,village:str|None=None,db:Session=Depends(get_db)): return svc.breakdown(db,filters(state,district,taluka,village),"department")
@router.get("/trends")
def trend(period:str=Query("monthly",pattern="^(daily|weekly|monthly|yearly)$"),state:str|None=None,district:str|None=None,taluka:str|None=None,village:str|None=None,db:Session=Depends(get_db)): return svc.trends(db,filters(state,district,taluka,village),period)
@router.get("/location")
def location(state:str|None=None,district:str|None=None,taluka:str|None=None,db:Session=Depends(get_db)): return svc.locations(db,filters(state,district,taluka))
@router.get("/rankings")
def ranking(level:str=Query("district",pattern="^(state|district|taluka|village)$"),state:str|None=None,district:str|None=None,taluka:str|None=None,village:str|None=None,category_id:str|None=None,department_id:str|None=None,db:Session=Depends(get_db)):
    f = filters(state,district,taluka,village,category_id,department_id)
    return svc.category_rankings(db, level, category_id, f) if category_id else svc.rankings(db, level, f)
@router.get("/rankings/{level}")
def ranking_level(level:str,category_id:str|None=None,db:Session=Depends(get_db)):
    if level not in svc.LEVELS: raise HTTPException(400,"Invalid geographic level")
    return svc.rankings(db,level,filters(category_id=category_id))
@router.get("/rankings/{level}/category/{category_id}")
def ranking_category(level:str,category_id:str,state:str|None=None,district:str|None=None,taluka:str|None=None,village:str|None=None,department_id:str|None=None,db:Session=Depends(get_db)):
    if level not in svc.LEVELS: raise HTTPException(400,"Invalid geographic level")
    _valid_uuid("category_id", category_id)
    _valid_uuid("department_id", department_id) if department_id else None
    return svc.category_rankings(db, level, category_id, filters(state,district,taluka,village,category_id,department_id))

@router.get("/most-improved")
def most_improved(level:str=Query("district",pattern="^(state|district|taluka|village)$"),period:str=Query("monthly",pattern="^(daily|weekly|monthly|yearly)$"),category_id:str|None=None,department_id:str|None=None,db:Session=Depends(get_db)):
    f = filters(category_id=category_id, department_id=department_id)
    return svc.most_improved(db, level, f, period)

@router.get("/methodology")
def methodology(db:Session=Depends(get_db)): return svc.methodology(db)
