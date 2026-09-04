from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict, Union

class FeasibleSolution(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: str
    name: str
    description: str
    risk_level: str
    strategy_type: Optional[str] = "direct_lift_shift"
    estimated_downtime_minutes: Optional[int] = None
    cost_delta_monthly: Optional[float] = None
    feasibility_score: Optional[float] = None
    predicted_suitability: Optional[float] = None
    suitability_percentage: Optional[float] = None
    confidence: Optional[str] = "High"
    confidence_score: Optional[float] = None
    supporting_features: List[str] = Field(default_factory=list)
    rank: Optional[int] = 1
    ml_derived: Optional[bool] = True
    downtime_basis: Optional[str] = None
    cost_basis: Optional[str] = None
    missing_data: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    implementation_steps: List[str] = Field(default_factory=list)

class SolutionApplyRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    source_environment: str
    target_component_id: str
    solution_id: Optional[str] = None
    solution_name: Optional[str] = None
    strategy_type: Optional[str] = None
    solution: Optional[Dict[str, Any]] = Field(default_factory=dict)
    action: Optional[str] = "migrate"

class SnapshotActionRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    snapshot_id: Optional[str] = None
    environment_id: Optional[str] = None
    target_component_id: Optional[str] = None
    action: Optional[str] = "migrate"

class SolutionRankRequest(BaseModel):
    simulation_result: Dict[str, Any]
    candidate_solutions: Optional[List[Dict[str, Any]]] = None

class DependencyBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    source_id: str
    target_id: str
    relationship_type: str = "depends_on"
    criticality: str = "medium"
    environment_id: Optional[str] = None
    source_environment: Optional[str] = None
    metadata_col: Optional[Dict[str, Any]] = Field(default_factory=dict)

class DependencyCreate(DependencyBase):
    pass

class Dependency(DependencyBase):
    id: str
    created_at: Optional[str] = None

class ComponentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    name: str
    type: str = "server"
    environment: str = "cloud"
    environment_id: Optional[str] = None
    provider: Optional[str] = "manual"
    region: Optional[str] = None
    location: Optional[str] = "us-east-1"
    criticality: str = "medium"
    owner: Optional[str] = "Ops"
    status: str = "active"
    cpu: Optional[float] = None
    memory: Optional[float] = None
    cost_per_month: float = 0.0
    currency: str = "USD"
    position_x: Optional[float] = 0.0
    position_y: Optional[float] = 0.0
    telemetry: Optional[Dict[str, Any]] = Field(default_factory=dict)
    metadata_col: Optional[Dict[str, Any]] = Field(default_factory=dict)
    source_environment: str = "aws"

class ComponentCreate(ComponentBase):
    pass

class ComponentPositionUpdate(BaseModel):
    position_x: float
    position_y: float

class Component(ComponentBase):
    id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class EnvironmentCreate(BaseModel):
    id: Optional[str] = None
    name: str
    type: str = "manual"
    region: Optional[str] = "us-east-1"

class EnvironmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: str
    name: str
    type: str
    region: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class ManualProjectCreate(BaseModel):
    name: str

class ManualProject(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: str
    name: str
    created_at: str

class SimulationRequest(BaseModel):
    target_component_id: Optional[str] = None
    component_id: Optional[str] = None
    action: str = "migrate"
    destination_env: Optional[str] = "cloud"
    target_environment: Optional[str] = None
    source_environment: Optional[str] = None
    use_ai: bool = False

    def get_component_id(self) -> str:
        return self.component_id or self.target_component_id or ""

class SimulationResult(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    target_component_id: Optional[str] = None
    component_id: Optional[str] = None
    target_component: str
    action: str = "migrate"
    change_action: str = "migrate"
    destination: Optional[str] = None
    target_environment: Optional[str] = None
    source_environment: Optional[str] = None
    total_nodes_affected: int = 0
    affected_count: int = 0
    affected_components: List[Any] = Field(default_factory=list)
    affected_component_names: List[str] = Field(default_factory=list)
    upstream_impact_count: int = 0
    upstream_impact: List[Dict[str, Any]] = Field(default_factory=list)
    downstream_dependencies_count: int = 0
    downstream_dependencies: List[Dict[str, Any]] = Field(default_factory=list)
    blast_radius_nodes: List[str] = Field(default_factory=list)
    risk_score: float = 0.0
    risk_level: str = "LOW"
    estimated_downtime_minutes: Optional[int] = None
    cost_delta_monthly: Optional[float] = None
    downtime_explanation: Optional[str] = None
    cost_explanation: Optional[str] = None
    critical_flags: List[str] = Field(default_factory=list)
    risk_factors: Dict[str, Any] = Field(default_factory=dict)
    feasible_solutions: List[FeasibleSolution] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    ai_explanation: Optional[str] = None
    ai_recommendation: Optional[str] = None
    financial_analysis: Optional[str] = None
    risk_analysis: Optional[str] = None
    architect_recommendation: Optional[str] = None
    financial_summary: Optional[Dict[str, Any]] = None
    risk_summary: Optional[Dict[str, Any]] = None
    architect_summary: Optional[Dict[str, Any]] = None
    recommended_actions: Optional[List[str]] = Field(default_factory=list)
    missing_data: List[str] = Field(default_factory=list)

class SimulationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: str
    environment_id: Optional[str] = None
    source_environment: str
    target_component_id: Optional[str] = None
    component_id: Optional[str] = None
    action: str
    destination_env: Optional[str] = None
    target_environment: Optional[str] = None
    affected_components: List[Any] = Field(default_factory=list)
    risk_score: float
    risk_level: str
    estimated_downtime_minutes: Optional[int] = None
    cost_delta_monthly: Optional[float] = None
    status: str
    created_at: str

class TwinStats(BaseModel):
    total_components: int
    critical_services_count: int
    total_monthly_cost: float
    on_prem_count: int
    cloud_count: int
    currency: Optional[str] = "USD"

class SPOFResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    spof_count: int
    spof_nodes: List[Dict[str, Any]]
    environment: str

