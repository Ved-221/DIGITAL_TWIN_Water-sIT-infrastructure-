import React from 'react';
import { 
  Server, AlertTriangle, DollarSign, Cloud, ShieldCheck, Layers, Radio, RefreshCw, Key, 
  Activity, HeartHandshake, CheckCircle2, Info, Sparkles, Network, Cpu
} from 'lucide-react';
import { formatINR, formatCost, formatISTDateTime, getRegionDisplayName } from '../utils/localization';

interface DashboardViewProps {
  stats: any;
  components: any[];
  awsStatus: any;
  mode?: 'unconnected' | 'live' | 'demo' | 'manual';
  metricsMap?: Record<string, any>;
  costReport?: any;
  healthReport?: any;
  onOpenConnect: () => void;
  onSyncAWS: (useSynthetic: boolean) => void;
  onAddManualResource?: () => void;
  syncing: boolean;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  stats,
  components,
  awsStatus,
  mode = 'unconnected',
  metricsMap = {},
  costReport,
  healthReport,
  onOpenConnect,
  onSyncAWS,
  onAddManualResource,
  syncing
}) => {
  // Count by component type
  const typeCounts: Record<string, number> = {};
  components.forEach((c) => {
    const t = c.type || 'other';
    typeCounts[t] = (typeCounts[t] || 0) + 1;
  });

  // Count by criticality
  const criticalCount = components.filter((c) => c.criticality === 'critical').length;
  const highCount = components.filter((c) => c.criticality === 'high').length;
  const mediumCount = components.filter((c) => c.criticality === 'medium').length;
  const lowCount = components.filter((c) => c.criticality === 'low').length;

  const isLiveAWS = mode === 'live' || (awsStatus?.authenticated && mode !== 'manual');
  const isManual = mode === 'manual' || (!isLiveAWS && components.some(c => c.discovery_source === 'manual'));

  // Derive live CloudWatch Telemetry Health from actual metricsMap
  let telemetryHealthy = 0;
  let telemetryDegraded = 0;
  let telemetryUnavailable = 0;

  components.forEach((c) => {
    const m = metricsMap[c.id];
    if (!m || m.status === 'UNAVAILABLE' || (m.cpu === null && m.latency === null && m.error_rate === null)) {
      telemetryUnavailable++;
    } else if ((m.cpu !== null && m.cpu >= 75) || (m.error_rate !== null && m.error_rate >= 1.0) || m.status === 'degraded') {
      telemetryDegraded++;
    } else {
      telemetryHealthy++;
    }
  });

  return (
    <div className="flex-1 overflow-y-auto p-8 bg-slate-900">
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* Top Header & Mode Banner */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-800/80 border border-slate-700/80 p-6 rounded-2xl shadow-xl">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-2xl font-bold text-white">Infrastructure Health & Digital Twin Estate</h2>
              {isLiveAWS ? (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-950 text-emerald-300 border border-emerald-800/80 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                  LIVE AWS MODE
                </span>
              ) : isManual ? (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/80 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                  MANUAL INFRASTRUCTURE MODE • Custom Topology
                </span>
              ) : (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-950 text-amber-300 border border-amber-800/80 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                  BASELINE MODE
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400">
              {isLiveAWS 
                ? `Connected to AWS Account ${awsStatus?.account_id || ''} (${getRegionDisplayName(awsStatus?.region || 'ap-south-1')}). Discovered resources reflect authentic AWS APIs, live CloudWatch metrics, and actual topologies.`
                : isManual
                ? "User-defined architecture estate. Resources, dependencies, and simulation assumptions are configured manually and analyzed via the common Digital Twin engine."
                : "Viewing Digital Twin environment. Connect active AWS credentials or build manual infrastructure."}
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            {isManual && onAddManualResource && (
              <button
                onClick={onAddManualResource}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition shadow-sm"
              >
                <span>+ Add Resource</span>
              </button>
            )}
            <button
              onClick={onOpenConnect}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600/80 transition shadow-sm"
            >
              <Key size={14} className="text-amber-400" />
              <span>{isLiveAWS ? 'Switch AWS Account' : 'Connect AWS'}</span>
            </button>
            {isLiveAWS && (
              <button
                onClick={() => onSyncAWS(false)}
                disabled={syncing}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition shadow-sm disabled:opacity-40"
              >
                <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
                <span>{syncing ? 'Synchronizing...' : 'Sync Live AWS'}</span>
              </button>
            )}
          </div>
        </div>

        {/* Primary KPI Cards */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
            <div className="bg-slate-800/90 p-5 rounded-xl border border-slate-700/80 shadow-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Server size={15} className="text-blue-400"/> Total Resources
                </span>
                <span className="text-[10px] bg-slate-700 text-slate-300 font-mono px-1.5 py-0.5 rounded">Estate</span>
              </div>
              <div className="text-3xl font-extrabold text-white">{stats.total_components}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                {components.filter(c => c.discovery_source === 'aws_api').length} from AWS APIs • {components.filter(c => c.discovery_source !== 'aws_api').length} Baseline
              </div>
            </div>

            <div className="bg-slate-800/90 p-5 rounded-xl border border-slate-700/80 shadow-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <AlertTriangle size={15} className="text-red-400"/> Critical Tier 1
                </span>
                <span className="text-[10px] bg-red-950 text-red-300 font-mono px-1.5 py-0.5 rounded">High Risk</span>
              </div>
              <div className="text-3xl font-extrabold text-white">{stats.critical_services_count}</div>
              <div className="text-[11px] text-slate-400 mt-1">Requires multi-AZ failover & strict change control</div>
            </div>

            <div className="bg-slate-800/90 p-5 rounded-xl border border-slate-700/80 shadow-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <DollarSign size={15} className="text-emerald-400"/> Monthly Run Rate
                </span>
                <span className="text-[10px] bg-emerald-950 text-emerald-300 font-mono px-1.5 py-0.5 rounded">
                  {isManual ? 'Configured' : 'Estimated'}
                </span>
              </div>
              <div className="text-3xl font-extrabold text-white">
                {isManual 
                  ? formatINR(stats.total_monthly_cost) 
                  : formatCost(stats.total_monthly_cost, 'estimated', 'USD')}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                {isManual ? 'Configured INR resource run rate' : 'AWS instance tier catalog pricing'}
              </div>
            </div>

            <div className="bg-slate-800/90 p-5 rounded-xl border border-slate-700/80 shadow-lg flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                <span className="flex items-center gap-1"><Cloud size={14} className="text-cyan-400" /> Cloud Workloads</span>
                <span className="font-bold text-white">{stats.cloud_count}</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-2 mb-2">
                <div 
                  className="bg-cyan-500 h-2 rounded-full transition-all" 
                  style={{ width: `${stats.total_components > 0 ? (stats.cloud_count / stats.total_components) * 100 : 0}%` }}
                ></div>
              </div>
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                <span className="flex items-center gap-1"><Server size={14} className="text-slate-400" /> On-Prem / Edge</span>
                <span className="font-bold text-white">{stats.on_prem_count}</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-2">
                <div 
                  className="bg-slate-400 h-2 rounded-full transition-all" 
                  style={{ width: `${stats.total_components > 0 ? (stats.on_prem_count / stats.total_components) * 100 : 0}%` }}
                ></div>
              </div>
            </div>
          </div>
        )}

        {/* Live Operational Intelligence Row: Cost Explorer, AWS Health, and CloudWatch Telemetry */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* 1. AWS Cost Explorer Live Spend */}
          <div className="bg-slate-800/80 p-6 rounded-xl border border-slate-700/80 shadow-lg flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <DollarSign size={18} className="text-emerald-400" /> AWS Cost Explorer Spend
                </h3>
                <span className="text-[10px] bg-slate-700 text-slate-300 font-mono px-1.5 py-0.5 rounded">ce:GetCostAndUsage</span>
              </div>

              {costReport?.spend_available ? (
                <div className="space-y-3">
                  <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-700/60">
                    <span className="text-[11px] text-slate-400 block">Current Month-to-Date Spend (Actual)</span>
                    <span className="text-xl font-bold text-emerald-400">
                      {formatCost(costReport.total_month_to_date_cost, 'actual', costReport.currency === 'INR' ? 'INR' : 'USD')}
                    </span>
                    <span className="text-[10px] text-slate-500 block mt-0.5">
                      Period: {costReport.time_period?.start} → {costReport.time_period?.end}
                    </span>
                  </div>

                  <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                    {costReport.service_breakdown?.slice(0, 4).map((svc: any, idx: number) => (
                      <div key={idx} className="flex justify-between items-center text-xs p-1.5 rounded bg-slate-900/40">
                        <span className="text-slate-300 truncate max-w-[170px]">{svc.service_name}</span>
                        <span className="font-mono text-emerald-400 font-semibold">
                          {formatCost(svc.amount, 'actual', costReport.currency === 'INR' ? 'INR' : 'USD')}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-slate-900/40 rounded-lg border border-slate-700/60 text-xs text-slate-400 space-y-2">
                  <div className="flex items-center gap-2 text-slate-300 font-semibold">
                    <Info size={15} className="text-blue-400 shrink-0" />
                    <span>Cost Explorer Status</span>
                  </div>
                  <p>
                    {isLiveAWS 
                      ? (costReport?.error || "Requires AWS IAM ce:GetCostAndUsage permission enabled on this credential role.") 
                      : "Available in Live AWS mode when IAM Cost Explorer permissions are active."}
                  </p>
                  <span className="text-[10px] text-slate-500 block font-mono">
                    Pricing Fallback: US-East-1 Standard Instance Catalog
                  </span>
                </div>
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-slate-700/60 text-[11px] text-slate-400">
              Source: {costReport?.pricing_source || "Standard Instance Catalog (730h/mo)"}
            </div>
          </div>

          {/* 2. AWS Health & Service Events */}
          <div className="bg-slate-800/80 p-6 rounded-xl border border-slate-700/80 shadow-lg flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <HeartHandshake size={18} className="text-cyan-400" /> AWS Health Operational Status
                </h3>
                <span className="text-[10px] bg-slate-700 text-slate-300 font-mono px-1.5 py-0.5 rounded">health:DescribeEvents</span>
              </div>

              {healthReport?.health_available ? (
                healthReport.open_events_count > 0 ? (
                  <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                    {healthReport.events.map((ev: any, idx: number) => (
                      <div key={idx} className="p-2.5 bg-amber-950/40 border border-amber-800/60 rounded-lg text-xs space-y-1">
                        <div className="flex items-center justify-between text-amber-300 font-semibold">
                          <span>{ev.service} • {ev.event_type_code}</span>
                          <span className="uppercase text-[10px] px-1 py-0.2 bg-amber-900 text-amber-200 rounded">{ev.status_code}</span>
                        </div>
                        <p className="text-slate-300 text-[11px] line-clamp-2">{ev.description}</p>
                        {ev.affected_entities?.length > 0 && (
                          <div className="text-[10px] text-slate-400 font-mono">
                            Affected: {ev.affected_entities.slice(0, 2).join(', ')}
                          </div>
                        )}
                        {(ev.start_time || ev.last_update_time) && (
                          <div className="text-[9px] text-slate-400 font-mono">
                            Event Time: {formatISTDateTime(ev.start_time || ev.last_update_time)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-4 bg-emerald-950/30 border border-emerald-800/50 rounded-lg text-xs text-emerald-300 flex items-start gap-2.5">
                    <CheckCircle2 size={18} className="text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-white">All AWS Infrastructure Operational</div>
                      <p className="text-[11px] text-emerald-400/90 mt-0.5">
                        Zero open health events or service degradations reported in {getRegionDisplayName(awsStatus?.region || 'ap-south-1')}.
                      </p>
                    </div>
                  </div>
                )
              ) : (
                <div className="p-4 bg-slate-900/40 rounded-lg border border-slate-700/60 text-xs text-slate-400 space-y-2">
                  <div className="flex items-center gap-2 text-slate-300 font-semibold">
                    <Info size={15} className="text-cyan-400 shrink-0" />
                    <span>AWS Health Endpoint</span>
                  </div>
                  <p>
                    {healthReport?.support_plan_required 
                      ? "AWS Health API requires an active AWS Business or Enterprise Support plan to stream tenant infrastructure events."
                      : (healthReport?.error || "Connect active AWS credentials to query global us-east-1 health endpoint.")}
                  </p>
                  <span className="text-[10px] text-slate-500 block font-mono">
                    Endpoint: health.us-east-1.amazonaws.com
                  </span>
                </div>
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-slate-700/60 text-[11px] text-slate-400">
              Source: {healthReport?.source || "AWS Health API (Global us-east-1)"}
            </div>
          </div>

          {/* 3. CloudWatch Telemetry Health Summary */}
          <div className="bg-slate-800/80 p-6 rounded-xl border border-slate-700/80 shadow-lg flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Activity size={18} className="text-blue-400" /> CloudWatch Telemetry Health
                </h3>
                <span className="text-[10px] bg-slate-700 text-slate-300 font-mono px-1.5 py-0.5 rounded">Real-time</span>
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-center p-2.5 bg-emerald-950/40 border border-emerald-800/60 rounded-lg">
                  <span className="text-xs font-semibold text-emerald-300 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400"></span> Nominal & Healthy
                  </span>
                  <span className="font-mono font-bold text-emerald-200 text-base">{telemetryHealthy}</span>
                </div>

                <div className="flex justify-between items-center p-2.5 bg-amber-950/40 border border-amber-800/60 rounded-lg">
                  <span className="text-xs font-semibold text-amber-300 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span> Under Telemetry Stress
                  </span>
                  <span className="font-mono font-bold text-amber-200 text-base">{telemetryDegraded}</span>
                </div>

                <div className="flex justify-between items-center p-2.5 bg-slate-900/60 border border-slate-700/60 rounded-lg">
                  <span className="text-xs font-semibold text-slate-400 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-slate-500"></span> No Data / Unavailable
                  </span>
                  <span className="font-mono font-bold text-slate-300 text-base">{telemetryUnavailable}</span>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-700/60 text-[11px] text-slate-400">
              Evaluated across CPU Utilization, Latency ms, and HTTP 5XX rates.
            </div>
          </div>

        </div>

        {/* AWS Discovered Resource Breakdown & Priority Matrix */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* Inventory Breakdown */}
          <div className="bg-slate-800/80 p-6 rounded-xl border border-slate-700/80 lg:col-span-2 shadow-lg">
            <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
              <Layers size={18} className="text-blue-400" /> Discovered Resource Distribution
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60">
                <span className="text-[11px] text-slate-400 block">EC2 Instances</span>
                <span className="text-xl font-bold text-white">{typeCounts['server'] || 0}</span>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60">
                <span className="text-[11px] text-slate-400 block">RDS Databases</span>
                <span className="text-xl font-bold text-white">{typeCounts['database'] || 0}</span>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60">
                <span className="text-[11px] text-slate-400 block">VPC Networks</span>
                <span className="text-xl font-bold text-white">{typeCounts['vpc'] || 0}</span>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60">
                <span className="text-[11px] text-slate-400 block">Subnets</span>
                <span className="text-xl font-bold text-white">{typeCounts['subnet'] || 0}</span>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60">
                <span className="text-[11px] text-slate-400 block">Security Groups</span>
                <span className="text-xl font-bold text-white">{typeCounts['security_group'] || 0}</span>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60">
                <span className="text-[11px] text-slate-400 block">Load Balancers</span>
                <span className="text-xl font-bold text-white">{typeCounts['load_balancer'] || 0}</span>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60">
                <span className="text-[11px] text-slate-400 block">S3 Buckets</span>
                <span className="text-xl font-bold text-white">{typeCounts['storage'] || 0}</span>
              </div>
              <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60">
                <span className="text-[11px] text-slate-400 block">Applications</span>
                <span className="text-xl font-bold text-white">{typeCounts['application'] || 0}</span>
              </div>
            </div>

            <div className="mt-5 p-3 bg-slate-900/40 rounded-lg border border-slate-700/60 flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-2">
                <Radio size={14} className="text-emerald-400 animate-pulse" />
                Deterministic Topology Mapping: Target Group Routes, Ingress Security Rules, IAM Policies
              </span>
              <span className="font-mono text-[11px] text-slate-300">Zero ML Guessing</span>
            </div>
          </div>

          {/* SRE Criticality Distribution */}
          <div className="bg-slate-800/80 p-6 rounded-xl border border-slate-700/80 shadow-lg flex flex-col justify-between">
            <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
              <ShieldCheck size={18} className="text-emerald-400" /> Criticality Tiers
            </h3>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-red-400 font-semibold">Tier 1 • Critical</span>
                  <span className="font-mono text-white font-bold">{criticalCount}</span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-1.5">
                  <div className="bg-red-500 h-1.5 rounded-full" style={{ width: `${components.length > 0 ? (criticalCount / components.length) * 100 : 0}%` }}></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-amber-400 font-semibold">Tier 2 • High</span>
                  <span className="font-mono text-white font-bold">{highCount}</span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-1.5">
                  <div className="bg-amber-500 h-1.5 rounded-full" style={{ width: `${components.length > 0 ? (highCount / components.length) * 100 : 0}%` }}></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-blue-400 font-semibold">Tier 3 • Medium</span>
                  <span className="font-mono text-white font-bold">{mediumCount}</span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-1.5">
                  <div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${components.length > 0 ? (mediumCount / components.length) * 100 : 0}%` }}></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-slate-400 font-semibold">Tier 4 • Low</span>
                  <span className="font-mono text-white font-bold">{lowCount}</span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-1.5">
                  <div className="bg-slate-400 h-1.5 rounded-full" style={{ width: `${components.length > 0 ? (lowCount / components.length) * 100 : 0}%` }}></div>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-700/60 text-[11px] text-slate-400">
              Criticality governs the deterministic risk engine weight in change simulations.
            </div>
          </div>

        </div>

        {/* 4-Stage Architectural Pipeline Verification */}
        <div className="bg-slate-800/60 p-5 rounded-xl border border-slate-700/60">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Digital Twin Decision Intelligence Pipeline
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-700/40">
              <span className="text-[10px] text-blue-400 font-bold block uppercase tracking-wider mb-1">1. ACTUAL AWS STATE</span>
              <span className="text-xs text-white font-semibold flex items-center gap-1.5">
                <Cloud size={14} className="text-blue-400" /> Boto3 & CloudWatch
              </span>
              <p className="text-[11px] text-slate-400 mt-1">Resource metadata, real VPC topology, and batched metric queries.</p>
            </div>

            <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-700/40">
              <span className="text-[10px] text-cyan-400 font-bold block uppercase tracking-wider mb-1">2. TOPOLOGY GRAPH</span>
              <span className="text-xs text-white font-semibold flex items-center gap-1.5">
                <Network size={14} className="text-cyan-400" /> Deterministic Edges
              </span>
              <p className="text-[11px] text-slate-400 mt-1">Target group health routing, security group rules, and IAM policies.</p>
            </div>

            {isManual ? (
              <>
                <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-700/40">
                  <span className="text-[10px] text-cyan-400 font-bold block uppercase tracking-wider mb-1">3. GRAPH PERSISTENCE</span>
                  <span className="text-xs text-white font-semibold flex items-center gap-1.5">
                    <Layers size={14} className="text-cyan-400" /> Digital Twin State
                  </span>
                  <p className="text-[11px] text-slate-400 mt-1">Manual node configurations and dependency graph normalization.</p>
                </div>

                <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-700/40">
                  <span className="text-[10px] text-emerald-400 font-bold block uppercase tracking-wider mb-1">4. DETERMINISTIC SIMULATION</span>
                  <span className="text-xs text-white font-semibold flex items-center gap-1.5">
                    <ShieldCheck size={14} className="text-emerald-400" /> Impact & Blast Radius
                  </span>
                  <p className="text-[11px] text-slate-400 mt-1">Cascading risk score, recovery downtime, and INR budget evaluation.</p>
                </div>
              </>
            ) : (
              <>
                <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-700/40">
                  <span className="text-[10px] text-purple-400 font-bold block uppercase tracking-wider mb-1">3. ML RECOMMENDATION</span>
                  <span className="text-xs text-white font-semibold flex items-center gap-1.5">
                    <Cpu size={14} className="text-purple-400" /> Random Forest Engine
                  </span>
                  <p className="text-[11px] text-slate-400 mt-1">Operational actions, class confidence, and telemetry driver extraction.</p>
                </div>

                <div className="p-3 bg-slate-900/60 rounded-lg border border-slate-700/40">
                  <span className="text-[10px] text-emerald-400 font-bold block uppercase tracking-wider mb-1">4. SIMULATION & EXPLANATION</span>
                  <span className="text-xs text-white font-semibold flex items-center gap-1.5">
                    <Sparkles size={14} className="text-emerald-400" /> Grounded Gemini
                  </span>
                  <p className="text-[11px] text-slate-400 mt-1">Deterministic risk/downtime/cost simulation with AI explanation.</p>
                </div>
              </>
            )}
          </div>
        </div>

      </div>
    </div>
  );
};

