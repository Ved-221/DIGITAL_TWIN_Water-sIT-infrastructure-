import React, { useState } from 'react';
import { 
  CheckCircle2, RotateCcw, AlertTriangle, 
  ChevronDown, ChevronUp, Layers, Lock, ArrowRight, RefreshCw
} from 'lucide-react';
import type { SandboxApplyResponse } from '../types/sandbox';

interface SandboxTransformationBarProps {
  sandboxResult: SandboxApplyResponse;
  isLoading: boolean;
  onAccept: () => void;
  onRollback: () => void;
}

export const SandboxTransformationBar: React.FC<SandboxTransformationBarProps> = ({
  sandboxResult,
  isLoading,
  onAccept,
  onRollback
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const { before, after, delta, topology_diff, mutations_applied, tradeoffs, remediation_outcome } = sandboxResult;
  const isImproved = remediation_outcome === 'IMPROVED' || (delta?.risk && delta.risk < 0) || (delta?.spof_count && delta.spof_count < 0);
  const friendlyName = sandboxResult.strategy_type?.replace(/_/g, ' ').toUpperCase() || 'ARCHITECTURE MODERNIZATION';

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 w-11/12 max-w-5xl transition-all duration-300">
      <div className="rounded-2xl bg-slate-950/95 backdrop-blur-xl border border-purple-500/50 shadow-2xl shadow-purple-950/40 p-4 text-white space-y-3">
        
        {/* Top Status & Controls Row */}
        <div className="flex flex-wrap items-center justify-between gap-3 pb-2.5 border-b border-slate-800">
          
          {/* Left Title & Strategy */}
          <div className="flex items-center gap-2.5">
            <span className="flex h-3 w-3 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-purple-500"></span>
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-purple-900/60 border border-purple-700/60 text-purple-300 font-extrabold text-[10px] tracking-wider uppercase font-mono">
                  SANDBOX TRANSFORMED
                </span>
                <span className="font-bold text-sm text-white">
                  {friendlyName}
                </span>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-slate-300 mt-0.5">
                {isImproved ? (
                  <span className="text-emerald-400 font-semibold flex items-center gap-1">
                    <CheckCircle2 size={13} />
                    <span>Objective Improvement: Resilience increased & SPOF eliminated</span>
                  </span>
                ) : (
                  <span className="text-amber-400 font-medium flex items-center gap-1">
                    <AlertTriangle size={13} />
                    <span>Alternative architecture evaluated in isolated sandbox</span>
                  </span>
                )}
                <span className="text-slate-600">•</span>
                <span className="text-slate-400 flex items-center gap-1 text-[10px]">
                  <Lock size={10} className="text-amber-400" />
                  <span>AWS Live read-only</span>
                </span>
              </div>
            </div>
          </div>

          {/* Right Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition flex items-center gap-1 border border-slate-700"
            >
              <Layers size={13} />
              <span>{isExpanded ? 'Hide Details' : 'View Diff'}</span>
              {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>

            <button
              type="button"
              onClick={onRollback}
              disabled={isLoading}
              className="px-3.5 py-1.5 rounded-lg bg-red-950/80 hover:bg-red-900 text-red-200 border border-red-800/80 text-xs font-bold transition shadow-sm flex items-center gap-1.5 disabled:opacity-50"
            >
              {isLoading ? (
                <RefreshCw size={13} className="animate-spin" />
              ) : (
                <RotateCcw size={13} />
              )}
              <span>Rollback to Baseline</span>
            </button>

            <button
              type="button"
              onClick={onAccept}
              disabled={isLoading}
              className="px-4 py-1.5 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold transition shadow-lg shadow-emerald-950/30 flex items-center gap-1.5 disabled:opacity-50"
            >
              {isLoading ? (
                <RefreshCw size={13} className="animate-spin" />
              ) : (
                <CheckCircle2 size={13} />
              )}
              <span>Accept Solution</span>
            </button>
          </div>

        </div>

        {/* Before vs After Metric Comparison Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
          
          {/* Risk Score */}
          <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-1">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              Risk Score
            </span>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-slate-400 line-through text-[11px]">
                {before?.risk != null ? before.risk.toFixed(0) : '—'}
              </span>
              <ArrowRight size={11} className="text-slate-500" />
              <span className="font-mono font-bold text-white text-sm">
                {after?.risk != null ? after.risk.toFixed(0) : '0'}
              </span>
            </div>
            {delta?.risk != null && delta.risk < 0 && (
              <span className="text-[10px] font-semibold text-emerald-400 block font-mono">
                {delta.risk.toFixed(0)} pts
              </span>
            )}
          </div>

          {/* SPOF Elimination */}
          <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-1">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              SPOFs
            </span>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-slate-400 line-through text-[11px]">
                {before?.spof_count ?? 1}
              </span>
              <ArrowRight size={11} className="text-slate-500" />
              <span className="font-mono font-bold text-emerald-400 text-sm">
                {after?.spof_count ?? 0}
              </span>
            </div>
            <span className="text-[10px] font-semibold text-emerald-400 block">
              {(before?.spof_count ?? 0) > (after?.spof_count ?? 0) ? 'SPOF Eliminated' : 'Zero SPOF'}
            </span>
          </div>

          {/* Blast Radius */}
          <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-1">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              Blast Radius
            </span>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-slate-400 line-through text-[11px]">
                {before?.blast_radius ?? 1}
              </span>
              <ArrowRight size={11} className="text-slate-500" />
              <span className="font-mono font-bold text-white text-sm">
                {after?.blast_radius ?? 0}
              </span>
            </div>
            <span className="text-[10px] text-slate-400 block">
              affected nodes
            </span>
          </div>

          {/* Downtime */}
          <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-1">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              Est. Downtime
            </span>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-slate-400 line-through text-[11px]">
                {before?.downtime ?? 0}m
              </span>
              <ArrowRight size={11} className="text-slate-500" />
              <span className="font-mono font-bold text-white text-sm">
                {after?.downtime ?? 0}m
              </span>
            </div>
            <span className="text-[10px] text-emerald-400 block font-mono">
              Zero-downtime cutover
            </span>
          </div>

          {/* Monthly Cost */}
          <div className="p-2.5 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-1">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              Monthly Cost
            </span>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-slate-400 line-through text-[11px]">
                ${before?.monthly_cost?.toFixed(0) ?? 0}
              </span>
              <ArrowRight size={11} className="text-slate-500" />
              <span className="font-mono font-bold text-white text-sm">
                ${after?.monthly_cost?.toFixed(0) ?? 0}
              </span>
            </div>
            <span className="text-[10px] text-amber-400 block font-mono">
              {delta?.monthly_cost != null && delta.monthly_cost > 0 ? `+$${delta.monthly_cost.toFixed(0)}/mo` : '$0/mo'}
            </span>
          </div>

        </div>

        {/* Collapsible Expanded Details */}
        {isExpanded && (
          <div className="pt-3 border-t border-slate-800 space-y-3 text-xs animate-in fade-in duration-200">
            
            {/* Mutations Applied List */}
            {mutations_applied && mutations_applied.length > 0 && (
              <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-800 space-y-1.5">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                  Mutations Applied to Twin:
                </span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 text-[11px] text-slate-200">
                  {mutations_applied.map((mut, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                      <span>{mut}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Topology Diff Breakdown */}
            {topology_diff && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-emerald-400 font-bold block text-[10px] uppercase tracking-wider">
                    Nodes Added ({topology_diff.nodes_added?.length || 0})
                  </span>
                  <div className="space-y-0.5 mt-1 font-mono text-[10px] text-slate-300">
                    {topology_diff.nodes_added?.map((n: any) => (
                      <div key={n.id} className="truncate">• {n.name}</div>
                    ))}
                    {(!topology_diff.nodes_added || topology_diff.nodes_added.length === 0) && (
                      <span className="text-slate-500 italic">None</span>
                    )}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-cyan-400 font-bold block text-[10px] uppercase tracking-wider">
                    Nodes Modified ({topology_diff.nodes_modified?.length || 0})
                  </span>
                  <div className="space-y-0.5 mt-1 font-mono text-[10px] text-slate-300">
                    {topology_diff.nodes_modified?.map((n: any) => (
                      <div key={n.id} className="truncate">• {n.name}</div>
                    ))}
                    {(!topology_diff.nodes_modified || topology_diff.nodes_modified.length === 0) && (
                      <span className="text-slate-500 italic">None</span>
                    )}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-purple-400 font-bold block text-[10px] uppercase tracking-wider">
                    Edges Added ({topology_diff.edges_added?.length || 0})
                  </span>
                  <div className="space-y-0.5 mt-1 font-mono text-[10px] text-slate-300">
                    {topology_diff.edges_added?.map((e: any, idx: number) => (
                      <div key={idx} className="truncate">• {e.source} → {e.target}</div>
                    ))}
                    {(!topology_diff.edges_added || topology_diff.edges_added.length === 0) && (
                      <span className="text-slate-500 italic">None</span>
                    )}
                  </div>
                </div>

                <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800">
                  <span className="text-red-400 font-bold block text-[10px] uppercase tracking-wider">
                    Edges Removed ({topology_diff.edges_removed?.length || 0})
                  </span>
                  <div className="space-y-0.5 mt-1 font-mono text-[10px] text-slate-300">
                    {topology_diff.edges_removed?.map((e: any, idx: number) => (
                      <div key={idx} className="truncate">• {e.source} → {e.target}</div>
                    ))}
                    {(!topology_diff.edges_removed || topology_diff.edges_removed.length === 0) && (
                      <span className="text-slate-500 italic">None (rerouted)</span>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Tradeoff Explanation */}
            {tradeoffs && tradeoffs.length > 0 && (
              <div className="p-2.5 bg-amber-950/30 rounded-lg border border-amber-800/40 text-[11px] text-amber-300 flex items-start gap-2">
                <AlertTriangle size={14} className="shrink-0 mt-0.5 text-amber-400" />
                <div>
                  <span className="font-bold text-[10px] uppercase tracking-wider block">Identified Tradeoffs:</span>
                  <span className="text-slate-300">{tradeoffs.join(' ')}</span>
                </div>
              </div>
            )}

          </div>
        )}

      </div>
    </div>
  );
};
