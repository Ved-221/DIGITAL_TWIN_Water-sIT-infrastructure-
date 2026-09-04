/**
 * Digital Twin Sandbox Execution Layer API Service
 * Handles isolated sandbox mutations, before-after diffs, rollbacks, and acceptances.
 */

import { apiClient } from './client';
import type {
  SandboxApplyRequest,
  SandboxApplyResponse,
  SandboxRollbackRequest,
  SandboxRollbackResponse,
  SandboxAcceptRequest,
  SandboxAcceptResponse,
  SandboxBeforeAfterResponse,
} from '../types/sandbox';

export const sandboxApi = {
  /**
   * Applies a selected candidate solution ONLY to an isolated SANDBOX environment.
   * Clones baseline rows, mutates topology in DB, rebuilds graph, re-simulates,
   * and returns structured Before vs After comparisons.
   */
  async apply(request: SandboxApplyRequest): Promise<SandboxApplyResponse> {
    return apiClient.post<SandboxApplyResponse>('/twin/sandbox/apply', request);
  },

  /**
   * Rolls back the sandbox environment to the captured baseline snapshot.
   * Restores original components and dependencies atomically.
   */
  async rollback(request: SandboxRollbackRequest): Promise<SandboxRollbackResponse> {
    return apiClient.post<SandboxRollbackResponse>('/twin/sandbox/rollback', request);
  },

  /**
   * Accepts the mutated sandbox state as the approved baseline.
   */
  async accept(request: SandboxAcceptRequest): Promise<SandboxAcceptResponse> {
    return apiClient.post<SandboxAcceptResponse>('/twin/sandbox/accept', request);
  },

  /**
   * Retrieves detailed Before vs After comparison and snapshot metrics.
   */
  async getBeforeAfter(snapshotId: string): Promise<SandboxBeforeAfterResponse> {
    return apiClient.get<SandboxBeforeAfterResponse>(`/twin/sandbox/before-after/${encodeURIComponent(snapshotId)}`);
  },
};
