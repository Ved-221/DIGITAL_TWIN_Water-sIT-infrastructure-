from pydantic import BaseModel, model_validator, ConfigDict
from typing import List, Optional, Any, Dict, Union
from models import ComponentType, EnvironmentEnum, Criticality, Status, DependencyType
Environment = EnvironmentEnum

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
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    name: str
    type: Optional[ComponentType] = ComponentType.server
    environment: Optional[Environment] = Environment.cloud
    location: Optional[str] = "us-east-1"
    criticality: Optional[Criticality] = Criticality.medium
    owner: Optional[str] = "Cloud Ops"
    status: Optional[Status] = Status.active
    cpu: Optional[float] = None
    memory: Optional[float] = None
    cost_per_month: float = 0.0
    arn: Optional[str] = None
    aws_region: Optional[str] = None
    discovery_source: Optional[str] = "manual"
    account_id: Optional[str] = None
    availability_zone: Optional[str] = None
    updated_at: Optional[str] = None
    domain: Optional[str] = "general"
    properties: Optional[Dict[str, Any]] = {}
    source: Optional[str] = None
    source_id: Optional[str] = None
    last_updated: Optional[str] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    metadata_col: dict = {}

    @model_validator(mode="before")
    @classmethod
    def set_defaults_if_none(cls, data):
        if isinstance(data, dict):
            if data.get("environment") is None:
                data["environment"] = Environment.cloud
            if data.get("criticality") is None:
                data["criticality"] = Criticality.medium
            if data.get("type") is None:
                data["type"] = ComponentType.server
        elif hasattr(data, "__dict__"):
            if getattr(data, "environment", None) is None:
                try:
                    setattr(data, "environment", Environment.cloud)
                except Exception:
                    pass
            if getattr(data, "criticality", None) is None:
                try:
                    setattr(data, "criticality", Criticality.medium)
                except Exception:
                    pass
            if getattr(data, "type", None) is None:
                try:
                    setattr(data, "type", ComponentType.server)
                except Exception:
                    pass
        return data

class ComponentCreate(ComponentBase):
    pass

class ComponentPositionUpdate(BaseModel):
    position_x: float
    position_y: float

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
    target_component_id: Optional[str] = None
    component_id: Optional[str] = None
    action: Optional[str] = "migrate"
    use_ml_recommendation: bool = False
    destination_env: Optional[str] = "cloud"
    target_environment: Optional[str] = None
    source_environment: Optional[str] = None
    use_ai: bool = False

    def get_component_id(self) -> str:
        return self.target_component_id or self.component_id or ""

class StructuredAIExplanation(BaseModel):
    what_is_happening: str
    why_ml_recommended: str
    affected_components_summary: str
    simulation_prediction: str
    key_risks: str
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
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: str
    name: Optional[str] = None
    description: str
    risk_level: Optional[str] = "LOW"
    strategy_type: Optional[str] = "direct_lift_shift"
    title: Optional[str] = None
    action_type: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_name_and_title(cls, data):
        if isinstance(data, dict):
            t = data.get("title")
            n = data.get("name")
            if not n and t:
                data["name"] = t
            elif not t and n:
                data["title"] = n
            elif not n and not t:
                data["name"] = data.get("id", "Solution")
                data["title"] = data.get("id", "Solution")
        elif hasattr(data, "__dict__"):
            t = getattr(data, "title", None)
            n = getattr(data, "name", None)
            if not n and t:
                setattr(data, "name", t)
            elif not t and n:
                setattr(data, "title", n)
        return data
    expected_impact: Optional[str] = None
    is_feasible: Optional[bool] = True
    feasibility_reason: Optional[str] = None
    constraints_evaluation: Optional[ConstraintsEvaluation] = None
    changes: Optional[Dict[str, Any]] = {}
    estimated_downtime_minutes: Optional[int] = None
    cost_delta_monthly: Optional[float] = None
    feasibility_score: Optional[float] = None
    predicted_suitability: Optional[float] = None
    suitability_percentage: Optional[float] = None
    confidence: Optional[str] = "High"
    confidence_score: Optional[float] = None
    supporting_features: List[str] = []
    rank: Optional[int] = 1
    ml_derived: Optional[bool] = True
    downtime_basis: Optional[str] = None
    cost_basis: Optional[str] = None
    missing_data: List[str] = []
    prerequisites: List[str] = []
    pros: List[str] = []
    cons: List[str] = []
    implementation_steps: List[str] = []

class SimulationResult(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    target_component_id: Optional[str] = None
    component_id: Optional[str] = None
    target_component: str
    action: str = "migrate"
    change_action: str = "migrate"
    recommended_action: Optional[str] = None
    destination: Optional[str] = None
    target_environment: Optional[str] = None
    source_environment: Optional[str] = None
    total_nodes_affected: int = 0
    affected_count: int = 0
    blast_radius: int = 0
    affected_components: List[Any] = []
    affected_components_details: Optional[List[Dict[str, Any]]] = []
    affected_component_names: List[str] = []
    upstream_impact_count: int = 0
    upstream_impact: List[Dict[str, Any]] = []
    downstream_dependencies_count: int = 0
    downstream_dependencies: List[Dict[str, Any]] = []
    blast_radius_nodes: List[str] = []
    risk_score: float = 0.0
    risk_level: str = "LOW"
    estimated_downtime_minutes: Optional[int] = None
    downtime_estimate: Optional[Any] = None
    cost_delta_monthly: Optional[float] = None
    cost_impact: Optional[float] = None
    cost_breakdown: Optional[Any] = None
    downtime_explanation: Optional[str] = None
    cost_explanation: Optional[str] = None
    critical_flags: List[str] = []
    critical_warnings: List[str] = []
    risk_factors: Union[Dict[str, Any], List[Any]] = {}
    feasible_solutions: List[FeasibleSolution] = []
    recommendations: List[str] = []
    ml_confidence: Optional[float] = None
    ml_reasoning_features: Optional[List[Any]] = None
    ai_explanation: Optional[str] = None
    ai_recommendation: Optional[str] = None
    structured_explanation: Optional[Any] = None
    financial_analysis: Optional[str] = None
    risk_analysis: Optional[str] = None
    architect_recommendation: Optional[str] = None
    financial_summary: Optional[Dict[str, Any]] = None
    risk_summary: Optional[Dict[str, Any]] = None
    architect_summary: Optional[Dict[str, Any]] = None
    recommended_actions: Optional[List[str]] = []
    missing_data: List[str] = []
    environment_source: Optional[str] = "manual"
    is_manual: bool = False
    configured_assumptions: Optional[Dict[str, Any]] = None

class TwinStats(BaseModel):
    total_components: int
    critical_services_count: int
    total_monthly_cost: float
    on_prem_count: int
    cloud_count: int
    currency: Optional[str] = "USD"

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
    source_environment: Optional[str] = "manual"
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
    source_component_id: Optional[str] = None
    target_component_id: Optional[str] = None
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    relationship_type: str = "connects_to"
    criticality: Optional[Criticality] = Criticality.medium
    source_environment: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def populate_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            src = data.get("source_component_id") or data.get("source_id")
            tgt = data.get("target_component_id") or data.get("target_id")
            data["source_component_id"] = src
            data["source_id"] = src
            data["target_component_id"] = tgt
            data["target_id"] = tgt
        return data

class ManualEnvironmentResponse(BaseModel):
    success: bool
    message: str
    mode: str = "manual"
    total_components: int = 0
    total_dependencies: int = 0

class EnvironmentSchema(BaseModel):
    id: str
    name: str
    provider: Optional[str] = "aws"
    source_type: Optional[str] = "aws"
    is_active: bool = True
    status: Optional[str] = "connected"
    created_at: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class EnvironmentCreate(BaseModel):
    name: str
    provider: Optional[str] = "manual"

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

# ==========================================
# Generic Digital Twin Builder Schemas
# ==========================================

class NaturalLanguageParseRequest(BaseModel):
    description: str
    domain: Optional[str] = "general"

class ParsedComponentPreview(BaseModel):
    temp_id: str
    name: str
    type: str
    domain: Optional[str] = "general"
    status: Optional[str] = "active"
    criticality: Optional[str] = "medium"
    properties: Optional[Dict[str, Any]] = {}
    metrics: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = {}
    source: str = "user_description"
    source_id: Optional[str] = None
    raw_mention: Optional[str] = None

class ParsedDependencyPreview(BaseModel):
    source_temp_id: str
    target_temp_id: str
    source_name: str
    target_name: str
    relationship_type: str
    source: str = "user_description"
    explicit_quote: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}

class ParsedDigitalTwinPreview(BaseModel):
    success: bool = True
    domain: str = "general"
    raw_description: str
    components: List[ParsedComponentPreview] = []
    dependencies: List[ParsedDependencyPreview] = []
    ambiguities: List[str] = []
    source: str = "user_description"

class ApplyParsedTwinRequest(BaseModel):
    domain: Optional[str] = "general"
    components: List[ParsedComponentPreview]
    dependencies: List[ParsedDependencyPreview]
    clear_existing: bool = True

class ApplyParsedTwinResponse(BaseModel):
    success: bool = True
    message: str
    components_count: int
    dependencies_count: int
    components: List[Component] = []
    dependencies: List[Dependency] = []

class StructuredTwinBuildRequest(BaseModel):
    domain: Optional[str] = "general"
    components: List[Dict[str, Any]]
    dependencies: List[Dict[str, Any]]
    clear_existing: bool = True


# ==========================================
# What-If Candidate Solutions Schemas
# ==========================================

class WhatIfRequest(BaseModel):
    target_component_id: str
    action: str = "fail"
    source_environment: Optional[str] = None


class CandidateVsBaseline(BaseModel):
    blast_radius_delta: Optional[int] = None
    risk_score_delta: Optional[float] = None
    downtime_delta: Optional[int] = None


class CandidateSimulationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    blast_radius: int = 0
    upstream_impact_count: int = 0
    downstream_dependencies_count: int = 0
    risk_score: Optional[float] = None
    risk_level: str = "unknown"
    estimated_downtime_minutes: Optional[int] = None
    cost_delta_monthly: Optional[float] = None
    critical_flags: List[str] = []
    spof_eliminated: bool = False
    vs_baseline: Optional[CandidateVsBaseline] = None


class WhatIfCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    candidate_id: str
    name: str
    description: str = ""
    strategy_type: str = "direct_lift_shift"
    proposed_changes: List[str] = []
    resulting_topology: Optional[Dict[str, Any]] = None
    affected_components: List[Dict[str, Any]] = []
    simulation_result: CandidateSimulationResult
    available_metrics: List[str] = []
    missing_data: List[str] = []
    feasibility: str = "unknown"          # feasible | conditional | unknown | not_feasible
    evidence: List[str] = []
    pros: List[str] = []
    cons: List[str] = []
    prerequisites: List[str] = []
    implementation_steps: List[str] = []
    complexity: int = 1
    provides_redundancy: bool = False
    zero_downtime_capable: bool = False


class WhatIfBaselineResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target_component_id: str
    target_component_name: str
    action: str
    source_environment: str
    blast_radius: int = 0
    upstream_impact_count: int = 0
    downstream_dependencies_count: int = 0
    risk_score: float = 0.0
    risk_level: str = "LOW"
    is_single_point_of_failure: bool = False
    topology: Optional[Dict[str, Any]] = None


class CandidateFeatureSet(BaseModel):
    model_config = ConfigDict(extra="ignore")
    candidate_id: str
    strategy_type: str
    component_type: str = "unknown"
    criticality: str = "unknown"
    action: str = "fail"
    affected_component_count: int = 0
    upstream_impact_count: int = 0
    downstream_dependencies_count: int = 0
    dependency_depth: int = 0
    critical_dependency_count: int = 0
    spof_indicator: bool = False
    spof_eliminated: bool = False
    topology_change_size: int = 0
    dependency_change_count: int = 0
    available_health_metrics: List[str] = []
    available_resource_metrics: List[str] = []
    cost_delta: Optional[float] = None
    cost_data_available: bool = False
    estimated_downtime_minutes: Optional[int] = None
    downtime_data_available: bool = False
    risk_score: Optional[float] = None
    risk_score_available: bool = False
    risk_score_delta: Optional[float] = None
    blast_radius_delta: Optional[int] = None
    provides_redundancy: bool = False
    zero_downtime_capable: bool = False
    complexity: int = 1
    feasibility: str = "unknown"
    missing_data: List[str] = []


class MLRankingItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    candidate_id: str
    rank: int
    recommendation: bool = False
    ranking_method: str = "Simulation-Trained ML Prototype"
    features_used: List[str] = []
    explanation: str = ""


class MLRecommendationSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    recommended_candidate_id: str
    candidate_name: str
    strategy_type: str
    reasoning: str
    ranking_method: str
    limitations: List[str] = []


class AgentReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    agent: str
    summary: str
    cost_status: Optional[str] = None
    findings: List[str] = []
    evidence: List[str] = []
    unknowns: List[str] = []
    recommendation: str = ""
    recommended_candidate_id: Optional[str] = None
    status: str = "complete"


class AgentConsensus(BaseModel):
    model_config = ConfigDict(extra="ignore")
    candidate_id: Optional[str] = None
    agreement: str = "none"
    reasoning: List[str] = []
    conflicts: List[Dict[str, Any]] = []
    ml_alignment: bool = False


class MultiAgentDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    financial: AgentReport
    risk: AgentReport
    architect: AgentReport
    consensus: AgentConsensus


class WhatIfCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    success: bool = True
    target_component_id: str
    target_component_name: Optional[str] = ""
    action: str
    source_environment: str
    original_baseline: Optional[WhatIfBaselineResult] = None
    candidate_count: int = 0
    candidates: List[WhatIfCandidate] = []
    scenario: Optional[Dict[str, Any]] = None
    simulation_results: List[Dict[str, Any]] = []
    extracted_features: List[CandidateFeatureSet] = []
    ml_ranking: List[MLRankingItem] = []
    ranking: List[MLRankingItem] = []
    recommended_candidate_id: Optional[str] = None
    recommendation: Optional[MLRecommendationSummary] = None
    ranking_status: str = "unavailable"
    ranking_method: Optional[str] = None
    evidence: List[str] = []
    missing_data: List[str] = []
    limitations: List[str] = []
    agents: Optional[MultiAgentDecision] = None
    consensus: Optional[AgentConsensus] = None
    financial_analyst: Optional[AgentReport] = None
    risk_analyst: Optional[AgentReport] = None
    system_architect: Optional[AgentReport] = None
    error: Optional[str] = None


# ─── Sandbox Execution Schemas ───────────────────────────────────────────────

class SandboxApplyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_environment: str = "manual"
    target_component_id: str
    candidate_id: Optional[str] = None
    action: str = "fail"
    candidate_data: Optional[Dict[str, Any]] = None
    sandbox_env_id: str = "sandbox"


class SandboxApplyResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    success: bool = True
    sandbox_id: str
    target_environment: str
    source_environment: str
    target_component_id: str
    original_component_id: str
    candidate_id: Optional[str] = None
    strategy_type: Optional[str] = None
    snapshot_id: str
    remediation_outcome: str
    mutations_applied: List[str] = []
    topology_diff: Dict[str, Any] = {}
    before: Dict[str, Any] = {}
    after: Dict[str, Any] = {}
    delta: Dict[str, Any] = {}
    tradeoffs: List[str] = []
    missing_data: List[str] = []


class SandboxRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    snapshot_id: str
    environment_id: Optional[str] = "sandbox"
    sandbox_id: Optional[str] = None
    target_component_id: Optional[str] = None


class SandboxRollbackResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    restored: bool = True
    snapshot_id: str
    environment_id: str
    sandbox_id: str
    components_count: int = 0
    dependencies_count: int = 0
    status: str = "rejected"


class SandboxAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    snapshot_id: str
    environment_id: Optional[str] = "sandbox"
    sandbox_id: Optional[str] = None


class SandboxAcceptResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    accepted: bool = True
    snapshot_id: str
    environment_id: str
    sandbox_id: str
    status: str = "accepted"


class SandboxBeforeAfterResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    snapshot_id: str
    environment_id: str
    status: str
    solution_id: Optional[str] = None
    solution_name: Optional[str] = None
    strategy_type: Optional[str] = None
    created_at: Optional[str] = None
    baseline_components_count: int = 0
    current_components_count: int = 0
    baseline_dependencies_count: int = 0
    current_dependencies_count: int = 0
    baseline_monthly_cost: float = 0.0
    current_monthly_cost: float = 0.0
    monthly_cost_delta: float = 0.0





