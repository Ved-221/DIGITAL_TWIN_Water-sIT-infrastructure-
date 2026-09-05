import React, { useState, useEffect, useMemo } from 'react';
import classNames from 'classnames';
import { 
  X, AlertTriangle, 
  RefreshCw, Info, ShieldCheck, ShieldAlert, Zap, 
  ArrowUpCircle, Database, GitFork, Server, CheckCircle2, 
  Sliders, Layers, Star, Award, Sparkles, GitCompare
} from 'lucide-react';
import { whatIfApi } from '../api/whatIfApi';
import { twinApi } from '../api/twinApi';
import { sandboxApi } from '../api/sandboxApi';
import { ThreeAgentsView } from './ThreeAgentsView';
import { SolutionReviewView } from './SolutionReviewView';
import type { 
  WhatIfCandidateResponse, 
  WhatIfCandidate, 
  WhatIfBaselineResult,
  MultiAgentDecision
} from '../types/whatIf';
import type { SandboxApplyResponse } from '../types/sandbox';
import type { ComponentImpact } from '../types/twin';
import { formatINR } from '../utils/localization';

interface WhatIfScenarioPanelProps {
  isOpen: boolean;
  targetNode: any | null;
  rawDependencies?: any[];
  rawComponents?: any[];
  metricsMap?: Record<string, any>;
  recommendations?: Record<string, any>;
  sourceEnvironment?: string;
  onClose: () => void;
  onSimulationComplete?: (result: WhatIfCandidateResponse) => void;
  onApplySolutionToSandbox?: (result: SandboxApplyResponse) => void;
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
  rawDependencies = [],
  rawComponents = [],
  metricsMap: _metricsMap = {},
  recommendations: _recommendations = {},
  sourceEnvironment = 'aws',
  onClose,
  onSimulationComplete,
  onApplySolutionToSandbox,
}) => {
  // 1. All state hooks declared unconditionally at top level
  const [selectedAction, setSelectedAction] = useState<string>('fail');
  const [targetEnvParam, setTargetEnvParam] = useState<string>('cloud');
  
  // Pre-run topological impact state
  const [impactData, setImpactData] = useState<ComponentImpact | null>(null);
  const [loadingImpact, setLoadingImpact] = useState<boolean>(false);

  // What-If Execution states
  const [simulating, setSimulating] = useState<boolean>(false);
  const [simulationStage, setSimulationStage] = useState<string>('');
  const [whatIfResponse, setWhatIfResponse] = useState<WhatIfCandidateResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Agent evaluation states
  const [agentsDecision, setAgentsDecision] = useState<MultiAgentDecision | null>(null);
  const [loadingAgents, setLoadingAgents] = useState<boolean>(false);

  // Solution Review & Sandbox Transformation states
  const [selectedCandidateForReview, setSelectedCandidateForReview] = useState<WhatIfCandidate | null>(null);
  const [isApplyingSolution, setIsApplyingSolution] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  // 2. Normalization memo hook - safe access regardless of object shape
  const normalizedNode = useMemo(() => {
    if (!targetNode) return null;
    const data = targetNode.data || {};
    const id = targetNode.id || data.id || '';
    const name = targetNode.name || data.name || targetNode.label || data.label || id || 'Selected Component';
    const type = targetNode.type || data.type || 'service';
    const status = targetNode.status || data.status || 'healthy';
    const criticality = targetNode.criticality || data.criticality || 'medium';
    const cost = targetNode.cost_per_month ?? data.cost_per_month ?? 0;
    const discoverySource = targetNode.discovery_source || data.discovery_source || targetNode.source || data.source;
    const arn = targetNode.arn || data.arn || null;
    const env = targetNode.environment || data.environment || sourceEnvironment;

    return {
      ...data,
      ...targetNode,
      id,
      name,
      type,
      status,
      criticality,
      cost_per_month: cost,
      discovery_source: discoverySource,
      arn,
      environment: env,
    };
  }, [targetNode, sourceEnvironment]);

  // 3. Direct dependencies memo hook
  const { directCallers, directDownstreams } = useMemo(() => {
    if (!normalizedNode?.id) return { directCallers: [], directDownstreams: [] };

    const compMap = new Map<string, string>();
    (rawComponents || []).forEach((c: any) => {
      compMap.set(c.id, c.name || c.id);
    });

    const callers: Array<{ id: string; name: string }> = [];
    const downstreams: Array<{ id: string; name: string }> = [];

    (rawDependencies || []).forEach((d: any) => {
      const srcId = d.source_component_id || d.source_id;
      const tgtId = d.target_component_id || d.target_id;

      if (tgtId === normalizedNode.id && srcId) {
        callers.push({ id: srcId, name: compMap.get(srcId) || srcId });
      }
      if (srcId === normalizedNode.id && tgtId) {
        downstreams.push({ id: tgtId, name: compMap.get(tgtId) || tgtId });
      }
    });

    return { directCallers: callers, directDownstreams: downstreams };
  }, [normalizedNode, rawDependencies, rawComponents]);

  // 4. ML ranking & candidates memo hooks - declared UNCONDITIONALLY
  const baseline: WhatIfBaselineResult | undefined = whatIfResponse?.original_baseline || undefined;
  const rawCandidates: WhatIfCandidate[] = whatIfResponse?.candidates || [];

  const rankingMap = useMemo(() => {
    if (!whatIfResponse?.ml_ranking) return new Map<string, any>();
    return new Map(whatIfResponse.ml_ranking.map((r) => [r.candidate_id, r]));
  }, [whatIfResponse]);

  const isMLRanked = whatIfResponse?.ranking_status === 'ranked' && (whatIfResponse?.ml_ranking?.length ?? 0) > 0;

  const displayedCandidates = useMemo(() => {
    if (!rawCandidates || rawCandidates.length === 0) return [];
    if (!isMLRanked) return rawCandidates;
    return [...rawCandidates].sort((a, b) => {
      const rankA = rankingMap.get(a.candidate_id)?.rank ?? 999;
      const rankB = rankingMap.get(b.candidate_id)?.rank ?? 999;
      return rankA - rankB;
    });
  }, [rawCandidates, isMLRanked, rankingMap]);

  // 5. Fetch contextual pre-run impact whenever a target node is provided
  useEffect(() => {
    if (!normalizedNode?.id || !isOpen) {
      setImpactData(null);
      setWhatIfResponse(null);
      setAgentsDecision(null);
      setSelectedCandidateForReview(null);
      setApplyError(null);
      setErrorMessage(null);
      return;
    }

    let isMounted = true;
    setLoadingImpact(true);
    setWhatIfResponse(null);
    setAgentsDecision(null);
    setSelectedCandidateForReview(null);
    setApplyError(null);
    setErrorMessage(null);

    twinApi
      .getComponentImpact(normalizedNode.id)
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
  }, [normalizedNode?.id, isOpen]);

  // 6. Early return ONLY after all hooks have been invoked
  if (!isOpen || !normalizedNode) return null;

  // Execute What-If API - ONLY executed on user click, never automatically on open
  const handleRunWhatIf = async () => {
    if (!normalizedNode?.id) return;

    setSimulating(true);
    setSimulationStage('Analyzing dependency graph...');
    setErrorMessage(null);

    try {
      await new Promise((resolve) => setTimeout(resolve, 200));
      setSimulationStage('Simulating scenario on isolated graph clones...');

      const effectiveEnv = normalizedNode.source_environment || normalizedNode.environment || sourceEnvironment || 'manual';
      const response = await whatIfApi.getCandidates({
        target_component_id: normalizedNode.id,
        action: selectedAction,
        source_environment: effectiveEnv,
      });

      if (!response.success && response.error) {
        throw new Error(response.error);
      }

      setWhatIfResponse(response);
      if (response.agents) {
        setAgentsDecision(response.agents);
      }
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

  const handleGetExpertAnalysis = async () => {
    if (!normalizedNode?.id) return;
    setLoadingAgents(true);
    setErrorMessage(null);
    try {
      const effectiveEnv = normalizedNode.source_environment || normalizedNode.environment || sourceEnvironment || 'manual';
      const result = await whatIfApi.evaluateAgents({
        target_component_id: normalizedNode.id,
        action: selectedAction,
        source_environment: effectiveEnv,
      });
      setAgentsDecision(result);
    } catch (err: any) {
      if (whatIfResponse?.agents) {
        setAgentsDecision(whatIfResponse.agents);
      } else {
        setErrorMessage(err?.message || 'Failed to analyze candidates with expert agents.');
      }
    } finally {
      setLoadingAgents(false);
    }
  };

  const isAWSResource = normalizedNode?.discovery_source === 'aws_api' || 
                        normalizedNode?.source_environment === 'aws' || 
                        normalizedNode?.arn != null;
  const isManualResource = normalizedNode?.discovery_source === 'manual' || 
                           normalizedNode?.discovery_source === 'user_description' ||
                           normalizedNode?.source === 'user_description' ||
                           normalizedNode?.source_environment === 'manual';
  const isDescribedResource = normalizedNode?.discovery_source === 'user_description' || normalizedNode?.source === 'user_description';
  const isSpof = impactData?.is_spof || false;

  const handleApplyToSandbox = async (candidate: WhatIfCandidate) => {
    if (!normalizedNode?.id) return;
    setIsApplyingSolution(true);
    setApplyError(null);
    try {
      // Determine effective environment based on the component's true origin
      let effectiveEnv: string;
      if (isAWSResource) {
        effectiveEnv = 'aws';
      } else if (isManualResource) {
        effectiveEnv = 'manual';
      } else {
        effectiveEnv = sourceEnvironment === 'aws' ? 'aws' : 'manual';
      }

      // Sanitize target component ID: prevent duplicate sb- prefixes
      let cleanTargetId = normalizedNode.id;
      while (cleanTargetId.startsWith('sb-sb-')) {
        cleanTargetId = cleanTargetId.slice(3);
      }
      const candId = candidate.candidate_id || candidate.id || (candidate as any).solution_id;

      const res = await sandboxApi.apply({
        source_environment: effectiveEnv,
        target_component_id: cleanTargetId,
        candidate_id: candId,
        id: candId,
        solution_id: candId,
        action: selectedAction,
        candidate_data: candidate as any,
        sandbox_env_id: 'sandbox'
      });
      if (onApplySolutionToSandbox) {
        onApplySolutionToSandbox(res);
      }
      setSelectedCandidateForReview(null);
      onClose();
    } catch (err: any) {
      console.error("Failed to apply candidate to sandbox:", err);
      setApplyError(err?.message || 'Failed to transform Digital Twin sandbox.');
    } finally {
      setIsApplyingSolution(false);
    }
  };


  return (
    <>
      {/* Subtle Backdrop - allows existing Twin topology to remain visible behind it */}
      <div 
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px] transition-opacity duration-200"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* What-If Right-Side Overlay Drawer */}
      <aside 
        aria-label="What-If Scenario Drawer"
        className="fixed inset-y-0 right-0 z-50 w-full sm:w-[560px] md:w-[600px] max-w-full bg-slate-900/98 backdrop-blur-md border-l border-slate-700/80 shadow-2xl flex flex-col transition-transform duration-300 overflow-hidden font-sans"
      >
        
        {/* Header Bar */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-purple-500/20">
              <Sliders size={16} />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                <span>WHAT-IF ANALYSIS</span>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
                  Scenario Engine
                </span>
              </h2>
              <p className="text-[11px] text-slate-400">Simulate architectural changes inside the Digital Twin</p>
            </div>
          </div>

          <button
            type="button"
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
              <div>
                <span className="font-bold block">What-If analysis could not be loaded.</span>
                <span className="text-[11px] opacity-90">{errorMessage}</span>
              </div>
            </div>
            <button 
              type="button"
              onClick={() => setErrorMessage(null)} 
              className="text-red-300 hover:text-white p-1"
            >
              <X size={14} />
            </button>
          </div>
        )}

        {/* Scrollable Main Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {selectedCandidateForReview ? (
            <SolutionReviewView
              candidate={selectedCandidateForReview}
              baseline={baseline || (whatIfResponse as any)?.baseline || null}
              targetNode={normalizedNode}
              sourceEnvironment={sourceEnvironment}
              isApplying={isApplyingSolution}
              applyError={applyError}
              onApply={() => handleApplyToSandbox(selectedCandidateForReview)}
              onCancel={() => {
                setSelectedCandidateForReview(null);
                setApplyError(null);
              }}
            />
          ) : (
            <>
              {/* 1. TARGET COMPONENT CARD */}
              <div className="bg-slate-950/70 p-4 rounded-xl border border-slate-800 space-y-3.5 shadow-sm">
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
                    {isAWSResource ? 'AWS RESOURCE' : isDescribedResource ? 'DESCRIBED TWIN' : isManualResource ? 'MANUAL' : 'DIGITAL TWIN'}
                  </span>
                </div>

                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="text-[10px] text-slate-400 font-mono uppercase block">Target:</span>
                    <h3 className="text-lg font-bold text-white leading-snug">{normalizedNode.name}</h3>
                    <div className="text-xs text-slate-400 capitalize mt-0.5">
                      {normalizedNode.type?.replace('_', ' ')} {normalizedNode.environment ? `• ${normalizedNode.environment}` : ''}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="font-mono text-xs font-semibold text-slate-300 block">
                      {isManualResource || isDescribedResource ? formatINR(normalizedNode.cost_per_month ?? 0) : `$${normalizedNode.cost_per_month ?? 0}`}/mo
                    </span>
                    <span className="text-[10px] text-slate-500 block">Base Cost</span>
                  </div>
                </div>

                {/* Status & Risk Indicators */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                  {/* Current Status */}
                  <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Current Status</span>
                    <div className="flex items-center gap-1.5">
                      <span className={classNames("w-2 h-2 rounded-full", normalizedNode.status === 'healthy' || normalizedNode.status === 'active' ? "bg-emerald-400" : "bg-amber-400")}></span>
                      <span className="text-xs font-semibold text-slate-200 capitalize">{normalizedNode.status || 'Active'}</span>
                    </div>
                  </div>

                  {/* Current Risk */}
                  <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Current Risk</span>
                    <div className="flex items-center gap-1.5">
                      {isSpof ? (
                        <>
                          <ShieldAlert size={14} className="text-red-400 shrink-0" />
                          <span className="text-xs font-bold text-red-400">High (Single Point of Failure)</span>
                        </>
                      ) : (
                        <>
                          <ShieldCheck size={14} className="text-emerald-400 shrink-0" />
                          <span className="text-xs font-semibold text-slate-200 capitalize">{normalizedNode.criticality || 'Normal'} Priority</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* Current Dependencies */}
                <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase font-bold text-slate-400">Current Dependencies</span>
                    <span className="text-[10px] font-mono text-slate-500">
                      {directCallers.length} callers • {directDownstreams.length} downstream
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300 flex flex-wrap gap-1.5">
                    {directCallers.length === 0 && directDownstreams.length === 0 ? (
                      <span className="text-slate-500 italic text-[10px]">No direct inbound/outbound dependencies</span>
                    ) : (
                      <>
                        {directCallers.map((c) => (
                          <span key={c.id} className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px] flex items-center gap-1">
                            <span className="text-purple-400">←</span> {c.name}
                          </span>
                        ))}
                        {directDownstreams.map((d) => (
                          <span key={d.id} className="px-2 py-0.5 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-800/60 text-[10px] flex items-center gap-1">
                            <span className="text-cyan-400">→</span> {d.name}
                          </span>
                        ))}
                      </>
                    )}
                  </div>
                </div>

                {/* Contextual Pre-Run Impact Bar */}
                {loadingImpact ? (
                  <div className="pt-2 border-t border-slate-800/80 text-[11px] text-cyan-300 flex items-center gap-2">
                    <RefreshCw size={12} className="animate-spin text-cyan-400" />
                    <span>Preparing What-If analysis...</span>
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
                  <label className="text-xs font-bold uppercase tracking-wider text-slate-200">
                    What would you like to test?
                  </label>
                  <span className="text-[10px] font-mono text-purple-400 font-semibold">8 Supported Scenarios</span>
                </div>

                {SUPPORTED_ACTIONS.length === 0 ? (
                  <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800 text-xs text-slate-400 text-center">
                    No What-If scenarios are available for this component.
                  </div>
                ) : (
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
                )}
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

              {/* 4. EXECUTE BUTTON & SAFETY NOTICE - NEVER AUTO-TRIGGERED */}
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
                      <span>{simulationStage || 'Simulating scenario...'}</span>
                    </>
                  ) : (
                    <>
                      <Sliders size={15} className="text-purple-200" />
                      <span>Run Simulation</span>
                    </>
                  )}
                </button>

                <div className="text-[11px] text-slate-400 flex items-center justify-center gap-1.5 pt-0.5">
                  <Info size={12} className="text-purple-400 shrink-0" />
                  <span>This is a simulation. No live infrastructure will be changed.</span>
                </div>
              </div>

              {/* 5. BASELINE & SIMULATED IMPACT RESULTS (only visible after user runs simulation) */}
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
                        <span>Candidate Solutions ({displayedCandidates.length})</span>
                      </span>
                      <div className="flex items-center gap-2">
                        {isMLRanked ? (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800 font-semibold">
                            ML Ranked • Prototype Model
                          </span>
                        ) : (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 font-semibold">
                            Simulation-based Fallback (Unranked)
                          </span>
                        )}
                        <span className="text-[10px] text-slate-400 font-mono">Independently Simulated</span>
                      </div>
                    </div>

                    {/* Prototype Model Disclaimer / Fallback Notice */}
                    {isMLRanked ? (
                      <div className="text-[11px] text-slate-300 bg-slate-950/70 p-3 rounded-xl border border-purple-900/40 flex items-start gap-2.5">
                        <Info size={14} className="text-purple-400 shrink-0 mt-0.5" />
                        <div className="space-y-0.5">
                          <div className="font-semibold text-purple-200 flex items-center gap-2">
                            <span>Simulation-Trained Prototype Model</span>
                            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-purple-900/60 text-purple-300 border border-purple-700">
                              RandomForest Regressor + Classifier
                            </span>
                          </div>
                          <p className="text-slate-400 text-[10px] leading-relaxed">
                            Candidates are ranked by an ML prototype trained on simulation-derived scenarios to score topology stability and blast radius reduction. Deterministic simulation metrics remain the authoritative truth.
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="text-[11px] text-slate-400 bg-slate-950/70 p-3 rounded-xl border border-slate-800 flex items-start gap-2.5">
                        <Info size={14} className="text-amber-400 shrink-0 mt-0.5" />
                        <div className="space-y-0.5">
                          <span className="font-semibold text-slate-300">Simulation-Based Fallback (Unranked): </span>
                          <p className="text-[10px] text-slate-400 leading-relaxed">
                            {whatIfResponse?.limitations?.[0] || 'ML ranking prototype is unavailable.'} Displaying candidates with deterministic graph simulation results without ML ranking.
                          </p>
                        </div>
                      </div>
                    )}

                    {displayedCandidates.length === 0 ? (
                      <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800 text-xs text-slate-400 text-center">
                        No candidate remediation strategies generated for this specific action and topology.
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {displayedCandidates.map((cand) => {
                          const sim = cand.simulation_result;
                          const vs = sim?.vs_baseline;
                          const mlRankItem = rankingMap.get(cand.candidate_id);
                          const isRecommended = isMLRanked && (mlRankItem?.recommendation || mlRankItem?.rank === 1);

                          return (
                            <div
                              key={cand.candidate_id}
                              className={classNames(
                                "p-4 rounded-xl space-y-3 transition shadow-sm border",
                                isRecommended
                                  ? "border-purple-600/70 bg-gradient-to-b from-purple-950/20 to-slate-950/90 shadow-lg shadow-purple-950/20"
                                  : "bg-slate-950/80 border-slate-800 hover:border-slate-700"
                              )}
                            >
                              {/* ML Ranking Header (if ML ranked) */}
                              {isMLRanked && mlRankItem && (
                                <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-800/80">
                                  <div className="flex items-center gap-2">
                                    {isRecommended ? (
                                      <span className="px-2.5 py-0.5 rounded-md bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-bold text-[10px] tracking-wide flex items-center gap-1 shadow-sm">
                                        <Star size={11} className="fill-amber-300 text-amber-300" />
                                        <span>ML RECOMMENDED</span>
                                      </span>
                                    ) : (
                                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-bold text-[10px] font-mono">
                                        RANK #{mlRankItem.rank}
                                      </span>
                                    )}
                                    <span className="text-[10px] text-purple-300/90 font-mono">
                                      ML Recommendation • {mlRankItem.ranking_method || 'Simulation-Trained ML Prototype'}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-2 text-[10px] font-mono">
                                    {mlRankItem.score != null && (
                                      <span className="px-2 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-800/60 font-semibold">
                                        Suitability: {(mlRankItem.score * 100).toFixed(1)}%
                                      </span>
                                    )}
                                    {mlRankItem.confidence != null && (
                                      <span className="px-2 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800/60 font-semibold">
                                        Confidence: {(mlRankItem.confidence * 100).toFixed(0)}%
                                      </span>
                                    )}
                                  </div>
                                </div>
                              )}

                              {/* Candidate Basic Info */}
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <div className="flex items-center gap-2">
                                    <h4 className="font-bold text-white text-sm">{cand.name}</h4>
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                                      {cand.strategy_type}
                                    </span>
                                  </div>
                                  <p className="text-xs text-slate-300 mt-1 leading-relaxed">{cand.description}</p>
                                </div>
                                <div className="text-right shrink-0">
                                  <span className="font-mono text-xs font-semibold text-slate-200 block">
                                    {isManualResource || isDescribedResource ? formatINR(sim?.cost_delta_monthly ?? 0) : `$${sim?.cost_delta_monthly ?? 0}`}/mo
                                  </span>
                                  <span className="text-[10px] text-slate-500 block">Cost Delta</span>
                                </div>
                              </div>

                              {/* Simulation Comparison Cards */}
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                                <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
                                  <span className="text-[10px] text-slate-400 block">Risk Change</span>
                                  <div className="flex items-center gap-1 mt-0.5">
                                    <span className="font-bold text-slate-200">{sim?.risk_score ?? '-'}</span>
                                    {vs?.risk_score_delta != null && (
                                      <span className={classNames(
                                        "text-[10px] font-mono font-bold",
                                        vs.risk_score_delta < 0 ? "text-emerald-400" : vs.risk_score_delta > 0 ? "text-red-400" : "text-slate-400"
                                      )}>
                                        {vs.risk_score_delta > 0 ? `+${vs.risk_score_delta}` : vs.risk_score_delta}
                                      </span>
                                    )}
                                  </div>
                                </div>

                                <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
                                  <span className="text-[10px] text-slate-400 block">Blast Radius</span>
                                  <div className="flex items-center gap-1 mt-0.5">
                                    <span className="font-bold text-slate-200">{sim?.blast_radius ?? '-'}</span>
                                    {vs?.blast_radius_delta != null && (
                                      <span className={classNames(
                                        "text-[10px] font-mono font-bold",
                                        vs.blast_radius_delta < 0 ? "text-emerald-400" : vs.blast_radius_delta > 0 ? "text-red-400" : "text-slate-400"
                                      )}>
                                        {vs.blast_radius_delta > 0 ? `+${vs.blast_radius_delta}` : vs.blast_radius_delta}
                                      </span>
                                    )}
                                  </div>
                                </div>

                                <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
                                  <span className="text-[10px] text-slate-400 block">SPOF Resolved</span>
                                  <div className="mt-0.5 font-bold">
                                    {sim?.spof_eliminated ? (
                                      <span className="text-emerald-400 text-[11px] flex items-center gap-1">
                                        <ShieldCheck size={12} />
                                        <span>Resolved</span>
                                      </span>
                                    ) : (
                                      <span className="text-red-400 text-[11px]">Still SPOF</span>
                                    )}
                                  </div>
                                </div>

                                <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
                                  <span className="text-[10px] text-slate-400 block">Feasibility</span>
                                  <span className={classNames(
                                    "text-[11px] font-bold block mt-0.5 uppercase",
                                    cand.feasibility === 'high' ? "text-emerald-400" :
                                    cand.feasibility === 'medium' ? "text-amber-400" : "text-slate-400"
                                  )}>
                                    {cand.feasibility}
                                  </span>
                                </div>
                              </div>

                              {/* Review Solution Action */}
                              <div className="flex items-center justify-between pt-1 border-t border-slate-800/80">
                                <div className="flex items-center gap-2">
                                  <span className="text-[11px] text-slate-400">
                                    Downtime: <strong className="text-slate-200">{sim?.estimated_downtime_minutes ?? 0} min</strong>
                                  </span>
                                  {cand.evidence && cand.evidence.length > 0 && (
                                    <span className="text-slate-400 italic text-[10px] truncate max-w-[200px]" title={cand.evidence.join('; ')}>
                                      • {cand.evidence[0]}
                                    </span>
                                  )}
                                </div>

                                <button
                                  type="button"
                                  onClick={() => {
                                    setSelectedCandidateForReview(cand);
                                    setApplyError(null);
                                  }}
                                  className="px-3.5 py-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs rounded-lg shadow-sm transition flex items-center gap-1.5 shrink-0"
                                >
                                  <GitCompare size={13} />
                                  <span>Review Solution</span>
                                </button>
                              </div>

                              {/* Data Integrity: Available vs Missing Data */}
                              <div className="flex flex-wrap items-center justify-between gap-2 pt-1.5 border-t border-slate-800/80 text-[10px]">
                                <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
                                  <CheckCircle2 size={11} />
                                  <span>AVAILABLE DATA: Graph Topology, Simulation Physics, Candidate Mutations</span>
                                </div>
                                {cand.missing_data && cand.missing_data.length > 0 ? (
                                  <div className="flex items-center gap-1.5 text-amber-400 font-medium">
                                    <Info size={11} />
                                    <span>MISSING DATA: {cand.missing_data.join(', ')}</span>
                                  </div>
                                ) : (
                                  <span className="text-slate-500 italic">No missing signals flagged</span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* 7. THREE-AGENT DECISION LAYER TRIGGER & VIEW */}
                  {displayedCandidates.length > 0 && (
                    <div className="space-y-3 pt-3 border-t border-slate-800/80">
                      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-slate-900/90 rounded-xl border border-indigo-900/40 shadow-sm">
                        <div className="flex items-center gap-2.5">
                          <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
                            <Award size={18} />
                          </div>
                          <div>
                            <span className="text-xs font-bold text-white block">Three-Agent Decision Layer</span>
                            <span className="text-[10px] text-slate-400">
                              Financial Analyst, Risk Analyst, and System Architect consensus evaluation
                            </span>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={handleGetExpertAnalysis}
                          disabled={loadingAgents}
                          className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 text-white text-xs font-bold rounded-lg shadow-md transition flex items-center gap-2 shrink-0"
                        >
                          {loadingAgents ? (
                            <>
                              <RefreshCw size={13} className="animate-spin text-white" />
                              <span>Analyzing candidates...</span>
                            </>
                          ) : (
                            <>
                              <Sparkles size={14} />
                              <span>{agentsDecision ? 'Re-Analyze with Agents' : 'Get Expert Analysis'}</span>
                            </>
                          )}
                        </button>
                      </div>

                      {/* Display ThreeAgentsView when decision is available */}
                      {agentsDecision && (
                        <ThreeAgentsView 
                          decision={agentsDecision}
                          candidates={displayedCandidates}
                          targetComponentName={normalizedNode.name}
                        />
                      )}
                    </div>
                  )}

                </div>
              )}
            </>
          )}

        </div>
      </aside>
    </>
  );
};
