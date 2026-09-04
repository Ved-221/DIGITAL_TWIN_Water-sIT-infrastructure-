from pydantic import BaseModel, model_validator, ConfigDict
from typing import List, Optional, Any, Dict
from models import ComponentType, Environment, Criticality, Status, DependencyType

class DependencyBase(BaseModel):
    source_component_id: str
    target_component_id: str
    relationship_type: str
    source: Optional[str] = "aws_api"
    criticality: Optional[Criticality] = Criticality.medium
    metadata: Optional[Dict[str, Any]] = {}

    # Backward compatibility fields
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    discovery_source: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            src = getattr(data, "source_component_id", None) or getattr(data, "source_id", None)
            tgt = getattr(data, "target_component_id", None) or getattr(data, "target_id", None)
            s = getattr(data, "source", None) or getattr(data, "discovery_source", None) or "aws_api"
            meta = getattr(data, "metadata_col", None)
            if not isinstance(meta, dict):
                raw_meta = getattr(data, "metadata", None)
                meta = raw_meta if isinstance(raw_meta, dict) else {}
            rel = getattr(data, "relationship_type", None)
            if hasattr(rel, "value"):
                rel = rel.value
            crit = getattr(data, "criticality", None) or Criticality.medium
            dep_id = getattr(data, "id", None)
            res = {
                "source_component_id": src,
                "target_component_id": tgt,
                "relationship_type": str(rel) if rel else "connects_to",
                "source": s,
                "criticality": crit,
                "metadata": meta,
                "source_id": src,
                "target_id": tgt,
                "discovery_source": s
            }
            if dep_id:
                res["id"] = dep_id
            return res
        elif isinstance(data, dict):
            src = data.get("source_component_id") or data.get("source_id")
            tgt = data.get("target_component_id") or data.get("target_id")
            s = data.get("source") or data.get("discovery_source") or "aws_api"
            meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else data.get("metadata_col", {})
            if not isinstance(meta, dict):
                meta = {}
            rel = data.get("relationship_type")
            if hasattr(rel, "value"):
                rel = rel.value
            crit = data.get("criticality") or Criticality.medium
            data["source_component_id"] = src
            data["source_id"] = src
            data["target_component_id"] = tgt
            data["target_id"] = tgt
            data["source"] = s
            data["discovery_source"] = s
            data["metadata"] = meta
            data["relationship_type"] = str(rel) if rel else "connects_to"
            data["criticality"] = crit
            return data
        return data

class DependencyCreate(DependencyBase):
    pass

class Dependency(DependencyBase):
    id: str
    model_config = ConfigDict(from_attributes=True)


class ComponentBase(BaseModel):
    name: str
    type: ComponentType
    environment: Environment = Environment.cloud
    location: Optional[str] = "us-east-1"
    criticality: Criticality = Criticality.medium
    owner: Optional[str] = "Cloud Ops"
    status: Status = Status.active
    cpu: Optional[float] = None
    memory: Optional[float] = None
    cost_per_month: float = 0.0
    arn: Optional[str] = None
    aws_region: Optional[str] = None
    discovery_source: Optional[str] = "manual"
    account_id: Optional[str] = None
    availability_zone: Optional[str] = None
    updated_at: Optional[str] = None
    metadata_col: dict = {}

class ComponentCreate(ComponentBase):
    pass

class Component(ComponentBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

class ReasoningFeature(BaseModel):
    feature: str
    value: Any
    impact: str

class RiskFactor(BaseModel):
    factor: str
    score_impact: int
    explanation: str

class CostBreakdown(BaseModel):
    cost_impact: float
    is_estimated: bool
    pricing_basis: str
    current_monthly_cost: float
    projected_monthly_cost: float
    calculation_formula: str

class DowntimeEstimate(BaseModel):
    estimated_downtime_minutes: int
    downtime_category: str
    rationale: str

class SimulationRequest(BaseModel):
    target_component_id: str
    action: Optional[str] = "migrate"
    use_ml_recommendation: bool = False
    destination_env: Optional[str] = "cloud"

class StructuredAIExplanation(BaseModel):
    what_is_happening: str
    why_ml_recommended: str
    affected_components_summary: str
    simulation_prediction: str
    key_risks: str
    engineer_considerations: List[str]

class SimulationResult(BaseModel):
    target_component_id: Optional[str] = None
    target_component: str
    change_action: str
    action: Optional[str] = None
    recommended_action: Optional[str] = None
    destination: Optional[str] = None
    affected_count: int
    blast_radius: int = 0
    affected_components: List[str]
    risk_score: int
    risk_level: str
    risk_factors: List[RiskFactor] = []
    estimated_downtime_minutes: int
    downtime_estimate: Optional[DowntimeEstimate] = None
    cost_delta_monthly: float
    cost_impact: float = 0.0
    cost_breakdown: Optional[CostBreakdown] = None
    critical_flags: List[str] = []
    critical_warnings: List[str] = []
    ml_confidence: Optional[float] = None
    ml_reasoning_features: Optional[List[ReasoningFeature]] = None
    ai_explanation: Optional[str] = None
    ai_recommendation: Optional[str] = None
    structured_explanation: Optional[StructuredAIExplanation] = None
    environment_source: Optional[str] = "aws_api"
    is_manual: bool = False
    configured_assumptions: Optional[Dict[str, Any]] = None

class TwinStats(BaseModel):
    total_components: int
    critical_services_count: int
    total_monthly_cost: float
    on_prem_count: int
    cloud_count: int

class AWSSyncRequest(BaseModel):
    mode: str = "merge"
    use_synthetic: bool = False
    region: Optional[str] = None

class AWSSyncResponse(BaseModel):
    success: bool
    message: str
    data_source: str
    account_id: Optional[str] = None
    region: Optional[str] = None
    components_added: int
    components_updated: int
    dependencies_added: int
    total_components: int
    total_dependencies: int

class AWSStatusResponse(BaseModel):
    authenticated: bool
    account_id: Optional[str] = None
    arn: Optional[str] = None
    region: str
    configured_source: str
    last_sync: Optional[str] = None
    aws_components_count: int
    total_components_count: int
    error: Optional[str] = None

class MetricSnapshotBase(BaseModel):
    resource_id: str
    timestamp: str
    resource_type: str
    cpu: Optional[float] = None
    memory: Optional[float] = None
    disk: Optional[Dict[str, Any]] = None
    network: Optional[Dict[str, Any]] = None
    latency: Optional[float] = None
    error_rate: Optional[float] = None
    request_rate: Optional[float] = None
    connections: Optional[float] = None
    status: str = "active"
    age_days: Optional[float] = None
    raw_metrics: Optional[Dict[str, Any]] = {}

class MetricSnapshotCreate(MetricSnapshotBase):
    pass

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    uptime_seconds: float
    database_connected: bool
    total_components: int
    aws_authenticated: bool
    data_source: str

class AWSConnectRequest(BaseModel):
    access_key_id: str
    secret_access_key: str
    session_token: Optional[str] = None
    region: Optional[str] = "us-east-1"

class AWSConnectResponse(BaseModel):
    authenticated: bool
    account_id: Optional[str] = None
    arn: Optional[str] = None
    region: str
    message: str
    error: Optional[str] = None

class ServiceSpend(BaseModel):
    service_name: str
    amount: float
    currency: str = "USD"

class AWSCostReport(BaseModel):
    authenticated: bool
    spend_available: bool
    total_month_to_date_cost: float
    currency: str = "USD"
    time_period: Dict[str, str] = {}
    service_breakdown: List[ServiceSpend] = []
    pricing_source: str
    error: Optional[str] = None

class AWSHealthEvent(BaseModel):
    arn: str
    service: str
    event_type_code: str
    event_type_category: str
    region: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status_code: str
    description: Optional[str] = None
    affected_entities: List[str] = []

class AWSHealthReport(BaseModel):
    authenticated: bool
    health_available: bool
    open_events_count: int = 0
    events: List[AWSHealthEvent] = []
    source: str = "AWS Health API (Global us-east-1)"
    support_plan_required: bool = False
    error: Optional[str] = None

class MetricSnapshot(MetricSnapshotBase):
    id: str
    model_config = ConfigDict(from_attributes=True)

class MetricsCollectRequest(BaseModel):
    use_synthetic: bool = False
    period_seconds: int = 300
    region: Optional[str] = None

class MetricsCollectResponse(BaseModel):
    success: bool
    message: str
    data_source: str
    timestamp: str
    metrics_collected: int
    snapshots: List[MetricSnapshot]

class MLRecommendation(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    resource_id: str
    resource_name: str
    resource_type: str
    recommended_action: str
    confidence: float
    reasoning_features: List[ReasoningFeature]
    is_trained_model: bool = True
    model_type: str = "RandomForestClassifier"
    model_timestamp: Optional[str] = None
    raw_features: Optional[Dict[str, Any]] = None

class MLTrainResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    success: bool
    message: str
    model_type: str
    trained_at: str
    n_samples_total: int
    validation_macro_f1: float
    test_accuracy: float
    test_macro_f1: float
    top_features: List[Dict[str, Any]]

class MLModelStatus(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    is_trained: bool
    model_type: str
    trained_at: Optional[str] = None
    test_macro_f1: Optional[float] = None
    test_accuracy: Optional[float] = None
    classes: List[str] = []
    top_features: List[Dict[str, Any]] = []

class TwinStateResponse(BaseModel):
    mode: str = "unconnected"
    authenticated: bool = False
    account_id: Optional[str] = None
    arn: Optional[str] = None
    region: Optional[str] = None
    discovery_status: str = "idle"
    discovery_summary: Dict[str, Any] = {}
    last_sync: Optional[str] = None
    error: Optional[str] = None
    total_components: int = 0
    total_dependencies: int = 0

class TwinResetResponse(BaseModel):
    success: bool
    message: str
    mode: str = "unconnected"

class TwinModeRequest(BaseModel):
    region: Optional[str] = "us-east-1"

class ManualAssumptions(BaseModel):
    cpu: Optional[float] = None
    memory: Optional[float] = None
    latency: Optional[float] = None
    error_rate: Optional[float] = None
    availability: Optional[float] = None

class ManualComponentCreate(BaseModel):
    id: Optional[str] = None
    name: str
    type: ComponentType
    criticality: Optional[Criticality] = Criticality.medium
    environment: Optional[Environment] = Environment.cloud
    location: Optional[str] = "us-east-1"
    owner: Optional[str] = "Infrastructure Team"
    cost_per_month: Optional[float] = 0.0
    assumptions: Optional[ManualAssumptions] = None
    metadata: Optional[Dict[str, Any]] = None

class ManualComponentUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[ComponentType] = None
    criticality: Optional[Criticality] = None
    environment: Optional[Environment] = None
    location: Optional[str] = None
    owner: Optional[str] = None
    cost_per_month: Optional[float] = None
    assumptions: Optional[ManualAssumptions] = None
    metadata: Optional[Dict[str, Any]] = None

class ManualDependencyCreate(BaseModel):
    source_component_id: str
    target_component_id: str
    relationship_type: str = "connects_to"
    criticality: Optional[Criticality] = Criticality.medium
    metadata: Optional[Dict[str, Any]] = None

class ManualEnvironmentResponse(BaseModel):
    success: bool
    message: str
    mode: str = "manual"
    total_components: int = 0
    total_dependencies: int = 0

class ConstraintsEvaluation(BaseModel):
    cost_impact: Optional[float] = None
    cost_impact_display: str = "Not enough data"
    resilience: str = "Not enough data"
    risk_reduction: str = "Not enough data"
    risk_score_before: int = 0
    risk_score_after: int = 0
    downtime_minutes: int = 0
    downtime_display: str = "0 min"
    blast_radius_before: int = 0
    blast_radius_after: int = 0
    performance: str = "Not enough data"

class FeasibleSolution(BaseModel):
    id: str
    title: str
    action_type: str
    description: str
    expected_impact: str
    is_feasible: bool = True
    feasibility_reason: str
    constraints_evaluation: ConstraintsEvaluation
    changes: Dict[str, Any] = {}

class FeasibleSolutionsGenerateRequest(BaseModel):
    target_component_id: str
    current_simulation: Optional[Dict[str, Any]] = None
    simulation_result: Optional[Dict[str, Any]] = None

class FeasibleSolutionsResponse(BaseModel):
    success: bool = True
    target_component_id: str
    target_component_name: str
    problem_identified: Optional[str] = None
    problem_summary: Optional[str] = None
    total_candidate_solutions: Optional[int] = 0
    feasible_solutions: List[FeasibleSolution] = []
    solutions: List[FeasibleSolution] = []
    message: Optional[str] = None

class ApplySolutionRequest(BaseModel):
    solution_id: str
    target_component_id: str
    solution: Optional[FeasibleSolution] = None
    solution_data: Optional[Dict[str, Any]] = None

class BeforeAfterComparison(BaseModel):
    affected_resources: Dict[str, Any]
    dependency_count: Dict[str, Any]
    blast_radius: Dict[str, Any]
    risk: Dict[str, Any]
    downtime: Dict[str, Any]
    cost: Dict[str, Any]
    resilience: Dict[str, Any]
    performance: Dict[str, Any]

class ApplySolutionResponse(BaseModel):
    success: bool
    applied_solution: FeasibleSolution
    is_live_aws: bool = False
    warning_banner: Optional[str] = None
    before_after_comparison: BeforeAfterComparison
    ai_explanation: Optional[str] = None
    ai_structured_explanation: Optional[Dict[str, Any]] = None
    updated_simulation: Optional[Dict[str, Any]] = None
