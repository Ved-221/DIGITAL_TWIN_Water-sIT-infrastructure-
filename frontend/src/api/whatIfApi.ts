/**
 * What-If Simulation, Candidate Solutions, and Feasible Solutions API Service
 */

import { apiClient } from './client';
import type {
  WhatIfRequest,
  WhatIfCandidateResponse,
  MultiAgentDecision,
  SimulationRequest,
  SimulationResult,
  FeasibleSolutionsGenerateRequest,
  FeasibleSolutionsResponse,
  ApplySolutionRequest,
  ApplySolutionResponse,
} from '../types/whatIf';

export const whatIfApi = {
  /**
   * Generates multiple candidate solutions for a target component and change action.
   * Simulates each candidate independently, runs ML feature ranking, and obtains 3-agent reports.
   */
  async getCandidates(request: WhatIfRequest): Promise<WhatIfCandidateResponse> {
    return apiClient.post<WhatIfCandidateResponse>('/twin/what-if/candidates', request);
  },

  /**
   * Triggers Three-Agent (Financial, Risk, System Architect) expert consensus analysis.
   */
  async evaluateAgents(request: WhatIfRequest): Promise<MultiAgentDecision> {
    return apiClient.post<MultiAgentDecision>('/twin/what-if/agents/evaluate', request);
  },

  /**
   * Runs deterministic digital twin simulation and returns blast radius, risk, downtime, and cost impacts.
   */
  async simulate(request: SimulationRequest): Promise<SimulationResult> {
    return apiClient.post<SimulationResult>('/simulate', request);
  },

  /**
   * Generates feasible remediation solutions based on current simulation indications.
   */
  async generateFeasibleSolutions(request: FeasibleSolutionsGenerateRequest): Promise<FeasibleSolutionsResponse> {
    return apiClient.post<FeasibleSolutionsResponse>('/feasible-solutions/generate', request);
  },

  /**
   * Applies a feasible solution virtually to evaluate before vs after comparison.
   */
  async applyFeasibleSolution(request: ApplySolutionRequest): Promise<ApplySolutionResponse> {
    return apiClient.post<ApplySolutionResponse>('/feasible-solutions/apply', request);
  },
};
