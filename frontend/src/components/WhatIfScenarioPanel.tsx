import React, { useState, useEffect } from 'react';
import classNames from 'classnames';
import { 
  X, AlertTriangle, 
  RefreshCw, Info, ShieldCheck, ShieldAlert, Zap, 
  ArrowUpCircle, Database, GitFork, Server, CheckCircle2, 
  Sliders, Layers
} from 'lucide-react';
import { whatIfApi } from '../api/whatIfApi';
import { twinApi } from '../api/twinApi';
import type { 
  WhatIfCandidateResponse, 
  WhatIfCandidate, 
  WhatIfBaselineResult 
} from '../types/whatIf';
import type { ComponentImpact } from '../types/twin';
import { formatINR } from '../utils/localization';

interface WhatIfScenarioPanelProps {
  isOpen: boolean;
  targetNode: any | null;
  sourceEnvironment?: string;
  onClose: () => void;
  onSimulationComplete?: (result: WhatIfCandidateResponse) => void;
}

interface ActionOption {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  category: 'resilience' | 'scaling' | 'lifecycle' | 'failure';
}

const SUPPORTED_ACTIONS: ActionOption[] = [
  {
    id: 'fail',
    name: 'Component Outage / Failure',
    description: 'Simulate what happens if this node suffers a hardware, software, or network outage.',
    icon: <AlertTriangle size={16} className="text-red-400" />,
    category: 'failure',
  },
  {
    id: 'scale_up',
    name: 'Scale Up Compute & Capacity',
    description: 'Simulate doubling CPU and memory capacity to handle higher operational loads.',
    icon: <ArrowUpCircle size={16} className="text-cyan-400" />,
    category: 'scaling',
  },
  {
    id: 'multi_az_modernize',
    name: 'Multi-AZ Standby Modernization',
    description: 'Simulate adding a standby replica in a second availability zone with automated failover.',
    icon: <ShieldCheck size={16} className="text-emerald-400" />,
    category: 'resilience',
  },
  {
    id: 'read_replica_offload',
    name: 'Read Replica Offloading',
    description: 'Simulate provisioning a dedicated read replica to offload intensive query traffic.',
    icon: <Database size={16} className="text-amber-400" />,
    category: 'resilience',
  },
  {
    id: 'dependency_circuit_breaker',
    name: 'Circuit Breaker / Queue Decoupling',
    description: 'Simulate inserting an asynchronous buffer queue to decouple synchronous callers.',
    icon: <Zap size={16} className="text-purple-400" />,
    category: 'resilience',
  },
  {
    id: 'phased_blue_green',
    name: 'Phased Blue/Green Shadow Cutover',
    description: 'Simulate staged traffic migration using a parallel shadow instance with dual-run sync.',
    icon: <GitFork size={16} className="text-blue-400" />,
    category: 'lifecycle',
  },
  {
    id: 'migrate',
    name: 'Cloud / Estate Migration',
    description: 'Simulate re-hosting this component to cloud or an alternative infrastructure provider.',
    icon: <Server size={16} className="text-indigo-400" />,
    category: 'lifecycle',
  },
  {
    id: 'remove',
    name: 'Decommission / Node Removal',
    description: 'Simulate retiring this component and safely severing its incident dependencies.',
    icon: <X size={16} className="text-rose-400" />,
    category: 'lifecycle',
  },
];

export const WhatIfScenarioPanel: React.FC<WhatIfScenarioPanelProps> = ({
  isOpen,
  targetNode,
  sourceEnvironment = 'aws',
  onClose,
  onSimulationComplete,
}) => {
  const [selectedAction, setSelectedAction] = useState<string>('fail');
  const [targetEnvParam, setTargetEnvParam] = useState<string>('cloud');
  
  // Pre-run topological impact
  const [impactData, setImpactData] = useState<ComponentImpact | null>(null);
  const [loadingImpact, setLoadingImpact] = useState<boolean>(false);

  // What-If Execution states
  const [simulating, setSimulating] = useState<boolean>(false);
  const [simulationStage, setSimulationStage] = useState<string>('');
  const [whatIfResponse, setWhatIfResponse] = useState<WhatIfCandidateResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Fetch contextual pre-run impact whenever a target node is provided
  useEffect(() => {
    if (!targetNode || !isOpen) {
      setImpactData(null);
      setWhatIfResponse(null);
      setErrorMessage(null);
      return;
    }

    let isMounted = true;
    setLoadingImpact(true);
    setWhatIfResponse(null);
    setErrorMessage(null);

    twinApi
      .getComponentImpact(targetNode.id)
      .then((data) => {
        if (isMounted) setImpactData(data);
      })
      .catch((err) => {
        console.debug('Optional component impact lookup:', err);
      })
      .finally(() => {
        if (isMounted) setLoadingImpact(false);
      });

    return () => {
      isMounted = false;
    };
  }, [targetNode, isOpen]);

  if (!isOpen || !targetNode) return null;

  // Execute What-If API
  const handleRunWhatIf = async () => {
    setSimulating(true);
    setSimulationStage('Analyzing dependency graph...');
    setErrorMessage(null);

    try {
      // Step 1 progress indication
      await new Promise((resolve) => setTimeout(resolve, 250));
      setSimulationStage('Simulating scenario on isolated graph clones...');

      const effectiveEnv = sourceEnvironment || targetNode.source_environment || 'aws';
      const response = await whatIfApi.getCandidates({
        target_component_id: targetNode.id,
        action: selectedAction,
        source_environment: effectiveEnv,
      });

      if (!response.success && response.error) {
        throw new Error(response.error);
      }

      setWhatIfResponse(response);
      if (onSimulationComplete) {
        onSimulationComplete(response);
      }
    } catch (err: any) {
      setErrorMessage(err?.message || 'Failed to simulate What-If scenario.');
    } finally {
      setSimulating(false);
      setSimulationStage('');
    }
  };

  const baseline: WhatIfBaselineResult | undefined = whatIfResponse?.original_baseline || undefined;
  const candidates: WhatIfCandidate[] = whatIfResponse?.candidates || [];

  const isAWSResource = targetNode.discovery_source === 'aws_api' || targetNode.arn != null;
  const isManualResource = targetNode.discovery_source === 'manual';
  const isDescribedResource = targetNode.discovery_source === 'user_description' || targetNode.source === 'user_description';

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full sm:w-[540px] bg-slate-900/95 backdrop-blur-md border-l border-slate-700/80 shadow-2xl flex flex-col transition-all duration-300 overflow-hidden font-sans">
      
      {/* Header Bar */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-purple-500/20">
            <Sliders size={16} />
          </div>
          <div>
            <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
              <span>What If?</span>
              <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
                Scenario Engine
              </span>
            </h2>
            <p className="text-[11px] text-slate-400">Simulate architectural changes against the Digital Twin</p>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          title="Close What-If Panel"
        >
          <X size={18} />
        </button>
      </div>

      {/* Dismissible Error Banner */}
      {errorMessage && (
        <div className="px-4 py-2.5 bg-red-950/90 border-b border-red-800 text-xs text-red-200 flex items-center justify-between z-10 shrink-0">
          <div className="flex items-center gap-2">
            <AlertTriangle size={15} className="text-red-400 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-red-300 hover:text-white p-1">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Scrollable Main Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-5">
        
        {/* 1. TARGET COMPONENT CARD */}
        <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800 space-y-3 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-[10px] font-bold tracking-wider uppercase text-slate-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
              Target Component
            </span>
            <span className={classNames(
              "text-[9px] font-mono px-2 py-0.5 rounded font-semibold",
              isAWSResource ? "bg-emerald-950 text-emerald-300 border border-emerald-800" :
              isDescribedResource ? "bg-indigo-950 text-indigo-300 border border-indigo-700" :
              isManualResource ? "bg-cyan-950 text-cyan-300 border border-cyan-800" :
              "bg-slate-800 text-slate-300"
            )}>
              {isAWSResource ? 'AWS RESOURCE' : isDescribedResource ? 'DESCRIBED TWIN' : isManualResource ? 'MANUAL' : 'BASELINE'}
            </span>
          </div>

          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-bold text-white leading-snug">{targetNode.name || targetNode.id}</h3>
              <div className="text-xs text-slate-400 capitalize mt-0.5">
                {targetNode.type?.replace('_', ' ')} • {targetNode.criticality || 'medium'} priority
              </div>
            </div>
            <div className="text-right shrink-0">
              <span className="font-mono text-xs font-semibold text-slate-300 block">
                {isManualResource || isDescribedResource ? formatINR(targetNode.cost_per_month ?? 0) : `$${targetNode.cost_per_month ?? 0}`}/mo
              </span>
              <span className="text-[10px] text-slate-500 block">Base Cost</span>
            </div>
          </div>

          {/* Contextual Pre-Run Impact Bar */}
          {loadingImpact ? (
            <div className="pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center gap-1.5">
              <RefreshCw size={11} className="animate-spin text-cyan-400" />
              <span>Analyzing graph impact...</span>
            </div>
          ) : impactData ? (
            <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                {impactData.in_degree} Inbound Callers
              </span>
              <span className="px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                {impactData.out_degree} Outbound Targets
              </span>
              <span className="px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-800">
                {impactData.upstream_impact_count} Transitive Dependents
              </span>
              {impactData.is_spof && (
                <span className="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-semibold flex items-center gap-1">
                  <ShieldAlert size={12} className="text-amber-400" />
                  <span>Single Point of Failure</span>
                </span>
              )}
            </div>
          ) : null}
        </div>

        {/* 2. CHOOSE WHAT-IF ACTION */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-300">
              What do you want to change?
            </label>
            <span className="text-[10px] font-mono text-slate-400">8 Supported Scenarios</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {SUPPORTED_ACTIONS.map((action) => {
              const isSelected = selectedAction === action.id;
              return (
                <button
                  key={action.id}
                  type="button"
                  onClick={() => setSelectedAction(action.id)}
                  className={classNames(
                    "p-3 rounded-xl border text-left transition-all flex flex-col justify-between gap-1.5",
                    isSelected
                      ? "bg-slate-800/90 border-purple-500 shadow-lg shadow-purple-950/30 ring-1 ring-purple-500/50"
                      : "bg-slate-950/50 border-slate-800 hover:border-slate-700 hover:bg-slate-850 text-slate-300"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <div className={classNames(
                      "w-7 h-7 rounded-lg flex items-center justify-center shrink-0 border",
                      isSelected ? "bg-purple-950/80 border-purple-700" : "bg-slate-900 border-slate-800"
                    )}>
                      {action.icon}
                    </div>
                    <span className="text-xs font-bold text-white leading-tight">
                      {action.name}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed line-clamp-2">
                    {action.description}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* 3. OPTIONAL ACTION CONFIGURATION */}
        {selectedAction === 'migrate' && (
          <div className="p-3.5 bg-slate-950/60 border border-slate-800 rounded-xl space-y-2 text-xs">
            <label className="block text-slate-300 font-semibold">Target Environment Destination</label>
            <select
              value={targetEnvParam}
              onChange={(e) => setTargetEnvParam(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-purple-500"
            >
              <option value="cloud">Cloud (AWS Managed)</option>
              <option value="on_prem">On-Premises Dedicated Server</option>
              <option value="hybrid">Hybrid Isolated Zone</option>
            </select>
          </div>
        )}

        {/* 4. EXECUTE BUTTON & SAFETY NOTICE */}
        <div className="space-y-2 pt-1">
          <button
            type="button"
            onClick={handleRunWhatIf}
            disabled={simulating}
            className="w-full py-3 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold transition flex items-center justify-center gap-2 shadow-lg shadow-purple-950/40 disabled:opacity-50"
          >
            {simulating ? (
              <>
                <RefreshCw size={15} className="animate-spin text-purple-200" />
                <span>{simulationStage || 'Simulating...'}</span>
              </>
            ) : (
              <>
                <Sliders size={15} className="text-purple-200" />
                <span>Run What-If Analysis</span>
              </>
            )}
          </button>

          <div className="text-[11px] text-slate-400 flex items-center justify-center gap-1.5 pt-0.5">
            <Info size={12} className="text-purple-400 shrink-0" />
            <span>This is a simulation. No live infrastructure will be changed.</span>
          </div>
        </div>

        {/* 5. BASELINE & SIMULATED IMPACT RESULTS */}
        {baseline && (
          <div className="space-y-4 pt-2 border-t border-slate-800">
            
            {/* CURRENT STATE BASELINE CARD */}
            <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="text-[10px] font-bold tracking-wider uppercase text-slate-400 flex items-center gap-1.5">
                  <Layers size={13} className="text-cyan-400" />
                  Baseline State Analysis
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  NetworkX Graph Engine
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                  <span className="text-[10px] text-slate-400 block mb-0.5">Risk Score</span>
                  <span className={classNames(
                    "text-base font-bold",
                    baseline.risk_level === 'CRITICAL' ? "text-red-400" :
                    baseline.risk_level === 'HIGH' ? "text-orange-400" :
                    baseline.risk_level === 'MODERATE' ? "text-amber-400" : "text-emerald-400"
                  )}>
                    {baseline.risk_score} <span className="text-[10px] font-normal text-slate-500">/ 100</span>
                  </span>
                </div>

                <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                  <span className="text-[10px] text-slate-400 block mb-0.5">Blast Radius</span>
                  <span className="text-base font-bold text-red-400">
                    {baseline.blast_radius} <span className="text-[10px] font-normal text-slate-500">nodes</span>
                  </span>
                </div>

                <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                  <span className="text-[10px] text-slate-400 block mb-0.5">Callers at Risk</span>
                  <span className="text-base font-bold text-amber-400">
                    {baseline.upstream_impact_count}
                  </span>
                </div>

                <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                  <span className="text-[10px] text-slate-400 block mb-0.5">SPOF Status</span>
                  <span className={classNames(
                    "text-xs font-bold block pt-1",
                    baseline.is_single_point_of_failure ? "text-red-400" : "text-emerald-400"
                  )}>
                    {baseline.is_single_point_of_failure ? 'Single Point of Failure' : 'Redundant'}
                  </span>
                </div>
              </div>

              {/* Missing data tags if reported by engine */}
              {whatIfResponse?.missing_data && whatIfResponse.missing_data.length > 0 && (
                <div className="text-[11px] bg-slate-900/60 p-2 rounded border border-slate-800 text-slate-400 flex items-start gap-1.5">
                  <Info size={12} className="text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="text-slate-300 font-medium">Missing Baseline Signals: </span>
                    <span>{whatIfResponse.missing_data.join(', ')}</span>
                  </div>
                </div>
              )}
            </div>

            {/* 6. CANDIDATE SOLUTIONS LIST */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <Zap size={14} className="text-purple-400" />
                  <span>Candidate Solutions ({candidates.length})</span>
                </span>
                <span className="text-[10px] text-slate-400 font-mono">Independently Simulated</span>
              </div>

              {candidates.length === 0 ? (
                <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800 text-xs text-slate-400 text-center">
                  No candidate remediation strategies generated for this specific action and topology.
                </div>
              ) : (
                <div className="space-y-3">
                  {candidates.map((cand) => {
                    const sim = cand.simulation_result;
                    const vs = sim?.vs_baseline;

                    return (
                      <div
                        key={cand.candidate_id}
                        className="p-4 bg-slate-950/80 border border-slate-800 rounded-xl space-y-3 hover:border-slate-700 transition shadow-sm"
                      >
                        {/* Candidate Top Header */}
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-white text-xs">{cand.name}</span>
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                                Simulated
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                              {cand.description}
                            </p>
                          </div>
                          <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-slate-900 text-purple-300 border border-purple-900/60 shrink-0">
                            {cand.strategy_type?.replace(/_/g, ' ')}
                          </span>
                        </div>

                        {/* Proposed Topological Changes */}
                        {cand.proposed_changes && cand.proposed_changes.length > 0 && (
                          <div className="bg-slate-900/50 p-2.5 rounded-lg border border-slate-800/80 space-y-1">
                            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                              Topological Mutations:
                            </span>
                            <ul className="list-disc list-inside text-[11px] text-slate-300 space-y-0.5">
                              {cand.proposed_changes.map((pc, i) => (
                                <li key={i}>{pc}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Independent Simulation Results Grid */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs pt-1">
                          <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                            <span className="text-[10px] text-slate-400 block">Simulated Risk</span>
                            <div className="font-bold text-white text-sm mt-0.5">
                              {sim?.risk_score != null ? sim.risk_score : 'N/A'}
                              {vs?.risk_score_delta != null && vs.risk_score_delta !== 0 && (
                                <span className={classNames(
                                  "text-[10px] font-mono ml-1 font-semibold",
                                  vs.risk_score_delta < 0 ? "text-emerald-400" : "text-amber-400"
                                )}>
                                  {vs.risk_score_delta < 0 ? '' : '+'}{vs.risk_score_delta}
                                </span>
                              )}
                            </div>
                          </div>

                          <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                            <span className="text-[10px] text-slate-400 block">Blast Radius</span>
                            <div className="font-bold text-white text-sm mt-0.5">
                              {sim?.blast_radius ?? 0}
                              {vs?.blast_radius_delta != null && vs.blast_radius_delta !== 0 && (
                                <span className={classNames(
                                  "text-[10px] font-mono ml-1 font-semibold",
                                  vs.blast_radius_delta < 0 ? "text-emerald-400" : "text-amber-400"
                                )}>
                                  {vs.blast_radius_delta < 0 ? '' : '+'}{vs.blast_radius_delta}
                                </span>
                              )}
                            </div>
                          </div>

                          <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                            <span className="text-[10px] text-slate-400 block">Est. Downtime</span>
                            <span className="font-bold text-white text-sm mt-0.5 block">
                              {sim?.estimated_downtime_minutes != null ? `${sim.estimated_downtime_minutes}m` : '0m'}
                            </span>
                          </div>

                          <div className="bg-slate-900 p-2 rounded border border-slate-800/80">
                            <span className="text-[10px] text-slate-400 block">Cost Delta</span>
                            <span className={classNames(
                              "font-bold text-sm mt-0.5 block",
                              (sim?.cost_delta_monthly ?? 0) > 0 ? "text-slate-200" : "text-emerald-400"
                            )}>
                              {sim?.cost_delta_monthly != null
                                ? `${sim.cost_delta_monthly > 0 ? '+' : ''}$${sim.cost_delta_monthly.toFixed(0)}/mo`
                                : '$0/mo'}
                            </span>
                          </div>
                        </div>

                        {/* SPOF Elimination & Feasibility Evidence */}
                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px]">
                          <div className="flex items-center gap-2">
                            {sim?.spof_eliminated ? (
                              <span className="text-emerald-400 font-semibold flex items-center gap-1">
                                <CheckCircle2 size={12} />
                                <span>Eliminates SPOF</span>
                              </span>
                            ) : (
                              <span className="text-slate-400">Maintains topology path</span>
                            )}

                            {cand.feasibility && (
                              <span className={classNames(
                                "px-1.5 py-0.2 rounded font-mono text-[9px] uppercase",
                                cand.feasibility === 'feasible' ? "bg-emerald-950 text-emerald-300 border border-emerald-800" :
                                cand.feasibility === 'conditional' ? "bg-amber-950 text-amber-300 border border-amber-800" :
                                "bg-slate-800 text-slate-300"
                              )}>
                                {cand.feasibility}
                              </span>
                            )}
                          </div>

                          {cand.evidence && cand.evidence.length > 0 && (
                            <span className="text-slate-400 italic text-[10px] truncate max-w-[240px]" title={cand.evidence.join('; ')}>
                              Evidence: {cand.evidence[0]}
                            </span>
                          )}
                        </div>

                        {/* Missing Data Notices */}
                        {cand.missing_data && cand.missing_data.length > 0 && (
                          <div className="text-[10px] text-slate-500 flex items-center gap-1 pt-0.5">
                            <Info size={11} className="text-slate-500" />
                            <span>Missing telemetry/cost signals: {cand.missing_data.join(', ')}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

          </div>
        )}

      </div>
    </div>
  );
};
