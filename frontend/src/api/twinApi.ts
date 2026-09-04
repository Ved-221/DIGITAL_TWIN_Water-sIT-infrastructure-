/**
 * Digital Twin API Service
 * Covers state, components, dependencies, metrics, impact, SPOF, and generic builder endpoints.
 */

import { apiClient } from './client';
import type {
  Component,
  Dependency,
  TwinState,
  TwinStats,
  MetricSnapshot,
  ComponentImpact,
  SPOFItem,
  NaturalLanguageParseRequest,
  ParsedDigitalTwinPreview,
  ApplyParsedTwinRequest,
  ApplyParsedTwinResponse,
  StructuredTwinBuildRequest,
  ManualComponentCreate,
  ManualComponentUpdate,
  ManualDependencyCreate,
  ManualEnvironmentResponse,
} from '../types/twin';

export const twinApi = {
  /**
   * Retrieves the current digital twin mode, authentication, and discovery status.
   */
  async getState(): Promise<TwinState> {
    return apiClient.get<TwinState>('/twin/state');
  },

  /**
   * Retrieves active digital twin components, optionally filtered by source environment.
   */
  async getComponents(sourceEnvironment?: string): Promise<Component[]> {
    return apiClient.get<Component[]>('/twin/components', {
      source_environment: sourceEnvironment,
    });
  },

  /**
   * Retrieves verified digital twin dependencies, optionally filtered by source environment.
   */
  async getDependencies(sourceEnvironment?: string): Promise<Dependency[]> {
    return apiClient.get<Dependency[]>('/twin/dependencies', {
      source_environment: sourceEnvironment,
    });
  },

  /**
   * Retrieves high-level digital twin estate statistics and counts.
   */
  async getStats(): Promise<TwinStats> {
    return apiClient.get<TwinStats>('/twin/stats');
  },

  /**
   * Retrieves the latest operational telemetry snapshots across all resources.
   */
  async getLatestMetrics(): Promise<MetricSnapshot[]> {
    return apiClient.get<MetricSnapshot[]>('/twin/metrics/latest');
  },

  /**
   * Retrieves detailed topology impact, direct/transitive callers, downstream targets, and SPOF status.
   */
  async getComponentImpact(componentId: string): Promise<ComponentImpact> {
    return apiClient.get<ComponentImpact>(`/twin/components/${encodeURIComponent(componentId)}/impact`);
  },

  /**
   * Retrieves Single Points of Failure (SPOF) for the requested environment.
   */
  async getSPOF(sourceEnvironment: string = 'aws'): Promise<SPOFItem[]> {
    return apiClient.get<SPOFItem[]>('/twin/spof', {
      source_environment: sourceEnvironment,
    });
  },

  /**
   * Parses natural language system descriptions into structured components and dependencies preview.
   */
  async parseDescription(request: NaturalLanguageParseRequest): Promise<ParsedDigitalTwinPreview> {
    return apiClient.post<ParsedDigitalTwinPreview>('/twin/build/parse-description', request);
  },

  /**
   * Commits a confirmed natural-language preview into the digital twin database.
   */
  async applyParsedTwin(request: ApplyParsedTwinRequest): Promise<ApplyParsedTwinResponse> {
    return apiClient.post<ApplyParsedTwinResponse>('/twin/build/apply', request);
  },

  /**
   * Builds and persists a domain-neutral digital twin directly from structured JSON definitions.
   */
  async applyStructuredTwin(request: StructuredTwinBuildRequest): Promise<ApplyParsedTwinResponse> {
    return apiClient.post<ApplyParsedTwinResponse>('/twin/build/structured', request);
  },

  /**
   * Switches active mode to live AWS.
   */
  async activateAWS(): Promise<{ success: boolean; message?: string }> {
    return apiClient.post<{ success: boolean; message?: string }>('/aws/activate');
  },

  /**
   * Switches active mode to manual builder.
   */
  async activateManual(): Promise<{ success: boolean; message?: string }> {
    return apiClient.post<{ success: boolean; message?: string }>('/manual/activate');
  },

  /**
   * Starts a clean manual infrastructure builder environment.
   */
  async startManual(): Promise<ManualEnvironmentResponse> {
    return apiClient.post<ManualEnvironmentResponse>('/manual/start');
  },

  /**
   * Creates a new manual infrastructure component.
   */
  async createManualComponent(data: ManualComponentCreate): Promise<Component> {
    return apiClient.post<Component>('/manual/components', data);
  },

  /**
   * Updates properties of an existing manual component.
   */
  async updateManualComponent(componentId: string, data: ManualComponentUpdate): Promise<Component> {
    return apiClient.put<Component>(`/manual/components/${encodeURIComponent(componentId)}`, data);
  },

  /**
   * Deletes a manual component and cascades all incident dependencies.
   */
  async deleteManualComponent(componentId: string): Promise<{ success: boolean; message?: string }> {
    return apiClient.delete<{ success: boolean; message?: string }>(`/manual/components/${encodeURIComponent(componentId)}`);
  },

  /**
   * Creates a verified dependency edge between two manual components.
   */
  async createManualDependency(data: ManualDependencyCreate): Promise<Dependency> {
    return apiClient.post<Dependency>('/manual/dependencies', data);
  },

  /**
   * Deletes a manual dependency edge.
   */
  async deleteManualDependency(dependencyId: string): Promise<{ success: boolean; message?: string }> {
    return apiClient.delete<{ success: boolean; message?: string }>(`/manual/dependencies/${encodeURIComponent(dependencyId)}`);
  },

  /**
   * Clears all user-created manual infrastructure and dependencies.
   */
  async clearManualEstate(): Promise<{ success: boolean; message?: string }> {
    return apiClient.post<{ success: boolean; message?: string }>('/manual/clear');
  },
};
