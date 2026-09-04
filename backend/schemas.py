from pydantic import BaseModel
from typing import List, Optional, Any
from models import ComponentType, Environment, Criticality, Status, DependencyType

class DependencyBase(BaseModel):
    source_id: str
    target_id: str
    relationship_type: DependencyType
    criticality: Criticality
    source_environment: str = "aws"

class DependencyCreate(DependencyBase):
    pass

class Dependency(DependencyBase):
    id: str

    class Config:
        from_attributes = True

class ComponentBase(BaseModel):
    name: str
    type: ComponentType
    environment: Environment
    location: str
    criticality: Criticality
    owner: str
    status: Status = Status.active
    cpu: Optional[float] = None
    memory: Optional[float] = None
    cost_per_month: float = 0.0
    metadata_col: dict = {}
    source_environment: str = "aws"

class ComponentCreate(ComponentBase):
    pass

class Component(ComponentBase):
    id: str

    class Config:
        from_attributes = True

class ManualProjectCreate(BaseModel):
    name: str

class ManualProject(BaseModel):
    id: str
    name: str
    created_at: str

    class Config:
        from_attributes = True

class SimulationRequest(BaseModel):
    target_component_id: str
    action: str = "migrate"
    destination_env: Optional[str] = "cloud"
    use_ai: bool = False

class SimulationResult(BaseModel):
    change_action: str
    target_component: str
    destination: Optional[str]
    affected_count: int
    affected_components: List[str]
    risk_score: int
    risk_level: str
    estimated_downtime_minutes: int
    cost_delta_monthly: float
    critical_flags: List[str]
    ai_explanation: Optional[str] = None
    ai_recommendation: Optional[str] = None
    financial_analysis: Optional[str] = None
    risk_analysis: Optional[str] = None
    architect_recommendation: Optional[str] = None
    recommended_actions: Optional[List[str]] = []

class TwinStats(BaseModel):
    total_components: int
    critical_services_count: int
    total_monthly_cost: float
    on_prem_count: int
    cloud_count: int
