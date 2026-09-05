/**
 * Digital Twin Sandbox Execution Layer Types matching backend/schemas.py
 */

export interface SandboxApplyRequest {
  source_environment?: string;
  target_component_id: string;
  candidate_id?: string | null;
  id?: string | null;
  solution_id?: string | null;
  action?: string;
  candidate_data?: Record<string, any> | null;
  sandbox_env_id?: string;
}

export interface SandboxApplyResponse {
  success: boolean;
  sandbox_id: string;
  target_environment: string;
  source_environment: string;
  target_component_id: string;
  original_component_id: string;
  candidate_id?: string | null;
  strategy_type?: string | null;
  snapshot_id: string;
  remediation_outcome: string;
  mutations_applied: string[];
  topology_diff: Record<string, any>;
  before: Record<string, any>;
  after: Record<string, any>;
  delta: Record<string, any>;
  tradeoffs: string[];
  missing_data: string[];
}

export interface SandboxRollbackRequest {
  snapshot_id: string;
  environment_id?: string;
  sandbox_id?: string | null;
  target_component_id?: string | null;
}

export interface SandboxRollbackResponse {
  restored: boolean;
  snapshot_id: string;
  environment_id: string;
  sandbox_id: string;
  components_count: number;
  dependencies_count: number;
  status: string;
}

export interface SandboxAcceptRequest {
  snapshot_id: string;
  environment_id?: string;
  sandbox_id?: string | null;
}

export interface SandboxAcceptResponse {
  accepted: boolean;
  snapshot_id: string;
  environment_id: string;
  sandbox_id: string;
  status: string;
}

export interface SandboxBeforeAfterResponse {
  snapshot_id: string;
  environment_id: string;
  status: string;
  solution_id?: string | null;
  solution_name?: string | null;
  strategy_type?: string | null;
  created_at?: string | null;
  baseline_components_count: number;
  current_components_count: number;
  baseline_dependencies_count: number;
  current_dependencies_count: number;
  baseline_monthly_cost: number;
  current_monthly_cost: number;
  monthly_cost_delta: number;
}
