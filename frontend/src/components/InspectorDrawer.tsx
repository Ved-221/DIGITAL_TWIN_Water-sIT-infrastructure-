import React, { useState } from 'react';
import classNames from 'classnames';
import { 
  AlertTriangle, Clock, DollarSign, Activity, Share2, 
  Sparkles, Sliders, Info, CheckCircle2, Check, XCircle, 
  ShieldCheck, RefreshCw, Layers, X 
} from 'lucide-react';
import { formatINR, formatCost, getRegionDisplayName } from '../utils/localization';

interface InspectorDrawerProps {
  selectedNode: any;
  metricsMap: Record<string, any>;
  recommendations: Record<string, any>;
  rawDependencies: any[];
  rawComponents: any[];
  simResult: any;
  simulating: boolean;
  onSimulate: (useMl: boolean) => void;
  onOpenWhatIf?: (node: any) => void;
  onClose?: () => void;
  onEditManualResource?: (node: any) => void;
  onDeleteManualResource?: (nodeId: string) => void;
  onSolutionApplied?: () => void;
  apiBase?: string;
}

export const InspectorDrawer: React.FC<InspectorDrawerProps> = ({
  selectedNode,
  metricsMap,
  recommendations,
  rawDependencies,
  rawComponents,
  simResult,
  simulating,
  onSimulate,
  onOpenWhatIf,
  onClose,
  onEditManualResource,
  onDeleteManualResource,
  onSolutionApplied,
  apiBase
}) => {
  const effectiveApiBase = apiBase || 'http://localhost:8000/api';
  // Feasible Solution Decision & Evaluation State
  const [solutionDecision, setSolutionDecision] = useState<'yes' | 'no' | null>(null);
  const [generatingSolutions, setGeneratingSolutions] = useState(false);
  const [feasibleSolutionsResponse, setFeasibleSolutionsResponse] = useState<any>(null);
  const [selectedSolutionId, setSelectedSolutionId] = useState<string | null>(null);
  const [isApplyingSolution, setIsApplyingSolution] = useState(false);
  const [showApplyConfirm, setShowApplyConfirm] = useState(false);
  const [appliedSolutionResult, setAppliedSolutionResult] = useState<any>(null);
  const [solutionError, setSolutionError] = useState<string | null>(null);

  const handleSimulateAction = (useMl: boolean) => {
    setSolutionDecision(null);
    setFeasibleSolutionsResponse(null);
    setSelectedSolutionId(null);
    setShowApplyConfirm(false);
    setAppliedSolutionResult(null);
    setSolutionError(null);
    onSimulate(useMl);
  };

  if (!selectedNode) return null;

  const handleFindSolutions = async () => {
    setSolutionDecision('yes');
    setGeneratingSolutions(true);
    setSolutionError(null);
    try {
      const res = await fetch(`${effectiveApiBase}/feasible-solutions/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_component_id: selectedNode.id,
          current_simulation: simResult
        })
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || `Failed to generate feasible solutions: ${res.statusText}`);
      }
      const data = await res.json();
      setFeasibleSolutionsResponse(data);
      const list = data.feasible_solutions || data.solutions || [];
      if (list.length > 0) {
        setSelectedSolutionId(list[0].id);
      }
    } catch (err: any) {
      setSolutionError(err.message || 'Error generating feasible solutions.');
    } finally {
      setGeneratingSolutions(false);
    }
  };

  const handleApplySolution = async () => {
    if (!selectedSolutionId || !feasibleSolutionsResponse) return;
    const solutions = feasibleSolutionsResponse.feasible_solutions || feasibleSolutionsResponse.solutions || [];
    const chosen = solutions.find((s: any) => s.id === selectedSolutionId);
    if (!chosen) return;

    setIsApplyingSolution(true);
    setSolutionError(null);
    try {
      const res = await fetch(`${effectiveApiBase}/feasible-solutions/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_component_id: selectedNode.id,
          solution_id: chosen.id,
          solution_data: chosen
        })
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || `Failed to apply solution: ${res.statusText}`);
      }
      const data = await res.json();
      setAppliedSolutionResult(data);
      setShowApplyConfirm(false);
      if (onSolutionApplied) {
        onSolutionApplied();
      }
    } catch (err: any) {
      setSolutionError(err.message || 'Error applying feasible solution.');
    } finally {
      setIsApplyingSolution(false);
    }
  };

  const getComponentName = (id: string) => {
    const comp = rawComponents.find((c: any) => c.id === id);
    return comp ? comp.name : id;
  };

  const outboundDeps = (rawDependencies || []).filter(
    (d: any) => (d.source_component_id || d.source_id) === selectedNode.id
  );

  const inboundDeps = (rawDependencies || []).filter(
    (d: any) => (d.target_component_id || d.target_id) === selectedNode.id
  );

  const metric = (metricsMap || {})[selectedNode.id];
  const rec = (recommendations || {})[selectedNode.id];
  const isAWSResource = selectedNode.discovery_source === 'aws_api' || selectedNode.arn != null;
  const isManualResource = selectedNode.discovery_source === 'manual';
  const assumptions = selectedNode.metadata_col?.assumptions;

  return (
    <div className="w-[450px] bg-slate-800/95 backdrop-blur border-l border-slate-700 p-6 flex flex-col gap-5 transition-transform shadow-2xl shrink-0 overflow-y-auto">
      
      {/* Top Header with Close Button */}
      <div className="flex items-center justify-between pb-1 -mt-1 border-b border-slate-700/60">
        <div className="flex items-center gap-2">
          <Layers size={16} className="text-cyan-400" />
          <span className="text-xs font-bold tracking-wider uppercase text-slate-300">Node Details</span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700/60 transition"
            title="Close Details"
            aria-label="Close Details"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Sandbox Notice */}
      <div className="p-2.5 bg-slate-900/80 border border-slate-700/80 rounded-lg text-[11px] text-slate-400 flex items-start gap-2 shadow-inner">
        <Info size={14} className="text-cyan-400 shrink-0 mt-0.5" />
        <span>
          <strong className="text-slate-200">Digital Twin Sandbox:</strong> Telemetry and simulated actions run virtually in this twin model. Real production AWS infrastructure is never modified.
        </span>
      </div>

      {/* 1. ACTUAL STATE */}
      <div className="bg-slate-900/40 p-4 rounded-xl border border-slate-700/60 flex flex-col gap-4 shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-700/60 pb-2">
          <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            1. Actual State
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            {isAWSResource ? '🟢 Live AWS Resource' : isManualResource ? '🛠️ Manual Resource' : '🟡 Baseline Demo'}
          </span>
        </div>

        <div>
          <h2 className="text-xl font-bold text-white mb-0.5">{selectedNode.name}</h2>
          <div className="text-xs text-slate-400 capitalize">{selectedNode.type?.replace('_', ' ')} • {selectedNode.environment}</div>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            <span className="px-2 py-0.5 bg-slate-700 rounded text-xs font-medium text-slate-300">Crit: {selectedNode.criticality || 'Normal'}</span>
            <span className="px-2 py-0.5 bg-slate-700 rounded text-xs font-medium text-slate-300">
              {isManualResource 
                ? formatCost(selectedNode.cost_per_month, 'configured')
                : formatCost(selectedNode.cost_per_month, 'actual', 'USD', { showConverted: true })}
            </span>
            {(selectedNode.location || selectedNode.aws_region) && (
              <span className="px-2 py-0.5 bg-slate-700 rounded text-xs font-medium text-slate-300">
                Region: {getRegionDisplayName(selectedNode.location || selectedNode.aws_region)}
              </span>
            )}
            {selectedNode.account_id && (
              <span className="px-2 py-0.5 bg-slate-700 rounded text-xs font-medium text-slate-300 font-mono">Acct: {selectedNode.account_id}</span>
            )}
          </div>
        </div>

        {/* What If Scenario Quick Launch */}
        {onOpenWhatIf && (
          <button
            type="button"
            onClick={() => onOpenWhatIf(selectedNode)}
            className="w-full py-2 bg-purple-950/60 hover:bg-purple-900/80 border border-purple-800/80 rounded-lg text-xs font-bold text-purple-200 transition flex items-center justify-center gap-2 shadow-sm"
          >
            <Sliders size={13} className="text-purple-300" />
            <span>Ask "What If?" for this component</span>
          </button>
        )}

        {/* Manual Resource Action Bar */}
        {isManualResource && (
          <div className="flex items-center gap-2 pt-2 border-t border-slate-700/60">
            {onEditManualResource && (
              <button
                onClick={() => onEditManualResource(selectedNode)}
                className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded text-xs font-medium flex items-center gap-1 transition"
              >
                <Sliders size={12} className="text-cyan-400" />
                <span>Edit Properties</span>
              </button>
            )}
            {onDeleteManualResource && (
              <button
                onClick={() => onDeleteManualResource(selectedNode.id)}
                className="px-2.5 py-1 bg-rose-950/50 hover:bg-rose-900/60 text-rose-300 border border-rose-800/60 rounded text-xs font-medium transition ml-auto"
              >
                Delete Resource
              </button>
            )}
          </div>
        )}

        {/* Telemetry / Assumptions Section */}
        {isManualResource ? (
          <div className="border-t border-slate-700/60 pt-3">
            <div className="text-xs font-semibold text-slate-300 mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1.5"><Activity size={13} className="text-cyan-400" /> Simulation Assumptions</span>
              <span className="text-[10px] text-cyan-400 font-mono">User Input</span>
            </div>

            {(assumptions || selectedNode.cpu != null || selectedNode.memory != null) ? (
              <>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-slate-800/70 p-2 rounded border border-slate-700">
                    <span className="text-slate-400 block text-[10px]">Assumed CPU</span>
                    <span className="text-white font-bold text-sm">
                      {(assumptions?.cpu ?? selectedNode.cpu) != null ? `${assumptions?.cpu ?? selectedNode.cpu}%` : 'Not set'}
                    </span>
                  </div>
                  <div className="bg-slate-800/70 p-2 rounded border border-slate-700">
                    <span className="text-slate-400 block text-[10px]">Assumed Memory</span>
                    <span className="text-white font-bold text-sm">
                      {(assumptions?.memory ?? selectedNode.memory) != null ? `${assumptions?.memory ?? selectedNode.memory}%` : 'Not set'}
                    </span>
                  </div>
                  <div className="bg-slate-800/70 p-2 rounded border border-slate-700">
                    <span className="text-slate-400 block text-[10px]">Assumed Latency</span>
                    <span className="text-white font-bold text-sm">
                      {assumptions?.latency != null ? `${assumptions.latency} ms` : 'Not set'}
                    </span>
                  </div>
                  <div className="bg-slate-800/70 p-2 rounded border border-slate-700">
                    <span className="text-slate-400 block text-[10px]">Assumed Error Rate</span>
                    <span className="text-white font-bold text-sm">
                      {assumptions?.error_rate != null ? `${assumptions.error_rate}%` : '0.0%'}
                    </span>
                  </div>
                </div>
                <div className="text-[10px] text-slate-400 mt-2 flex items-start gap-1 bg-slate-950/40 p-2 rounded border border-slate-800">
                  <Info size={12} className="text-cyan-400 shrink-0 mt-0.5" />
                  <span>Configured assumptions for simulation. Real CloudWatch telemetry is unavailable in manual mode.</span>
                </div>
              </>
            ) : (
              <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/60 text-xs text-slate-400">
                <span className="block text-slate-300 font-medium mb-0.5">Telemetry Unavailable</span>
                No telemetry source configured. You can configure simulation assumptions by clicking Edit Properties above.
              </div>
            )}
          </div>
        ) : (
          <div className="border-t border-slate-700/60 pt-3">
            <div className="text-xs font-semibold text-slate-300 mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1.5"><Activity size={13} className="text-emerald-400" /> Operational Telemetry</span>
              <span className="text-[10px] text-slate-400 font-mono">
                {metric ? (metric.raw_metrics?.source === 'cloudwatch' ? '🟢 CloudWatch' : '🟡 Baseline') : 'Inactive'}
              </span>
            </div>

            {metric ? (
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-800/70 p-2 rounded border border-slate-700">
                  <span className="text-slate-400 block text-[10px]">CPU Utilization</span>
                  <span className={classNames(
                    "text-sm font-bold",
                    (metric.cpu ?? 0) > 80 ? "text-red-400" : (metric.cpu ?? 0) > 60 ? "text-amber-400" : "text-emerald-400"
                  )}>
                    {metric.cpu != null ? `${metric.cpu.toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="bg-slate-800/70 p-2 rounded border border-slate-700">
                  <span className="text-slate-400 block text-[10px]">Memory Usage</span>
                  <span className={classNames(
                    "text-sm font-bold",
                    (metric.memory ?? 0) > 80 ? "text-red-400" : "text-slate-200"
                  )}>
                    {metric.memory != null ? `${metric.memory.toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="bg-slate-800/70 p-2 rounded border border-slate-700">
                  <span className="text-slate-400 block text-[10px]">Network Latency</span>
                  <span className="text-slate-200 text-sm font-bold">
                    {metric.latency != null ? `${metric.latency.toFixed(1)} ms` : 'N/A'}
                  </span>
                </div>
                <div className="bg-slate-800/70 p-2 rounded border border-slate-700">
                  <span className="text-slate-400 block text-[10px]">Error Rate</span>
                  <span className={classNames(
                    "text-sm font-bold",
                    (metric.error_rate ?? 0) > 1.0 ? "text-red-400" : "text-emerald-400"
                  )}>
                    {metric.error_rate != null ? `${metric.error_rate.toFixed(2)}%` : '0.00%'}
                  </span>
                </div>
              </div>
            ) : (
              <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-700/60 text-xs text-slate-400">
                No telemetry data available for this resource.
              </div>
            )}
          </div>
        )}

        {/* Topologically Verified Dependencies */}
        <div className="border-t border-slate-700/60 pt-3">
          <div className="text-xs font-semibold text-slate-300 mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5"><Share2 size={13} className="text-blue-400" /> Infrastructure Dependencies</span>
            <span className="text-[10px] text-slate-400 font-mono">{outboundDeps.length + inboundDeps.length} Verified</span>
          </div>

          {outboundDeps.length === 0 && inboundDeps.length === 0 ? (
            <p className="text-xs text-slate-500 italic">No inbound or outbound infrastructure dependencies discovered.</p>
          ) : (
            <div className="space-y-3">
              {outboundDeps.length > 0 && (
                <div>
                  <div className="text-[11px] font-medium text-slate-400 mb-1">Outbound Targets ({outboundDeps.length})</div>
                  <div className="space-y-1.5">
                    {outboundDeps.map((dep: any, idx: number) => (
                      <div key={idx} className="p-2 bg-slate-800/60 rounded border border-slate-700 text-xs flex items-center justify-between">
                        <span className="font-medium text-slate-200">→ {getComponentName(dep.target_component_id || dep.target_id)}</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 font-mono">
                          {dep.relationship_type?.replace(/_/g, ' ')}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {inboundDeps.length > 0 && (
                <div>
                  <div className="text-[11px] font-medium text-slate-400 mb-1">Inbound Sources ({inboundDeps.length})</div>
                  <div className="space-y-1.5">
                    {inboundDeps.map((dep: any, idx: number) => (
                      <div key={idx} className="p-2 bg-slate-800/60 rounded border border-slate-700 text-xs flex items-center justify-between">
                        <span className="font-medium text-slate-200">← {getComponentName(dep.source_component_id || dep.source_id)}</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 font-mono">
                          {dep.relationship_type?.replace(/_/g, ' ')}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 2. ML OPERATIONAL RECOMMENDATION */}
      {!isManualResource && rec && (
        <div className="bg-slate-900/40 p-4 rounded-xl border border-purple-900/40 flex flex-col gap-3 shadow-sm">
          <div className="flex items-center justify-between border-b border-purple-900/50 pb-2">
            <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800/80 flex items-center gap-1.5">
              <Sparkles size={11} className="text-purple-300" />
              2. ML Recommendation
            </span>
            <span className="text-[10px] text-purple-300 font-mono">
              {(rec.confidence * 100).toFixed(0)}% Confidence
            </span>
          </div>

          <div className={classNames(
            "p-3 rounded-lg border flex flex-col gap-2 shadow-sm",
            rec.recommended_action === 'NO_ACTION' ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-200" :
            rec.recommended_action === 'SCALE_COMPUTE' ? "bg-amber-950/40 border-amber-700/60 text-amber-200" :
            rec.recommended_action === 'EXPAND_STORAGE' ? "bg-purple-950/40 border-purple-700/60 text-purple-200" :
            rec.recommended_action === 'INVESTIGATE_LATENCY_ERROR' ? "bg-red-950/40 border-red-700/60 text-red-200" :
            rec.recommended_action === 'INVESTIGATE_DATABASE_BOTTLENECK' ? "bg-rose-950/40 border-rose-700/60 text-rose-200" :
            rec.recommended_action === 'REDUNDANCY_RISK' ? "bg-red-950/50 border-red-600 text-red-100" :
            "bg-blue-950/40 border-blue-700/60 text-blue-200"
          )}>
            <div className="flex items-center justify-between">
              <span className="font-bold text-sm tracking-wide">
                {rec.recommended_action.replace(/_/g, ' ')}
              </span>
              <span className="text-[9px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-900/60 text-slate-300">
                {rec.model_type}
              </span>
            </div>

            {rec.reasoning_features && rec.reasoning_features.length > 0 && (
              <div className="mt-1 space-y-1">
                <span className="text-[10px] font-semibold text-slate-400 block uppercase tracking-wider">Driving Telemetry Signals:</span>
                {rec.reasoning_features.map((rf: any, i: number) => (
                  <div key={i} className="flex items-center justify-between text-xs bg-slate-900/50 px-2 py-1 rounded">
                    <span className="text-slate-300 font-mono text-[11px]">{rf.feature}</span>
                    <span className="font-semibold text-white">{rf.value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="text-[10px] text-slate-400 bg-slate-950/40 p-2 rounded border border-slate-800 flex items-center gap-1.5">
            <Info size={12} className="text-purple-400 shrink-0" />
            <span>Digital Twin prediction only. Click below to evaluate deterministic blast radius before taking action.</span>
          </div>
        </div>
      )}

      {/* 3. SIMULATED IMPACT */}
      <div className="bg-slate-900/40 p-4 rounded-xl border border-amber-900/40 flex flex-col gap-3 shadow-sm">
        <div className="flex items-center justify-between border-b border-amber-900/50 pb-2">
          <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800/80 flex items-center gap-1.5">
            <Sliders size={11} className="text-amber-300" />
            3. Simulated Impact
          </span>
          <span className="text-[10px] text-amber-300 font-mono">Deterministic Engine</span>
        </div>

        <div className="flex flex-col gap-2">
          {onOpenWhatIf && (
            <button
              type="button"
              onClick={() => onOpenWhatIf(selectedNode)}
              className="w-full py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 rounded-md font-bold transition flex items-center justify-center gap-2 shadow-lg shadow-purple-950/20 text-xs text-white"
            >
              <Sliders size={14} className="text-purple-200" />
              <span>What If? (Scenario Engine)</span>
            </button>
          )}

          {isManualResource ? (
            <button 
              onClick={() => handleSimulateAction(false)}
              disabled={simulating}
              className="w-full py-2.5 bg-gradient-to-r from-blue-600 to-amber-600 hover:from-blue-500 hover:to-amber-500 rounded-md font-semibold transition flex items-center justify-center gap-2 shadow-lg shadow-amber-950/20 text-xs text-white disabled:opacity-50"
            >
              {simulating ? <Activity className="animate-spin" size={14} /> : <Sliders size={14} className="text-amber-200" />}
              Simulate Impact (Deterministic)
            </button>
          ) : (
            <>
              <button 
                onClick={() => handleSimulateAction(true)}
                disabled={simulating}
                className="w-full py-2.5 bg-gradient-to-r from-purple-600 to-amber-600 hover:from-purple-500 hover:to-amber-500 rounded-md font-semibold transition flex items-center justify-center gap-2 shadow-lg shadow-amber-950/20 text-xs text-white disabled:opacity-50"
              >
                {simulating ? <Activity className="animate-spin" size={14} /> : <Sparkles size={14} className="text-amber-200" />}
                Simulate ML Recommended Action
              </button>
              <button 
                onClick={() => handleSimulateAction(false)}
                disabled={simulating}
                className="w-full py-2 bg-slate-700/80 hover:bg-slate-700 rounded-md font-medium transition flex items-center justify-center gap-1.5 text-xs text-slate-300 border border-slate-600/60"
              >
                Simulate Migration (Manual)
              </button>
            </>
          )}
        </div>

        {simResult && (
          <div className="border-t border-slate-700/60 pt-3 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300">Simulated Action:</span>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-amber-300 border border-amber-800/50">
                {simResult.action ? simResult.action.replace(/_/g, ' ') : 'Simulated'}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <div className="text-slate-400 text-[10px] mb-0.5 flex items-center gap-1"><AlertTriangle size={11}/> Risk Score</div>
                <div className={classNames(
                  "text-xl font-bold",
                  simResult.risk_level === 'CRITICAL' ? 'text-red-400' :
                  simResult.risk_level === 'HIGH' ? 'text-orange-400' : 'text-yellow-400'
                )}>
                  {simResult.risk_score} <span className="text-xs font-normal text-slate-500">/ 100</span>
                </div>
              </div>
              
              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <div className="text-slate-400 text-[10px] mb-0.5 flex items-center gap-1"><Clock size={11}/> Est. Downtime</div>
                <div className="text-xl font-bold text-white">
                  {simResult.estimated_downtime_minutes} <span className="text-xs font-normal text-slate-500">min</span>
                </div>
              </div>

              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <div className="text-slate-400 text-[10px] mb-0.5 flex items-center gap-1"><Share2 size={11}/> Blast Radius</div>
                <div className="text-xl font-bold text-red-400">
                  {simResult.blast_radius || simResult.affected_count} <span className="text-xs font-normal text-slate-500">nodes</span>
                </div>
              </div>

              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <div className="text-slate-400 text-[10px] mb-0.5 flex items-center gap-1"><DollarSign size={11}/> Cost Impact</div>
                <div className={classNames(
                  "text-xl font-bold",
                  (simResult.cost_impact ?? simResult.cost_delta_monthly) < 0 ? 'text-emerald-400' : 'text-slate-200'
                )}>
                  {(simResult.cost_impact ?? simResult.cost_delta_monthly) < 0 ? '-' : '+'}
                  {isManualResource 
                    ? formatINR(Math.abs(simResult.cost_impact ?? simResult.cost_delta_monthly))
                    : `$${Math.abs(simResult.cost_impact ?? simResult.cost_delta_monthly).toFixed(0)}`}
                  <span className="text-xs font-normal text-slate-500">/mo</span>
                </div>
              </div>
            </div>

            {/* Transparent Factor Breakdown */}
            {simResult.risk_factors && simResult.risk_factors.length > 0 && (
              <div className="bg-slate-950/40 p-2.5 rounded border border-slate-800 space-y-1.5">
                <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">Transparent Risk Factors:</span>
                {simResult.risk_factors.map((rf: any, idx: number) => (
                  <div key={idx} className="flex items-start justify-between text-[11px] gap-2">
                    <span className="text-slate-300">• {rf.explanation}</span>
                    <span className="font-mono font-semibold text-amber-300 shrink-0">+{rf.score_impact}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 4. AI EXPLANATION */}
      {simResult && simResult.ai_explanation && (
        <div className="bg-slate-900/40 p-4 rounded-xl border border-blue-900/40 flex flex-col gap-3 shadow-sm">
          <div className="flex items-center justify-between border-b border-blue-900/50 pb-2">
            <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800/80 flex items-center gap-1.5">
              <Sparkles size={11} className="text-blue-300" />
              4. AI Explanation
            </span>
            <span className="text-[10px] text-blue-300 font-mono">Gemini Reasoning</span>
          </div>

          {simResult.structured_explanation ? (
            <div className="space-y-2.5 text-xs">
              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <span className="font-semibold text-blue-300 block mb-0.5">1. What is happening:</span>
                <span className="text-slate-300 leading-relaxed">{simResult.structured_explanation.what_is_happening}</span>
              </div>
              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <span className="font-semibold text-amber-300 block mb-0.5">2. Why ML recommended action:</span>
                <span className="text-slate-300 leading-relaxed">{simResult.structured_explanation.why_ml_recommended}</span>
              </div>
              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <span className="font-semibold text-cyan-300 block mb-0.5">3. Affected infrastructure components:</span>
                <span className="text-slate-300 leading-relaxed">{simResult.structured_explanation.affected_components_summary}</span>
              </div>
              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <span className="font-semibold text-emerald-300 block mb-0.5">4. Simulation forecast:</span>
                <span className="text-slate-300 leading-relaxed">{simResult.structured_explanation.simulation_prediction}</span>
              </div>
              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <span className="font-semibold text-red-300 block mb-0.5">5. Important risks:</span>
                <span className="text-slate-300 leading-relaxed">{simResult.structured_explanation.key_risks}</span>
              </div>
              <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                <span className="font-semibold text-purple-300 block mb-0.5">6. Engineer pre-change checklist:</span>
                <ul className="space-y-1 text-slate-300 mt-1 list-disc list-inside">
                  {simResult.structured_explanation.engineer_considerations.map((c: string, i: number) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <p className="whitespace-pre-line leading-relaxed text-xs text-slate-300 bg-slate-800/70 p-3 rounded border border-slate-700">{simResult.ai_explanation}</p>
          )}

          {simResult.ai_recommendation && (
            <div className="p-2.5 bg-blue-950/30 rounded border border-blue-800/50">
              <span className="font-semibold text-blue-200 block mb-1 text-xs">Architect Executive Summary:</span> 
              <span className="leading-relaxed text-blue-100/90 text-xs whitespace-pre-line">{simResult.ai_recommendation}</span>
            </div>
          )}
        </div>
      )}

      {/* 5. FEASIBLE SOLUTION EVALUATION */}
      {simResult && (
        <div className="bg-slate-900/40 p-4 rounded-xl border border-cyan-900/50 flex flex-col gap-4 shadow-sm">
          <div className="flex items-center justify-between border-b border-cyan-900/60 pb-2">
            <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/80 flex items-center gap-1.5">
              <Sliders size={11} className="text-cyan-300" />
              5. Feasible Solutions
            </span>
            <span className="text-[10px] text-cyan-300 font-mono">
              {appliedSolutionResult ? 'Applied to Twin' : solutionDecision === 'yes' ? 'Candidate Evaluation' : 'Decision Gate'}
            </span>
          </div>

          {/* STATE A: SOLUTION HAS BEEN APPLIED TO THE DIGITAL TWIN */}
          {appliedSolutionResult ? (
            <div className="flex flex-col gap-4 animate-in fade-in">
              {/* AWS Safety Banner */}
              {appliedSolutionResult.is_live_aws && (
                <div className="p-3 bg-purple-950/80 border border-purple-500 rounded-xl flex items-start gap-2.5 shadow-lg shadow-purple-950/40 text-xs text-purple-200">
                  <AlertTriangle size={16} className="text-purple-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-white block mb-0.5">Proposed change — not deployed to AWS</span>
                    <span className="leading-relaxed">
                      This feasible solution was applied virtually to the Digital Twin model for impact evaluation. Real AWS infrastructure is never modified and live production APIs were not invoked.
                    </span>
                  </div>
                </div>
              )}

              {/* Applied Solution Card Summary */}
              <div className="p-3 bg-slate-900/70 rounded-xl border border-emerald-800/60 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white">
                    {appliedSolutionResult.applied_solution?.title || 'Applied Feasible Solution'}
                  </span>
                  <span className="text-[9px] font-semibold px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 flex items-center gap-1">
                    <CheckCircle2 size={10} /> Applied to Twin
                  </span>
                </div>
                <p className="text-xs text-slate-300">
                  {appliedSolutionResult.applied_solution?.description}
                </p>
              </div>

              {/* Before vs After Comparison Table */}
              {appliedSolutionResult.before_after_comparison && (
                <div className="bg-slate-950/50 rounded-xl border border-slate-700/80 overflow-hidden shadow-sm">
                  <div className="px-3 py-2 bg-slate-900/80 border-b border-slate-700 text-xs font-semibold text-slate-200 flex items-center justify-between">
                    <span>Before vs After Comparison</span>
                    <span className="text-[10px] text-cyan-400 font-mono">Deterministic Engine</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-[10px] uppercase text-slate-400 bg-slate-900/40">
                          <th className="py-2 px-3">Dimension</th>
                          <th className="py-2 px-3">Before</th>
                          <th className="py-2 px-3">After</th>
                          <th className="py-2 px-3">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 text-slate-300">
                        <tr>
                          <td className="py-2 px-3 font-medium text-slate-400">Risk Score</td>
                          <td className="py-2 px-3 text-amber-400">{appliedSolutionResult.before_after_comparison.risk?.before}</td>
                          <td className="py-2 px-3 text-emerald-400 font-bold">{appliedSolutionResult.before_after_comparison.risk?.after}</td>
                          <td className="py-2 px-3 text-emerald-400 font-mono text-[11px]">{appliedSolutionResult.before_after_comparison.risk?.status}</td>
                        </tr>
                        <tr>
                          <td className="py-2 px-3 font-medium text-slate-400">Blast Radius</td>
                          <td className="py-2 px-3 text-red-400">{appliedSolutionResult.before_after_comparison.blast_radius?.before}</td>
                          <td className="py-2 px-3 text-white font-bold">{appliedSolutionResult.before_after_comparison.blast_radius?.after}</td>
                          <td className="py-2 px-3 text-emerald-400 font-mono text-[11px]">{appliedSolutionResult.before_after_comparison.blast_radius?.status}</td>
                        </tr>
                        <tr>
                          <td className="py-2 px-3 font-medium text-slate-400">Downtime</td>
                          <td className="py-2 px-3">{appliedSolutionResult.before_after_comparison.downtime?.before}</td>
                          <td className="py-2 px-3 text-white font-bold">{appliedSolutionResult.before_after_comparison.downtime?.after}</td>
                          <td className="py-2 px-3 text-slate-400 font-mono text-[11px]">{appliedSolutionResult.before_after_comparison.downtime?.status}</td>
                        </tr>
                        <tr>
                          <td className="py-2 px-3 font-medium text-slate-400">Monthly Cost</td>
                          <td className="py-2 px-3">{appliedSolutionResult.before_after_comparison.cost?.before}</td>
                          <td className="py-2 px-3 text-white font-bold">{appliedSolutionResult.before_after_comparison.cost?.after}</td>
                          <td className="py-2 px-3 text-cyan-400 font-mono text-[11px]">{appliedSolutionResult.before_after_comparison.cost?.status}</td>
                        </tr>
                        <tr>
                          <td className="py-2 px-3 font-medium text-slate-400">Resilience</td>
                          <td className="py-2 px-3 text-slate-400">{appliedSolutionResult.before_after_comparison.resilience?.before}</td>
                          <td className="py-2 px-3 text-emerald-400 font-medium" colSpan={2}>{appliedSolutionResult.before_after_comparison.resilience?.after}</td>
                        </tr>
                        <tr>
                          <td className="py-2 px-3 font-medium text-slate-400">Performance</td>
                          <td className="py-2 px-3 text-slate-400">{appliedSolutionResult.before_after_comparison.performance?.before}</td>
                          <td className="py-2 px-3 text-cyan-300 font-medium" colSpan={2}>{appliedSolutionResult.before_after_comparison.performance?.after}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Gemini Architectural Solution Explanation */}
              {(appliedSolutionResult.ai_structured_explanation || appliedSolutionResult.ai_explanation) && (
                <div className="bg-slate-900/50 p-4 rounded-xl border border-emerald-900/40 flex flex-col gap-3 shadow-sm">
                  <div className="flex items-center justify-between border-b border-emerald-900/50 pb-2">
                    <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/80 flex items-center gap-1.5">
                      <Sparkles size={11} className="text-emerald-300" />
                      Architectural Solution Assessment
                    </span>
                    <span className="text-[10px] text-emerald-300 font-mono">Gemini Explanation Layer</span>
                  </div>

                  {appliedSolutionResult.ai_structured_explanation ? (
                    <div className="space-y-2.5 text-xs">
                      <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                        <span className="font-semibold text-emerald-300 block mb-0.5">1. What Changed:</span>
                        <span className="text-slate-300 leading-relaxed">{appliedSolutionResult.ai_structured_explanation.what_changed}</span>
                      </div>
                      <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                        <span className="font-semibold text-cyan-300 block mb-0.5">2. Why It Helps:</span>
                        <span className="text-slate-300 leading-relaxed">{appliedSolutionResult.ai_structured_explanation.why_it_helps}</span>
                      </div>
                      <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                        <span className="font-semibold text-blue-300 block mb-0.5">3. Affected Dependencies:</span>
                        <span className="text-slate-300 leading-relaxed">{appliedSolutionResult.ai_structured_explanation.affected_dependencies}</span>
                      </div>
                      <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                        <span className="font-semibold text-amber-300 block mb-0.5">4. Simulation Indications:</span>
                        <span className="text-slate-300 leading-relaxed">{appliedSolutionResult.ai_structured_explanation.simulation_indications}</span>
                      </div>
                      <div className="bg-slate-800/70 p-2.5 rounded border border-slate-700">
                        <span className="font-semibold text-purple-300 block mb-0.5">5. Trade-offs & Limitations:</span>
                        <ul className="space-y-1 text-slate-300 mt-1 list-disc list-inside">
                          {(appliedSolutionResult.ai_structured_explanation.trade_offs_and_limitations || []).map((t: string, i: number) => (
                            <li key={i}>{t}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  ) : (
                    <p className="whitespace-pre-line leading-relaxed text-xs text-slate-300 bg-slate-800/70 p-3 rounded border border-slate-700">
                      {appliedSolutionResult.ai_explanation}
                    </p>
                  )}
                </div>
              )}

              {/* Re-evaluate or test another action */}
              <button
                onClick={() => {
                  setAppliedSolutionResult(null);
                  setSolutionDecision(null);
                  setFeasibleSolutionsResponse(null);
                }}
                className="w-full py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-md text-xs font-medium text-slate-300 flex items-center justify-center gap-1.5 transition"
              >
                <RefreshCw size={13} className="text-cyan-400" />
                <span>Test Another Feasible Solution</span>
              </button>
            </div>
          ) : (
            <>
              {/* STATE B: DECISION GATE (PROMPT USER YES OR NO) */}
              {solutionDecision === null && (
                <div className="flex flex-col gap-3">
                  <div className="text-xs text-slate-300 leading-relaxed bg-slate-950/40 p-3 rounded-lg border border-slate-800">
                    <span className="font-semibold text-white block mb-1">Problem Identified</span>
                    Simulation and Gemini reasoning identified operational risks for <strong className="text-white">{selectedNode.name}</strong>.
                    Would you like to find feasible solutions for this problem?
                  </div>

                  <div className="flex flex-col gap-2">
                    <button
                      onClick={handleFindSolutions}
                      className="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold rounded-md text-xs transition flex items-center justify-center gap-2 shadow-lg shadow-cyan-950/20"
                    >
                      <CheckCircle2 size={14} className="text-cyan-200" />
                      YES — Find Feasible Solutions
                    </button>
                    <button
                      onClick={() => setSolutionDecision('no')}
                      className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium rounded-md text-xs transition flex items-center justify-center gap-1.5 border border-slate-700"
                    >
                      <XCircle size={14} className="text-slate-400" />
                      NO — Continue Without Changes
                    </button>
                  </div>
                </div>
              )}

              {/* STATE C: USER SELECTED NO (CONTINUE WITHOUT CHANGES) */}
              {solutionDecision === 'no' && (
                <div className="p-3 bg-slate-900/60 border border-slate-700/80 rounded-xl flex items-center justify-between shadow-sm">
                  <div className="flex items-center gap-2 text-xs text-slate-300">
                    <Check size={14} className="text-emerald-400 shrink-0" />
                    <span>Problem Identified • Continued Without Changes</span>
                  </div>
                  <button
                    onClick={handleFindSolutions}
                    className="px-2.5 py-1 text-[11px] bg-slate-800 hover:bg-slate-700 text-cyan-400 border border-slate-700 rounded transition shrink-0 ml-2"
                  >
                    Re-evaluate
                  </button>
                </div>
              )}

              {/* STATE D: USER SELECTED YES (GENERATING CANDIDATES) */}
              {solutionDecision === 'yes' && (
                <div className="flex flex-col gap-3">
                  {generatingSolutions ? (
                    <div className="p-4 bg-slate-900/60 border border-cyan-900/50 rounded-xl flex items-center justify-center gap-2.5 text-xs text-cyan-300">
                      <Activity className="animate-spin" size={16} />
                      <span>Analyzing feasible infrastructure changes via sandbox simulation...</span>
                    </div>
                  ) : feasibleSolutionsResponse ? (
                    <>
                      {/* Check if 0 feasible solutions found */}
                      {((feasibleSolutionsResponse.feasible_solutions || feasibleSolutionsResponse.solutions || []).length === 0) ? (
                        <div className="p-4 bg-slate-900/60 border border-amber-900/50 rounded-xl flex flex-col gap-2 text-xs">
                          <div className="flex items-center gap-2 text-amber-300 font-bold">
                            <Info size={16} className="text-amber-400 shrink-0" />
                            <span>No Feasible Solutions Found</span>
                          </div>
                          <p className="text-slate-300 leading-relaxed">
                            No feasible solution found with the available constraints and data.
                          </p>
                          <div className="text-[11px] text-slate-400 mt-1">
                            The candidate solutions evaluated did not meet required operational safety, cost, or dependency constraints for this component.
                          </div>
                          <button
                            onClick={() => setSolutionDecision(null)}
                            className="mt-2 py-1.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 text-xs font-medium self-start"
                          >
                            Return to Decision Gate
                          </button>
                        </div>
                      ) : (
                        /* Render List of Feasible Solutions */
                        <div className="flex flex-col gap-3">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                              <Layers size={13} className="text-cyan-400" />
                              Feasible Solutions ({(feasibleSolutionsResponse.feasible_solutions || feasibleSolutionsResponse.solutions || []).length} options evaluated)
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">In-Memory Sandbox</span>
                          </div>

                          <div className="space-y-2.5">
                            {(feasibleSolutionsResponse.feasible_solutions || feasibleSolutionsResponse.solutions || []).map((sol: any) => {
                              const isSelected = selectedSolutionId === sol.id;
                              const ce = sol.constraints_evaluation || {};
                              return (
                                <div
                                  key={sol.id}
                                  onClick={() => setSelectedSolutionId(sol.id)}
                                  className={classNames(
                                    "p-3 rounded-xl border transition-all cursor-pointer flex flex-col gap-2.5 shadow-sm text-xs",
                                    isSelected
                                      ? "bg-slate-800/90 border-cyan-500 shadow-cyan-950/40 ring-1 ring-cyan-500/60"
                                      : "bg-slate-900/50 border-slate-700/80 hover:border-slate-600 hover:bg-slate-800/50 text-slate-300"
                                  )}
                                >
                                  <div className="flex items-start justify-between gap-2">
                                    <div className="flex items-center gap-2">
                                      <div className={classNames(
                                        "w-4 h-4 rounded-full border flex items-center justify-center shrink-0",
                                        isSelected ? "border-cyan-400 bg-cyan-500 text-white" : "border-slate-600"
                                      )}>
                                        {isSelected && <Check size={10} />}
                                      </div>
                                      <span className="font-bold text-white text-xs">{sol.title}</span>
                                    </div>
                                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 border border-cyan-900 shrink-0">
                                      {sol.action_type?.replace(/_/g, ' ')}
                                    </span>
                                  </div>

                                  <p className="text-slate-300 text-[11px] leading-relaxed">
                                    {sol.description}
                                  </p>

                                  {/* Feasibility Rationale */}
                                  {sol.feasibility_reason && (
                                    <div className="text-[11px] bg-slate-950/50 p-2 rounded border border-slate-800/80 text-cyan-300 flex items-start gap-1.5">
                                      <Info size={12} className="shrink-0 mt-0.5 text-cyan-400" />
                                      <span>{sol.feasibility_reason}</span>
                                    </div>
                                  )}

                                  {/* Constraints Evaluation Breakdown */}
                                  <div className="grid grid-cols-2 gap-1.5 pt-1 text-[11px]">
                                    <div className="bg-slate-900/60 p-1.5 rounded border border-slate-800">
                                      <span className="text-slate-500 block text-[9px] uppercase">Risk Reduction</span>
                                      <span className="text-emerald-400 font-semibold">{ce.risk_reduction || 'Improved'}</span>
                                    </div>
                                    <div className="bg-slate-900/60 p-1.5 rounded border border-slate-800">
                                      <span className="text-slate-500 block text-[9px] uppercase">Cost Impact</span>
                                      <span className="text-slate-200 font-semibold">{ce.cost_impact_display || 'Calculated'}</span>
                                    </div>
                                    <div className="bg-slate-900/60 p-1.5 rounded border border-slate-800">
                                      <span className="text-slate-500 block text-[9px] uppercase">Downtime</span>
                                      <span className="text-white font-semibold">{ce.downtime_display || '0 min'}</span>
                                    </div>
                                    <div className="bg-slate-900/60 p-1.5 rounded border border-slate-800">
                                      <span className="text-slate-500 block text-[9px] uppercase">Blast Radius</span>
                                      <span className="text-white font-semibold">
                                        {ce.blast_radius_before != null && ce.blast_radius_after != null
                                          ? `${ce.blast_radius_before} → ${ce.blast_radius_after} node(s)`
                                          : 'Contained'}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>

                          {/* Action Bar & Apply Confirmation */}
                          {showApplyConfirm ? (
                            <div className="p-3.5 bg-slate-950 border border-cyan-700/80 rounded-xl flex flex-col gap-2.5 shadow-xl animate-in fade-in">
                              <div className="text-xs font-semibold text-white flex items-center gap-1.5">
                                <ShieldCheck size={15} className="text-cyan-400 shrink-0" />
                                <span>Make the Selected Infrastructure Change?</span>
                              </div>
                              <p className="text-xs text-slate-300 leading-relaxed">
                                {isAWSResource
                                  ? "This will update the Digital Twin model with the proposed changes for simulation verification. Real AWS production infrastructure will NOT be modified."
                                  : "This will update your manually constructed Digital Twin topology with the selected infrastructure modifications."}
                              </p>
                              <div className="flex items-center gap-2 pt-1">
                                <button
                                  onClick={handleApplySolution}
                                  disabled={isApplyingSolution}
                                  className="flex-1 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white rounded text-xs font-semibold transition flex items-center justify-center gap-1.5 disabled:opacity-50"
                                >
                                  {isApplyingSolution ? <Activity className="animate-spin" size={13} /> : <Check size={13} />}
                                  <span>Confirm & Make the Change</span>
                                </button>
                                <button
                                  onClick={() => setShowApplyConfirm(false)}
                                  disabled={isApplyingSolution}
                                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-medium transition"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <button
                              onClick={() => setShowApplyConfirm(true)}
                              disabled={!selectedSolutionId || isApplyingSolution}
                              className="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-emerald-600 hover:from-cyan-500 hover:to-emerald-500 text-white font-semibold rounded-md text-xs transition flex items-center justify-center gap-2 shadow-lg shadow-cyan-950/20 disabled:opacity-50"
                            >
                              <CheckCircle2 size={14} className="text-cyan-200" />
                              Make the Change (Simulate Proposed State)
                            </button>
                          )}
                        </div>
                      )}
                    </>
                  ) : null}
                </div>
              )}

              {solutionError && (
                <div className="p-2.5 bg-red-950/50 border border-red-800/80 rounded text-xs text-red-200 flex items-center gap-1.5">
                  <AlertTriangle size={13} className="text-red-400 shrink-0" />
                  <span>{solutionError}</span>
                </div>
              )}
            </>
          )}
        </div>
      )}

    </div>
  );
};
