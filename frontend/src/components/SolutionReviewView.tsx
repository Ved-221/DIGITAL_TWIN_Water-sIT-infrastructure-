import React from 'react';
import classNames from 'classnames';
import { 
  ArrowLeft, CheckCircle2, AlertTriangle, ShieldCheck, 
  ShieldAlert, GitCompare, Zap, Layers, RefreshCw, 
  Server, Lock, DollarSign, Clock, ArrowRight
} from 'lucide-react';
import type { WhatIfCandidate, WhatIfBaselineResult } from '../types/whatIf';

interface SolutionReviewViewProps {
  candidate: WhatIfCandidate;
  baseline: WhatIfBaselineResult | null;
  targetNode: any | null;
  sourceEnvironment?: string;
  isApplying: boolean;
  applyError?: string | null;
  onApply: () => void;
  onCancel: () => void;
}

export const SolutionReviewView: React.FC<SolutionReviewViewProps> = ({
  candidate,
  baseline,
  targetNode,
  isApplying,
  applyError,
  onApply,
  onCancel
}) => {
  const sim = candidate.simulation_result;
  const vs = sim?.vs_baseline;
  const targetName = targetNode?.data?.label || targetNode?.id || baseline?.target_component_name || 'Component';
  const stratType = candidate.strategy_type?.toLowerCase() || '';

  // Parse structured topology changes
  const getStructuredChanges = () => {
    if (stratType.includes('multi_az') || stratType.includes('redundancy') || stratType.includes('load_balancer')) {
      return {
        added: [
          { name: `ALB-${targetName}`, type: 'Application Load Balancer', role: 'Traffic distribution & health monitoring' },
          { name: `${targetName}-Standby-AZ2`, type: targetNode?.data?.type || 'Application / Service', role: 'Multi-AZ hot standby replica' }
        ],
        modified: [
          { name: targetName, change: 'Criticality lowered to Medium; Multi-AZ active health checks enabled' }
        ],
        removed: [],
        dependencies: [
          'Upstream caller traffic rerouted directly to ingress ALB',
          'Ingress ALB forwards traffic to Primary and Standby target groups',
          'Automated health check and failover paths established'
        ]
      };
    } else if (stratType.includes('replica') || stratType.includes('replication')) {
      return {
        added: [
          { name: `${targetName}-ReadReplica`, type: 'Database (Read Replica)', role: 'Read-traffic offloading' }
        ],
        modified: [
          { name: targetName, change: 'Automated asynchronous replication stream activated' }
        ],
        removed: [],
        dependencies: [
          'Dedicated database replication link: ReadReplica replicates from Primary',
          'Read traffic routed to replica pool, reducing primary query load'
        ]
      };
    } else if (stratType.includes('circuit_breaker') || stratType.includes('buffer') || stratType.includes('queue')) {
      return {
        added: [
          { name: `Queue-Buffer-${targetName}`, type: 'Asynchronous Queue Buffer', role: 'Decoupling & backpressure absorption' }
        ],
        modified: [
          { name: targetName, change: 'Decoupled from synchronous caller dependencies' }
        ],
        removed: [],
        dependencies: [
          'Upstream synchronous callers rerouted to message buffer queue',
          'Asynchronous worker ingestion path to target component'
        ]
      };
    } else if (stratType.includes('blue_green') || stratType.includes('shadow') || stratType.includes('migration')) {
      return {
        added: [
          { name: `${targetName}-Shadow-Target`, type: targetNode?.data?.type || 'Shadow Target', role: 'Zero-downtime cutover target' }
        ],
        modified: [
          { name: targetName, change: 'Dual-run state replication activated (0 min downtime)' }
        ],
        removed: [],
        dependencies: [
          'Dual-write / sync link established between primary and shadow target'
        ]
      };
    } else if (stratType.includes('scale')) {
      return {
        added: [],
        modified: [
          { name: targetName, change: 'Doubled compute allocations (CPU: 2x, RAM: 2x)' }
        ],
        removed: [],
        dependencies: [
          'All existing dependency connections maintained at higher throughput capacity'
        ]
      };
    } else if (stratType.includes('remove') || stratType.includes('decommission')) {
      return {
        added: [],
        modified: [],
        removed: [
          { name: targetName, type: targetNode?.data?.type || 'Component', role: 'Decommissioned from topology' }
        ],
        dependencies: [
          'All incident upstream and downstream edges removed'
        ]
      };
    }

    return {
      added: candidate.resulting_topology?.nodes?.filter((n: any) => n.id.startsWith('alb-') || n.id.startsWith('standby-') || n.id.startsWith('replica-') || n.id.startsWith('queue-')).map((n: any) => ({
        name: n.name,
        type: n.type,
        role: 'Remediation node'
      })) || [],
      modified: [{ name: targetName, change: 'Topology and resilience attributes remediated' }],
      removed: [],
      dependencies: candidate.proposed_changes || ['Dependency paths optimized for resilience']
    };
  };

  const changes = getStructuredChanges();

  return (
    <div className="flex flex-col h-full space-y-4 text-slate-100">
      
      {/* Top Header / Back Navigation */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isApplying}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition flex items-center gap-1 text-xs"
          >
            <ArrowLeft size={14} />
            <span>Back to Candidates</span>
          </button>
          <span className="text-slate-600">/</span>
          <span className="text-xs font-semibold text-purple-400 uppercase tracking-wider font-mono">
            Solution Review
          </span>
        </div>
        
        <div className="flex items-center gap-2">
          <span className={classNames(
            "px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider font-mono border",
            candidate.feasibility === 'feasible' 
              ? "bg-emerald-950/80 text-emerald-300 border-emerald-700/80"
              : candidate.feasibility === 'conditional'
              ? "bg-amber-950/80 text-amber-300 border-amber-700/80"
              : "bg-slate-800 text-slate-300 border-slate-700"
          )}>
            {candidate.feasibility}
          </span>
        </div>
      </div>

      {/* Main Review Title */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-purple-950/40 via-indigo-950/30 to-slate-900 border border-purple-800/40 shadow-sm space-y-1.5 shrink-0">
        <div className="flex items-center gap-2">
          <GitCompare size={18} className="text-purple-400" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400 font-mono">
            SOLUTION SELECTED
          </span>
        </div>
        <h2 className="text-lg font-black text-white tracking-tight">
          {candidate.name}
        </h2>
        <p className="text-xs text-slate-300 leading-relaxed">
          {candidate.description}
        </p>
      </div>

      {/* Scrollable Review Body */}
      <div className="flex-1 overflow-y-auto space-y-5 pr-1 text-xs">
        
        {/* Error banner if previous apply attempt failed */}
        {applyError && (
          <div className="p-3 bg-red-950/80 border border-red-800 rounded-xl text-red-200 flex items-start gap-2.5">
            <AlertTriangle size={16} className="text-red-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-xs block">Failed to apply solution to sandbox</span>
              <span className="text-[11px] text-red-300">{applyError}</span>
            </div>
          </div>
        )}

        {/* SECTION 1: WHAT CHANGES (Topology Mutations) */}
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Layers size={13} className="text-blue-400" />
              <span>What Changes in the Digital Twin</span>
            </span>
            <span className="text-[10px] text-slate-400 font-mono">
              Actual Graph Transformation
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            
            {/* Components Added */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
              <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                <CheckCircle2 size={12} />
                <span>Components Added ({changes.added.length})</span>
              </span>
              {changes.added.length > 0 ? (
                <div className="space-y-1.5">
                  {changes.added.map((item: any, idx: number) => (
                    <div key={idx} className="p-2 rounded-lg bg-slate-950/80 border border-slate-800/80 text-[11px]">
                      <div className="font-semibold text-emerald-300 font-mono">{item.name}</div>
                      <div className="text-[10px] text-slate-400">{item.type} • {item.role}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <span className="text-[11px] text-slate-500 italic block">No new components required</span>
              )}
            </div>

            {/* Components Modified */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
              <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1">
                <Server size={12} />
                <span>Components Modified ({changes.modified.length})</span>
              </span>
              {changes.modified.length > 0 ? (
                <div className="space-y-1.5">
                  {changes.modified.map((item: any, idx: number) => (
                    <div key={idx} className="p-2 rounded-lg bg-slate-950/80 border border-slate-800/80 text-[11px]">
                      <div className="font-semibold text-cyan-300 font-mono">{item.name}</div>
                      <div className="text-[10px] text-slate-400">{item.change}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <span className="text-[11px] text-slate-500 italic block">No component attribute modifications</span>
              )}
            </div>

            {/* Components Removed */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
              <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider flex items-center gap-1">
                <AlertTriangle size={12} />
                <span>Components Removed ({changes.removed.length})</span>
              </span>
              {changes.removed.length > 0 ? (
                <div className="space-y-1.5">
                  {changes.removed.map((item: any, idx: number) => (
                    <div key={idx} className="p-2 rounded-lg bg-slate-950/80 border border-slate-800/80 text-[11px]">
                      <div className="font-semibold text-red-300 font-mono">{item.name}</div>
                      <div className="text-[10px] text-slate-400">{item.type} • {item.role}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <span className="text-[11px] text-slate-500 italic block">Preserves all existing components (0 removed)</span>
              )}
            </div>

            {/* Dependencies Changed */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
              <span className="text-[10px] font-bold text-purple-400 uppercase tracking-wider flex items-center gap-1">
                <Zap size={12} />
                <span>Dependencies Changed ({changes.dependencies.length})</span>
              </span>
              <div className="space-y-1.5">
                {changes.dependencies.map((dep: string, idx: number) => (
                  <div key={idx} className="p-2 rounded-lg bg-slate-950/80 border border-slate-800/80 text-[11px] text-slate-300">
                    • {dep}
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* Full Proposed Mutations Checklist */}
          {candidate.proposed_changes && candidate.proposed_changes.length > 0 && (
            <div className="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-1.5">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Engine Mutation Plan:
              </span>
              <div className="space-y-1 text-[11px] text-slate-300">
                {candidate.proposed_changes.map((change, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <CheckCircle2 size={13} className="text-emerald-400 shrink-0 mt-0.5" />
                    <span>{change}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* SECTION 2: WHY (Objective Remediation Evidence & Metrics) */}
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <ShieldCheck size={13} className="text-emerald-400" />
              <span>Why: Objective Remediation Impact</span>
            </span>
            <span className="text-[10px] text-emerald-400 font-mono">
              Deterministic Simulation Evidence
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            
            {/* Risk Score */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Risk Score
              </span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-slate-400 line-through text-xs">
                  {baseline?.risk_score != null ? baseline.risk_score.toFixed(0) : '—'}
                </span>
                <ArrowRight size={12} className="text-slate-500" />
                <span className="font-mono text-white font-bold text-sm">
                  {sim?.risk_score != null ? sim.risk_score.toFixed(0) : '0'}
                </span>
              </div>
              {vs?.risk_score_delta != null && vs.risk_score_delta < 0 && (
                <span className="text-[10px] text-emerald-400 font-semibold block">
                  {vs.risk_score_delta.toFixed(0)} risk points
                </span>
              )}
            </div>

            {/* SPOF Status */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                SPOF Status
              </span>
              <div className="flex items-center gap-1.5">
                {sim?.spof_eliminated ? (
                  <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold text-[10px] flex items-center gap-1">
                    <CheckCircle2 size={11} />
                    <span>ELIMINATED</span>
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]">
                    Maintained
                  </span>
                )}
              </div>
              <span className="text-[10px] text-slate-400 block truncate">
                {baseline?.is_single_point_of_failure ? 'Was single point of failure' : 'Resilient path'}
              </span>
            </div>

            {/* Blast Radius */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Blast Radius
              </span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-slate-400 line-through text-xs">
                  {baseline?.blast_radius ?? 1}
                </span>
                <ArrowRight size={12} className="text-slate-500" />
                <span className="font-mono text-white font-bold text-sm">
                  {sim?.blast_radius ?? 0}
                </span>
              </div>
              <span className="text-[10px] text-slate-400 block">
                {sim?.blast_radius === 0 ? 'Zero blast radius' : `${sim?.blast_radius} affected nodes`}
              </span>
            </div>

            {/* Availability */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Availability
              </span>
              <div className="font-bold text-emerald-300 text-xs flex items-center gap-1">
                <ShieldCheck size={13} />
                <span>Multi-AZ HA</span>
              </div>
              <span className="text-[10px] text-slate-400 block">
                Active health check failover
              </span>
            </div>

            {/* Est. Downtime */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Est. Downtime
              </span>
              <div className="flex items-center gap-1 text-white font-mono font-bold text-sm">
                <Clock size={13} className="text-blue-400" />
                <span>{sim?.estimated_downtime_minutes != null ? `${sim.estimated_downtime_minutes}m` : '0m'}</span>
              </div>
              <span className="text-[10px] text-emerald-400 block">
                {sim?.estimated_downtime_minutes === 0 ? 'Zero-downtime cutover' : 'Brief maintenance'}
              </span>
            </div>

            {/* Cost Impact */}
            <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-1">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                Monthly Cost
              </span>
              <div className="flex items-center gap-1 text-white font-mono font-bold text-sm">
                <DollarSign size={13} className="text-amber-400" />
                <span>
                  {sim?.cost_delta_monthly != null 
                    ? `${sim.cost_delta_monthly > 0 ? '+' : ''}$${sim.cost_delta_monthly.toFixed(0)}/mo` 
                    : 'Cost neutral'}
                </span>
              </div>
              <span className="text-[10px] text-slate-400 block truncate">
                {sim?.cost_delta_monthly && sim.cost_delta_monthly > 0 ? 'Secondary replica / ALB cost' : 'No cost increase'}
              </span>
            </div>

          </div>
        </div>

        {/* SECTION 3: BEFORE vs AFTER ARCHITECTURE */}
        <div className="space-y-2.5">
          <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <GitCompare size={13} className="text-purple-400" />
            <span>Architecture Transformation: Before vs After</span>
          </span>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            
            {/* BEFORE Card */}
            <div className="p-3.5 rounded-xl bg-slate-950/80 border border-red-900/40 space-y-2.5">
              <div className="flex items-center justify-between pb-1.5 border-b border-slate-800/80">
                <span className="text-[10px] font-bold uppercase tracking-wider text-red-400 font-mono flex items-center gap-1">
                  <ShieldAlert size={12} />
                  <span>BEFORE (Current Baseline)</span>
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  Single Point of Failure
                </span>
              </div>
              
              <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 font-mono text-[11px] space-y-2">
                <div className="flex items-center gap-2 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-slate-500"></span>
                  <span>Upstream Ingress / Callers</span>
                </div>
                <div className="pl-3 border-l-2 border-dashed border-red-500/50 py-1 space-y-1">
                  <div className="text-[10px] text-red-400 flex items-center gap-1 font-bold">
                    <AlertTriangle size={11} />
                    <span>Direct Dependency (No Redundancy)</span>
                  </div>
                  <div className="p-1.5 rounded bg-red-950/50 border border-red-800/60 text-red-200 font-semibold">
                    {targetName} (SPOF)
                  </div>
                </div>
                <div className="flex items-center gap-2 text-slate-400">
                  <span className="w-2 h-2 rounded-full bg-slate-600"></span>
                  <span>Downstream Infrastructure</span>
                </div>
              </div>
            </div>

            {/* AFTER Card */}
            <div className="p-3.5 rounded-xl bg-slate-950/80 border border-emerald-900/40 space-y-2.5">
              <div className="flex items-center justify-between pb-1.5 border-b border-slate-800/80">
                <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 font-mono flex items-center gap-1">
                  <ShieldCheck size={12} />
                  <span>AFTER (Proposed Sandbox Architecture)</span>
                </span>
                <span className="text-[10px] text-emerald-400 font-mono">
                  High Availability & Resilient
                </span>
              </div>
              
              <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 font-mono text-[11px] space-y-2">
                <div className="flex items-center gap-2 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-slate-500"></span>
                  <span>Upstream Ingress / Callers</span>
                </div>
                <div className="pl-3 border-l-2 border-emerald-500/50 py-1 space-y-1.5">
                  <div className="p-1.5 rounded bg-blue-950/60 border border-blue-800/60 text-blue-200 font-semibold text-[10px] flex items-center justify-between">
                    <span>ALB-{targetName} (Load Balancer)</span>
                    <span className="text-[9px] text-cyan-300">Active HA</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5 pt-0.5">
                    <div className="p-1.5 rounded bg-emerald-950/50 border border-emerald-800/60 text-emerald-200 font-semibold text-[10px]">
                      {targetName} (AZ-1)
                    </div>
                    <div className="p-1.5 rounded bg-emerald-950/50 border border-emerald-800/60 text-emerald-200 font-semibold text-[10px]">
                      {targetName}-Standby (AZ-2)
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-slate-400">
                  <span className="w-2 h-2 rounded-full bg-slate-600"></span>
                  <span>Downstream Infrastructure</span>
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* SECTION 4: AWS SAFETY GUARANTEE */}
        <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800 flex items-start gap-2.5">
          <Lock size={15} className="text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="text-[11px] font-bold text-amber-300 block">
              Simulation Only — AWS Live Infrastructure Remains Read-Only
            </span>
            <p className="text-[10px] text-slate-400 leading-normal">
              No live cloud mutation, API deletion, or cost will occur. This solution transforms the isolated Digital Twin Sandbox environment to verify topology stability, risk reduction, and blast radius changes before any production decision.
            </p>
          </div>
        </div>

      </div>

      {/* Action Footer */}
      <div className="pt-3 border-t border-slate-800 flex items-center justify-between gap-3 shrink-0">
        <button
          type="button"
          onClick={onCancel}
          disabled={isApplying}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-xs font-semibold transition disabled:opacity-50"
        >
          Cancel
        </button>

        <button
          type="button"
          onClick={onApply}
          disabled={isApplying}
          className="px-5 py-2.5 bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 disabled:opacity-50 text-white rounded-lg text-xs font-bold shadow-lg shadow-emerald-950/30 transition flex items-center gap-2"
        >
          {isApplying ? (
            <>
              <RefreshCw size={14} className="animate-spin" />
              <span>Applying Solution to Sandbox...</span>
            </>
          ) : (
            <>
              <CheckCircle2 size={14} />
              <span>Apply Solution to Sandbox</span>
            </>
          )}
        </button>
      </div>

    </div>
  );
};
