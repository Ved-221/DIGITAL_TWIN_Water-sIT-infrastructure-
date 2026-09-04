/**
 * Digital Twin Component, Dependency, Environment, and Telemetry Types
 * Accurately matching backend Pydantic schemas in backend/schemas.py and backend/models.py
 */

export type ComponentType =
  | 'server'
  | 'database'
  | 'load_balancer'
  | 'storage'
  | 'vpc'
  | 'subnet'
  | 'security_group'
  | 'application'
  | 'api'
  | 'identity'
  | 'other';

export type EnvironmentEnum = 'cloud' | 'on_prem' | 'hybrid' | 'edge';

export type Criticality = 'low' | 'medium' | 'high' | 'critical';

export type Status = 'active' | 'inactive' | 'degraded' | 'terminated';

export interface Component {
  id: string;
  name: string;
  type: ComponentType | string;
  environment?: EnvironmentEnum | string;
  location?: string;
  criticality?: Criticality | string;
  owner?: string;
  status?: Status | string;
  cpu?: number | null;
  memory?: number | null;
  cost_per_month: number;
  arn?: string | null;
  aws_region?: string | null;
  discovery_source?: string;
  account_id?: string | null;
  availability_zone?: string | null;
  updated_at?: string | null;
  domain?: string;
  properties?: Record<string, any>;
  source?: string | null;
  source_id?: string | null;
  last_updated?: string | null;
  position_x?: number | null;
  position_y?: number | null;
  metadata_col?: Record<string, any>;
}

export interface ComponentPositionUpdate {
  position_x: number;
  position_y: number;
}

export interface Dependency {
  id: string;
  source_component_id: string;
  target_component_id: string;
  relationship_type: string;
  source?: string;
  criticality?: Criticality | string;
  metadata?: Record<string, any>;
  source_id?: string | null;
  target_id?: string | null;
  discovery_source?: string | null;
}

export interface TwinState {
  mode: 'unconnected' | 'live' | 'demo' | 'manual';
  authenticated: boolean;
  account_id?: string | null;
  arn?: string | null;
  region?: string | null;
  discovery_status: 'idle' | 'discovering' | 'completed' | 'empty' | 'failed';
  discovery_summary?: Record<string, any>;
  last_sync?: string | null;
  error?: string | null;
  total_components: number;
  total_dependencies: number;
}

export interface TwinStats {
  total_components: number;
  critical_services_count: number;
  total_monthly_cost: number;
  on_prem_count: number;
  cloud_count: number;
  currency?: string;
}

export interface MetricSnapshot {
  resource_id: string;
  timestamp: string;
  resource_type: string;
  cpu?: number | null;
  memory?: number | null;
  disk?: Record<string, any> | null;
  network_in?: number | null;
  network_out?: number | null;
  latency?: number | null;
  error_rate?: number | null;
  status?: string;
  raw_metrics?: Record<string, any>;
}

export interface DirectCallerTarget {
  component_id: string;
  relationship_type: string;
}

export interface DependentNode {
  component_id: string;
}

export interface ComponentImpact {
  component_id: string;
  name: string;
  in_degree: number;
  out_degree: number;
  direct_inbound_callers: DirectCallerTarget[];
  direct_outbound_targets: DirectCallerTarget[];
  upstream_dependents: DependentNode[];
  upstream_impact_count: number;
  downstream_dependencies: DependentNode[];
  downstream_dependency_count: number;
  is_spof: boolean;
  spof_reasons: string[];
}

export interface SPOFItem {
  id: string;
  component_id: string;
  name: string;
  type: string;
  criticality?: string;
  cost_per_month?: number;
  in_degree?: number;
  out_degree?: number;
  reason?: string;
}

export interface ManualAssumptions {
  cpu?: number | null;
  memory?: number | null;
  latency?: number | null;
  error_rate?: number | null;
  availability?: number | null;
}

export interface ManualComponentCreate {
  id?: string;
  name: string;
  type: ComponentType | string;
  criticality?: Criticality | string;
  environment?: EnvironmentEnum | string;
  location?: string;
  owner?: string;
  cost_per_month?: number;
  source_environment?: string;
  assumptions?: ManualAssumptions;
  metadata?: Record<string, any>;
}

export interface ManualComponentUpdate {
  name?: string;
  type?: ComponentType | string;
  criticality?: Criticality | string;
  environment?: EnvironmentEnum | string;
  location?: string;
  owner?: string;
  cost_per_month?: number;
  assumptions?: ManualAssumptions;
  metadata?: Record<string, any>;
}

export interface ManualDependencyCreate {
  source_component_id?: string;
  target_component_id?: string;
  source_id?: string;
  target_id?: string;
  relationship_type: string;
  criticality?: Criticality | string;
  source_environment?: string;
  metadata?: Record<string, any>;
}

export interface ManualEnvironmentResponse {
  success: boolean;
  message: string;
  mode: string;
  total_components: number;
  total_dependencies: number;
}

export interface EnvironmentSchema {
  id: string;
  name: string;
  provider?: string;
  source_type?: string;
  is_active: boolean;
  status?: string;
  created_at?: string | null;
}

export interface EnvironmentCreate {
  name: string;
  provider?: string;
}

export interface NaturalLanguageParseRequest {
  description: string;
  domain?: string;
}

export interface ParsedComponentPreview {
  temp_id: string;
  name: string;
  type: string;
  domain?: string;
  status?: string;
  criticality?: string;
  properties?: Record<string, any>;
  metrics?: Record<string, any> | null;
  metadata?: Record<string, any>;
  source?: string;
  source_id?: string | null;
  raw_mention?: string | null;
}

export interface ParsedDependencyPreview {
  source_temp_id: string;
  target_temp_id: string;
  source_name: string;
  target_name: string;
  relationship_type: string;
  source?: string;
  explicit_quote?: string | null;
  metadata?: Record<string, any>;
}

export interface ParsedDigitalTwinPreview {
  success: boolean;
  domain: string;
  raw_description: string;
  components: ParsedComponentPreview[];
  dependencies: ParsedDependencyPreview[];
  ambiguities: string[];
  source: string;
}

export interface ApplyParsedTwinRequest {
  domain?: string;
  components: ParsedComponentPreview[];
  dependencies: ParsedDependencyPreview[];
  clear_existing?: boolean;
}

export interface ApplyParsedTwinResponse {
  success: boolean;
  message: string;
  components_count: number;
  dependencies_count: number;
  components: Component[];
  dependencies: Dependency[];
}

export interface StructuredTwinBuildRequest {
  domain?: string;
  components: Array<Record<string, any>>;
  dependencies: Array<Record<string, any>>;
  clear_existing?: boolean;
}
