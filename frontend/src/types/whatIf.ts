/**
 * What-If Simulation, Candidate Solutions, ML Ranking, Three-Agent Decision,
 * and Feasible Solutions Types matching backend/schemas.py
 */

export interface WhatIfRequest {
  target_component_id: string;
  action?: string;
  source_environment?: string;
}

export interface CandidateVsBaseline {
  blast_radius_delta?: number | null;
  risk_score_delta?: number | null;
  downtime_delta?: number | null;
}

export interface CandidateSimulationResult {
  blast_radius: number;
  upstream_impact_count: number;
  downstream_dependencies_count: number;
  risk_score?: number | null;
  risk_level: string;
  estimated_downtime_minutes?: number | null;
  cost_delta_monthly?: number | null;
  critical_flags: string[];
  spof_eliminated: boolean;
  vs_baseline?: CandidateVsBaseline | null;
}

export interface WhatIfCandidate {
  candidate_id: string;
  name: string;
  description: string;
  strategy_type: string;
  proposed_changes: string[];
  resulting_topology?: Record<string, any> | null;
  affected_components: Array<Record<string, any>>;
  simulation_result: CandidateSimulationResult;
  available_metrics: string[];
  missing_data: string[];
  feasibility: 'feasible' | 'conditional' | 'unknown' | 'not_feasible' | string;
  evidence: string[];
  pros: string[];
  cons: string[];
  prerequisites: string[];
  implementation_steps: string[];
  complexity: number;
  provides_redundancy: boolean;
  zero_downtime_capable: boolean;
}

export interface WhatIfBaselineResult {
  target_component_id: string;
  target_component_name: string;
  action: string;
  source_environment: string;
  blast_radius: number;
  upstream_impact_count: number;
  downstream_dependencies_count: number;
  risk_score: number;
  risk_level: string;
  is_single_point_of_failure: boolean;
  topology?: Record<string, any> | null;
}

export interface CandidateFeatureSet {
  candidate_id: string;
  strategy_type: string;
  component_type: string;
  criticality: string;
  action: string;
  affected_component_count: number;
  upstream_impact_count: number;
  downstream_dependencies_count: number;
  dependency_depth: number;
  critical_dependency_count: number;
  spof_indicator: boolean;
  spof_eliminated: boolean;
  topology_change_size: number;
  dependency_change_count: number;
  available_health_metrics: string[];
  available_resource_metrics: string[];
  cost_delta?: number | null;
  cost_data_available: boolean;
  estimated_downtime_minutes?: number | null;
  downtime_data_available: boolean;
  risk_score?: number | null;
  risk_score_available: boolean;
  risk_score_delta?: number | null;
  blast_radius_delta?: number | null;
  provides_redundancy: boolean;
  zero_downtime_capable: boolean;
  complexity: number;
  feasibility: string;
  missing_data: string[];
}

export interface MLRankingItem {
  candidate_id: string;
  rank: number;
  recommendation: boolean;
  ranking_method: string;
  features_used: string[];
  explanation: string;
}

export interface MLRecommendationSummary {
  recommended_candidate_id: string;
  candidate_name: string;
  strategy_type: string;
  reasoning: string;
  ranking_method: string;
  limitations: string[];
}

export interface AgentReport {
  agent: string;
  summary: string;
  cost_status?: string | null;
  findings: string[];
  evidence: string[];
  unknowns: string[];
  recommendation: string;
  recommended_candidate_id?: string | null;
  status: string;
}

export interface AgentConflict {
  dimension?: string;
  description?: string;
  agents_involved?: string[];
  details?: Record<string, any>;
}

export interface AgentConsensus {
  candidate_id?: string | null;
  agreement: string;
  reasoning: string[];
  conflicts: AgentConflict[];
  ml_alignment: boolean;
}

export interface MultiAgentDecision {
  financial: AgentReport;
  risk: AgentReport;
  architect: AgentReport;
  consensus: AgentConsensus;
}

export interface WhatIfCandidateResponse {
  success: boolean;
  target_component_id: string;
  target_component_name?: string;
  action: string;
  source_environment: string;
  original_baseline?: WhatIfBaselineResult | null;
  candidate_count: number;
  candidates: WhatIfCandidate[];
  scenario?: Record<string, any> | null;
  simulation_results: Array<Record<string, any>>;
  extracted_features: CandidateFeatureSet[];
  ml_ranking: MLRankingItem[];
  ranking: MLRankingItem[];
  recommended_candidate_id?: string | null;
  recommendation?: MLRecommendationSummary | null;
  ranking_status: string;
  ranking_method?: string | null;
  evidence: string[];
  missing_data: string[];
  limitations: string[];
  agents?: MultiAgentDecision | null;
  consensus?: AgentConsensus | null;
  financial_analyst?: AgentReport | null;
  risk_analyst?: AgentReport | null;
  system_architect?: AgentReport | null;
  error?: string | null;
}

export interface SimulationRequest {
  target_component_id?: string;
  component_id?: string;
  action?: string;
  use_ml_recommendation?: boolean;
  destination_env?: string;
  target_environment?: string;
  source_environment?: string;
  use_ai?: boolean;
}

export interface ConstraintsEvaluation {
  cost_impact?: number | null;
  cost_impact_display: string;
  resilience: string;
  risk_reduction: string;
  risk_score_before: number;
  risk_score_after: number;
  downtime_minutes: number;
  downtime_display: string;
  blast_radius_before: number;
  blast_radius_after: number;
  performance: string;
}

export interface FeasibleSolution {
  id: string;
  name?: string | null;
  title?: string | null;
  description: string;
  risk_level?: string;
  strategy_type?: string;
  action_type?: string | null;
  expected_impact?: string | null;
  is_feasible?: boolean;
  feasibility_reason?: string | null;
  constraints_evaluation?: ConstraintsEvaluation | null;
  changes?: Record<string, any>;
  estimated_downtime_minutes?: number | null;
  cost_delta_monthly?: number | null;
  feasibility_score?: number | null;
  predicted_suitability?: number | null;
  suitability_percentage?: number | null;
  confidence?: string;
  confidence_score?: number | null;
  supporting_features: string[];
  rank?: number;
  ml_derived?: boolean;
  missing_data: string[];
  prerequisites: string[];
  pros: string[];
  cons: string[];
  implementation_steps: string[];
}

export interface SimulationResult {
  target_component_id?: string | null;
  component_id?: string | null;
  target_component: string;
  action: string;
  change_action: string;
  recommended_action?: string | null;
  destination?: string | null;
  target_environment?: string | null;
  source_environment?: string | null;
  total_nodes_affected: number;
  affected_count: number;
  blast_radius: number;
  affected_components: any[];
  affected_components_details?: Array<Record<string, any>>;
  affected_component_names: string[];
  upstream_impact_count: number;
  upstream_impact: Array<Record<string, any>>;
  downstream_dependencies_count: number;
  downstream_dependencies: Array<Record<string, any>>;
  blast_radius_nodes: string[];
  risk_score: number;
  risk_level: string;
  estimated_downtime_minutes?: number | null;
  cost_delta_monthly?: number | null;
  cost_impact?: number | null;
  critical_flags: string[];
  critical_warnings: string[];
  risk_factors: Record<string, any> | any[];
  feasible_solutions: FeasibleSolution[];
  recommendations: string[];
  ml_confidence?: number | null;
  ml_reasoning_features?: any[] | null;
  ai_explanation?: string | null;
  ai_recommendation?: string | null;
  structured_explanation?: any;
  financial_analysis?: string | null;
  risk_analysis?: string | null;
  architect_recommendation?: string | null;
  financial_summary?: Record<string, any> | null;
  risk_summary?: Record<string, any> | null;
  architect_summary?: Record<string, any> | null;
  recommended_actions?: string[];
  missing_data: string[];
  environment_source?: string;
  is_manual: boolean;
  configured_assumptions?: Record<string, any> | null;
}

export interface FeasibleSolutionsGenerateRequest {
  target_component_id: string;
  current_simulation?: Record<string, any> | null;
  simulation_result?: Record<string, any> | null;
}

export interface FeasibleSolutionsResponse {
  success: boolean;
  target_component_id: string;
  target_component_name: string;
  problem_identified?: string | null;
  problem_summary?: string | null;
  total_candidate_solutions?: number;
  feasible_solutions: FeasibleSolution[];
  solutions: FeasibleSolution[];
  message?: string | null;
}

export interface BeforeAfterComparison {
  affected_resources: Record<string, any>;
  dependency_count: Record<string, any>;
  blast_radius: Record<string, any>;
  risk: Record<string, any>;
  downtime: Record<string, any>;
  cost: Record<string, any>;
  resilience: Record<string, any>;
  performance: Record<string, any>;
}

export interface ApplySolutionRequest {
  solution_id: string;
  target_component_id: string;
  solution?: FeasibleSolution | null;
  solution_data?: Record<string, any> | null;
}

export interface ApplySolutionResponse {
  success: boolean;
  applied_solution: FeasibleSolution;
  is_live_aws: boolean;
  warning_banner?: string | null;
  before_after_comparison: BeforeAfterComparison;
  ai_explanation?: string | null;
  ai_structured_explanation?: Record<string, any> | null;
  updated_simulation?: Record<string, any> | null;
}
