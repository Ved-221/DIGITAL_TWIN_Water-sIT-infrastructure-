import React from 'react';
import classNames from 'classnames';
import { 
  DollarSign, ShieldAlert, Cpu, CheckCircle2, AlertTriangle, 
  GitCompare, Info, Award
} from 'lucide-react';
import type { MultiAgentDecision, WhatIfCandidate } from '../types/whatIf';

interface ThreeAgentsViewProps {
  decision: MultiAgentDecision;
  candidates?: WhatIfCandidate[];
  targetComponentName?: string;
}

export const ThreeAgentsView: React.FC<ThreeAgentsViewProps> = ({
  decision,
  candidates = [],
  targetComponentName = 'Target Component'
}) => {
  const { financial, risk, architect, consensus } = decision;

  // Resolve candidate friendly names from candidate IDs
  const getCandidateName = (id?: string | null): string => {
    if (!id) return 'None Selected';
    const found = candidates.find(c => c.candidate_id === id);
    return found ? found.name : id;
  };

  const isDisagreement = consensus.agreement === 'split' || consensus.agreement === 'none' || (consensus.conflicts && consensus.conflicts.length > 0);
  const consensusCandidateName = getCandidateName(consensus.candidate_id);

  return (
    <div className="space-y-4 pt-2">
      {/* Header Banner */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
            <Award size={15} />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white uppercase tracking-wider">
              Three-Agent Expert Decision Layer
            </h4>
            <p className="text-[10px] text-slate-400">
              Multi-perspective analysis grounded in deterministic graph simulation and ML ranking
            </p>
          </div>
        </div>
        <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/80">
          Independent Consensus Engine
        </span>
      </div>

      {/* 3 Agents Columns Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
        
        {/* 1. FINANCIAL ANALYST */}
        <div className="bg-slate-950/80 border border-emerald-900/40 rounded-xl p-4 flex flex-col justify-between space-y-3 shadow-md hover:border-emerald-700/60 transition">
          <div className="space-y-2.5">
            {/* Agent Header */}
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
              <div className="flex items-center gap-1.5">
                <div className="p-1 rounded bg-emerald-500/10 text-emerald-400">
                  <DollarSign size={14} />
                </div>
                <span className="font-bold text-slate-200 text-[11px] uppercase tracking-wide">
                  Financial Analyst
                </span>
              </div>
              <span className={classNames(
                "text-[9px] font-mono px-1.5 py-0.2 rounded uppercase font-semibold",
                financial.cost_status === 'known' 
                  ? "bg-emerald-950 text-emerald-300 border border-emerald-800" 
                  : "bg-slate-800 text-amber-300 border border-amber-800/60"
              )}>
                {financial.cost_status === 'known' ? 'Pricing Known' : 'Cost Unknown'}
              </span>
            </div>

            {/* Assessment */}
            <div>
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                Assessment
              </span>
              <p className="text-[11px] text-slate-300 leading-relaxed bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                {financial.summary}
              </p>
            </div>

            {/* Available Evidence */}
            {financial.evidence && financial.evidence.length > 0 && (
              <div className="space-y-1">
                <span className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider block">
                  Available Evidence:
                </span>
                <ul className="space-y-1 text-[11px] text-slate-300 bg-emerald-950/20 p-2 rounded-lg border border-emerald-900/30">
                  {financial.evidence.map((ev, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="text-emerald-400 font-bold">•</span>
                      <span>{ev}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Concerns / Missing Data */}
            <div className="space-y-1">
              <span className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider block">
                Missing Data & Constraints:
              </span>
              {financial.cost_status === 'unknown' ? (
                <div className="text-[11px] text-amber-200 bg-amber-950/20 border border-amber-900/40 p-2 rounded-lg space-y-1">
                  <div className="font-semibold text-amber-300 flex items-center gap-1">
                    <AlertTriangle size={12} />
                    <span>Cost data unavailable.</span>
                  </div>
                  <p className="text-[10px] text-amber-300/80">
                    No billing or cost-per-month telemetry exists for {targetComponentName}. No prices were estimated or invented.
                  </p>
                </div>
              ) : financial.unknowns && financial.unknowns.length > 0 ? (
                <ul className="space-y-1 text-[10px] text-slate-400 bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                  {financial.unknowns.map((u, i) => (
                    <li key={i} className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                      <span>Missing: {u.replace(/_/g, ' ')}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-[10px] text-slate-500 italic">No missing financial constraints flagged.</span>
              )}
            </div>
          </div>

          {/* Recommendation */}
          <div className="pt-2 border-t border-slate-800/80">
            <span className="text-[10px] text-slate-400 block font-medium mb-0.5">Recommendation</span>
            <div className="text-[11px] font-semibold text-emerald-300 bg-emerald-950/30 p-2 rounded-lg border border-emerald-900/50">
              {financial.recommended_candidate_id 
                ? `${getCandidateName(financial.recommended_candidate_id)}`
                : 'Recommendation deferred (Pricing missing)'}
            </div>
          </div>
        </div>

        {/* 2. RISK ANALYST */}
        <div className="bg-slate-950/80 border border-rose-900/40 rounded-xl p-4 flex flex-col justify-between space-y-3 shadow-md hover:border-rose-700/60 transition">
          <div className="space-y-2.5">
            {/* Agent Header */}
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
              <div className="flex items-center gap-1.5">
                <div className="p-1 rounded bg-rose-500/10 text-rose-400">
                  <ShieldAlert size={14} />
                </div>
                <span className="font-bold text-slate-200 text-[11px] uppercase tracking-wide">
                  Risk Analyst
                </span>
              </div>
              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-800 font-semibold">
                Blast & SPOF
              </span>
            </div>

            {/* Assessment */}
            <div>
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                Assessment
              </span>
              <p className="text-[11px] text-slate-300 leading-relaxed bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                {risk.summary}
              </p>
            </div>

            {/* Available Evidence */}
            {risk.evidence && risk.evidence.length > 0 && (
              <div className="space-y-1">
                <span className="text-[10px] font-semibold text-rose-400 uppercase tracking-wider block">
                  Available Evidence:
                </span>
                <ul className="space-y-1 text-[11px] text-slate-300 bg-rose-950/20 p-2 rounded-lg border border-rose-900/30">
                  {risk.evidence.map((ev, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="text-rose-400 font-bold">•</span>
                      <span>{ev}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Concerns / Missing Data */}
            <div className="space-y-1">
              <span className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider block">
                Missing Telemetry Signals:
              </span>
              {risk.unknowns && risk.unknowns.length > 0 ? (
                <ul className="space-y-1 text-[10px] text-slate-400 bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                  {risk.unknowns.map((u, i) => (
                    <li key={i} className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                      <span>Missing: {u.replace(/_/g, ' ')}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-[10px] text-slate-500 italic">Full topological telemetry available.</span>
              )}
            </div>
          </div>

          {/* Recommendation */}
          <div className="pt-2 border-t border-slate-800/80">
            <span className="text-[10px] text-slate-400 block font-medium mb-0.5">Recommendation</span>
            <div className="text-[11px] font-semibold text-rose-300 bg-rose-950/30 p-2 rounded-lg border border-rose-900/50">
              {risk.recommended_candidate_id 
                ? `${getCandidateName(risk.recommended_candidate_id)}`
                : 'No candidate available'}
            </div>
          </div>
        </div>

        {/* 3. SYSTEM / CLOUD ARCHITECT */}
        <div className="bg-slate-950/80 border border-cyan-900/40 rounded-xl p-4 flex flex-col justify-between space-y-3 shadow-md hover:border-cyan-700/60 transition">
          <div className="space-y-2.5">
            {/* Agent Header */}
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
              <div className="flex items-center gap-1.5">
                <div className="p-1 rounded bg-cyan-500/10 text-cyan-400">
                  <Cpu size={14} />
                </div>
                <span className="font-bold text-slate-200 text-[11px] uppercase tracking-wide">
                  System / Cloud Architect
                </span>
              </div>
              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-semibold">
                Feasibility & Mutations
              </span>
            </div>

            {/* Assessment */}
            <div>
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                Assessment
              </span>
              <p className="text-[11px] text-slate-300 leading-relaxed bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                {architect.summary}
              </p>
            </div>

            {/* Available Evidence */}
            {architect.evidence && architect.evidence.length > 0 && (
              <div className="space-y-1">
                <span className="text-[10px] font-semibold text-cyan-400 uppercase tracking-wider block">
                  Available Evidence:
                </span>
                <ul className="space-y-1 text-[11px] text-slate-300 bg-cyan-950/20 p-2 rounded-lg border border-cyan-900/30">
                  {architect.evidence.map((ev, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="text-cyan-400 font-bold">•</span>
                      <span>{ev}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Concerns / Missing Data */}
            <div className="space-y-1">
              <span className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider block">
                Operational Unknowns:
              </span>
              {architect.unknowns && architect.unknowns.length > 0 ? (
                <ul className="space-y-1 text-[10px] text-slate-400 bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                  {architect.unknowns.map((u, i) => (
                    <li key={i} className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                      <span>Missing: {u.replace(/_/g, ' ')}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-[10px] text-slate-500 italic">No architectural unknowns flagged.</span>
              )}
            </div>
          </div>

          {/* Recommendation */}
          <div className="pt-2 border-t border-slate-800/80">
            <span className="text-[10px] text-slate-400 block font-medium mb-0.5">Recommendation</span>
            <div className="text-[11px] font-semibold text-cyan-300 bg-cyan-950/30 p-2 rounded-lg border border-cyan-900/50">
              {architect.recommended_candidate_id 
                ? `${getCandidateName(architect.recommended_candidate_id)}`
                : 'No candidate available'}
            </div>
          </div>
        </div>

      </div>

      {/* AGENT DECISIONS SUMMARY BAR */}
      <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <GitCompare size={13} className="text-indigo-400" />
          <span>Agent Decisions:</span>
        </span>
        <div className="flex flex-wrap items-center gap-3 text-[11px]">
          <span className="flex items-center gap-1 bg-slate-950 px-2 py-1 rounded border border-slate-800">
            <span className="text-emerald-400 font-semibold">Financial:</span>
            <span className="text-slate-200">
              {financial.recommended_candidate_id ? getCandidateName(financial.recommended_candidate_id) : 'Deferred'}
            </span>
          </span>
          <span className="flex items-center gap-1 bg-slate-950 px-2 py-1 rounded border border-slate-800">
            <span className="text-rose-400 font-semibold">Risk:</span>
            <span className="text-slate-200">
              {risk.recommended_candidate_id ? getCandidateName(risk.recommended_candidate_id) : 'None'}
            </span>
          </span>
          <span className="flex items-center gap-1 bg-slate-950 px-2 py-1 rounded border border-slate-800">
            <span className="text-cyan-400 font-semibold">Architect:</span>
            <span className="text-slate-200">
              {architect.recommended_candidate_id ? getCandidateName(architect.recommended_candidate_id) : 'None'}
            </span>
          </span>
        </div>
      </div>

      {/* CONSENSUS & CONFLICT TRADEOFF SECTION */}
      <div className={classNames(
        "p-4 rounded-xl border space-y-3 transition",
        isDisagreement
          ? "bg-amber-950/20 border-amber-900/50"
          : "bg-indigo-950/20 border-indigo-900/50"
      )}>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2">
          <div className="flex items-center gap-2">
            {isDisagreement ? (
              <span className="px-2.5 py-0.5 rounded-md bg-amber-900/60 text-amber-300 font-bold text-[10px] tracking-wide border border-amber-700 flex items-center gap-1">
                <AlertTriangle size={12} />
                <span>AGENTS DISAGREE</span>
              </span>
            ) : (
              <span className="px-2.5 py-0.5 rounded-md bg-emerald-900/60 text-emerald-300 font-bold text-[10px] tracking-wide border border-emerald-700 flex items-center gap-1">
                <CheckCircle2 size={12} />
                <span>AGENT CONSENSUS REACHED ({consensus.agreement.toUpperCase()})</span>
              </span>
            )}
            <span className="text-xs font-bold text-white">
              {consensus.candidate_id ? `Favored: ${consensusCandidateName}` : 'No Consensus Candidate'}
            </span>
          </div>

          {/* ML Alignment Flag */}
          <div className="flex items-center gap-1.5 text-[10px] font-mono">
            {consensus.ml_alignment ? (
              <span className="text-purple-300 bg-purple-950/60 px-2 py-0.5 rounded border border-purple-800">
                ✓ Aligns with ML Rank #1
              </span>
            ) : (
              <span className="text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                Independent from ML Rank #1
              </span>
            )}
          </div>
        </div>

        {/* Reasoning and Tradeoff Summaries */}
        {consensus.reasoning && consensus.reasoning.length > 0 && (
          <div className="space-y-1 text-xs">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              Consensus Reasoning:
            </span>
            <ul className="space-y-1 text-[11px] text-slate-300">
              {consensus.reasoning.map((r, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="text-indigo-400 font-bold">›</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Explicit Conflict Breakdown */}
        {consensus.conflicts && consensus.conflicts.length > 0 && (
          <div className="space-y-2 pt-1 border-t border-slate-800/80">
            <span className="text-[10px] font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1">
              <AlertTriangle size={12} />
              <span>Explicit Tradeoff Conflicts ({consensus.conflicts.length}):</span>
            </span>
            <div className="space-y-2">
              {consensus.conflicts.map((conflict, i) => (
                <div key={i} className="bg-slate-950/90 p-3 rounded-lg border border-amber-900/40 space-y-1.5 text-xs">
                  <div className="font-bold text-amber-200 text-[11px]">
                    Dimension: {conflict.dimension}
                  </div>
                  {conflict.financial_view && (
                    <div className="text-[10px] text-emerald-300">
                      <span className="font-semibold">Financial Perspective: </span>
                      <span>{conflict.financial_view}</span>
                    </div>
                  )}
                  {conflict.risk_view && (
                    <div className="text-[10px] text-rose-300">
                      <span className="font-semibold">Risk Perspective: </span>
                      <span>{conflict.risk_view}</span>
                    </div>
                  )}
                  {conflict.architect_view && (
                    <div className="text-[10px] text-cyan-300">
                      <span className="font-semibold">Architect Perspective: </span>
                      <span>{conflict.architect_view}</span>
                    </div>
                  )}
                  {conflict.tradeoff_summary && (
                    <div className="text-[11px] text-slate-200 bg-amber-950/30 p-2 rounded border border-amber-800/40 mt-1">
                      <span className="font-semibold text-amber-300">Architectural Compromise: </span>
                      <span>{conflict.tradeoff_summary}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Trust Notice */}
        <div className="pt-2 border-t border-slate-800/80 flex items-center gap-2 text-[10px] text-slate-500">
          <Info size={12} className="text-slate-400 shrink-0" />
          <span>
            Three-Agent analysis synthesizes deterministic graph simulations. Recommendations never mutate infrastructure.
          </span>
        </div>
      </div>
    </div>
  );
};
