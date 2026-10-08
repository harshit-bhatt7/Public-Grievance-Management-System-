from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

CATEGORIES=['Roads & Potholes','Drainage & Sewage','Water Supply','Electricity','Street Lights','Garbage & Waste','Public Transport','Public Safety','Government Services','Healthcare','Education','Housing','Environment','Other']

class MilestoneIn(BaseModel):
    title:str=Field(min_length=1,max_length=250); description:Optional[str]=None; planned_date:Optional[date]=None; actual_date:Optional[date]=None; status:str='PENDING'; completion_percent:float=Field(ge=0,le=100); evidence:Optional[str]=None
class MilestoneOut(MilestoneIn):
    model_config=ConfigDict(from_attributes=True); id:UUID; updated_at:datetime; created_at:datetime

class ProjectCreate(BaseModel):
    name:str=Field(min_length=1,max_length=250); description:str=Field(min_length=1); category:str; department_id:Optional[UUID]=None
    state:Optional[str]=None; district:Optional[str]=None; taluka:Optional[str]=None; village:Optional[str]=None; latitude:Optional[float]=None; longitude:Optional[float]=None
    status:str='PLANNED'; start_date:Optional[date]=None; expected_completion_date:Optional[date]=None; actual_completion_date:Optional[date]=None
    estimated_cost:Optional[float]=Field(default=None,ge=0); approved_cost:Optional[float]=Field(default=None,ge=0); revised_cost:Optional[float]=Field(default=None,ge=0); amount_spent:Optional[float]=Field(default=None,ge=0); funding_source:Optional[str]=None
    project_manager_name:Optional[str]=None; project_manager_designation:Optional[str]=None; responsible_team:Optional[str]=None; responsible_personnel_count:Optional[int]=Field(default=None,ge=0)
    progress_percent:float=Field(default=0,ge=0,le=100); current_stage:Optional[str]=None; next_milestone:Optional[str]=None; is_public:bool=True
class ProjectUpdateIn(BaseModel):
    name:Optional[str]=None; description:Optional[str]=None; category:Optional[str]=None; department_id:Optional[UUID]=None; state:Optional[str]=None; district:Optional[str]=None; taluka:Optional[str]=None; village:Optional[str]=None; latitude:Optional[float]=None; longitude:Optional[float]=None
    status:Optional[str]=None; start_date:Optional[date]=None; expected_completion_date:Optional[date]=None; actual_completion_date:Optional[date]=None; estimated_cost:Optional[float]=Field(default=None,ge=0); approved_cost:Optional[float]=Field(default=None,ge=0); revised_cost:Optional[float]=Field(default=None,ge=0); amount_spent:Optional[float]=Field(default=None,ge=0); funding_source:Optional[str]=None
    project_manager_name:Optional[str]=None; project_manager_designation:Optional[str]=None; responsible_team:Optional[str]=None; responsible_personnel_count:Optional[int]=Field(default=None,ge=0); progress_percent:Optional[float]=Field(default=None,ge=0,le=100); current_stage:Optional[str]=None; next_milestone:Optional[str]=None; is_public:Optional[bool]=None
class ProjectOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID; project_number:str; name:str; description:str; category:str; department_id:Optional[UUID]; department_name:Optional[str]=None; state:Optional[str]; district:Optional[str]; taluka:Optional[str]; village:Optional[str]; latitude:Optional[float]; longitude:Optional[float]; status:str; schedule_state:str; start_date:Optional[date]; expected_completion_date:Optional[date]; original_completion_date:Optional[date]; actual_completion_date:Optional[date]; estimated_cost:Optional[float]; approved_cost:Optional[float]; revised_cost:Optional[float]; amount_spent:Optional[float]; remaining_amount:Optional[float]=None; funding_source:Optional[str]; project_manager_name:Optional[str]; project_manager_designation:Optional[str]; responsible_team:Optional[str]; responsible_personnel_count:Optional[int]; progress_percent:float; current_stage:Optional[str]; next_milestone:Optional[str]; created_at:datetime; updated_at:datetime
class ProjectDetail(ProjectOut):
    milestones:list[MilestoneOut]=[]; timeline:list[dict]=[]; documents:list[dict]=[]; photos:list[dict]=[]; grievance_summary:dict={}; is_following:bool=False
