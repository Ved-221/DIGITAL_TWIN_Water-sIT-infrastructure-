import React from 'react';
import {
  Cloud, Server, Key, ArrowRight, ShieldCheck,
  Search, CheckCircle2, AlertCircle, RefreshCw, Layers, Sparkles, Plus,
  FileCode, Zap
} from 'lucide-react';

export const QUICK_START_TEMPLATES = [
  {
    id: 'cloud_web',
    label: 'Cloud Web Architecture',
    domain: 'cloud',
    badge: '3-Tier Web',
    badgeColor: 'text-blue-400 bg-blue-950/80 border-blue-800',
    description: 'Application Load Balancer distributing traffic across two web servers, connected to PostgreSQL and S3 storage.',
    text: 'Two application servers behind an Application Load Balancer. Both application servers connect to a PostgreSQL database. PostgreSQL connects to an S3 backup storage.',
  },
  {
    id: 'water_scada',
    label: 'Water Infrastructure SCADA',
    domain: 'water',
    badge: 'SCADA / IoT',
    badgeColor: 'text-cyan-400 bg-cyan-950/80 border-cyan-800',
    description: 'SCADA workstation connected to high service pump station PLC, flow meter sensor, and central operational DB.',
    text: 'SCADA monitoring workstation connects to high service pump station PLC controller. The PLC controller receives signals from flow meter sensor and pressure valve. SCADA workstation connects to central operational database.',
  },
  {
    id: 'decoupled_queue',
    label: 'Decoupled Queue & Cache',
    domain: 'cloud',
    badge: 'Microservices',
    badgeColor: 'text-purple-400 bg-purple-950/80 border-purple-800',
    description: 'API Gateway decoupled by an asynchronous message queue buffer feeding two worker servers and a Redis cache.',
    text: 'API Gateway connects to Message Queue Buffer. Message Queue Buffer distributes work to two Worker Servers. Worker Servers connect to Redis Cache and Database.',
  },
  {
    id: 'ha_database',
    label: 'Enterprise High Availability DB',
    domain: 'cloud',
    badge: 'Multi-AZ HA',
    badgeColor: 'text-emerald-400 bg-emerald-950/80 border-emerald-800',
    description: 'Primary Database replicating synchronously to Multi-AZ Standby and offloading queries to a Read Replica.',
    text: 'Application Server connects to Primary Database. Primary Database replicates to Multi-AZ Standby Replica. Primary Database replicates to Dedicated Read Replica.',
  },
];

export interface EmptyStateProps {
  mode: 'unconnected' | 'live' | 'demo' | 'manual';
  discoveryStatus: 'idle' | 'discovering' | 'completed' | 'empty' | 'failed';
  accountId?: string;
  region?: string;
  arn?: string;
  onOpenConnect: () => void;
  onDiscover: () => void;
  onStartManual: () => void;
  onSelectAWS?: () => void;
  onSelectManual?: () => void;
  onAddResource?: () => void;
  onOpenBuildTwin?: () => void;
  onOpenDescribeBuild?: () => void;
  onOpenImportJson?: () => void;
  onLoadTemplate?: (template: { label: string; text: string; domain: string }) => void;
  loading: boolean;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  mode,
  discoveryStatus,
  accountId,
  region = 'ap-south-1',
  arn,
  onOpenConnect,
  onDiscover,
  onStartManual,
  onSelectAWS,
  onSelectManual,
  onAddResource,
  onOpenBuildTwin,
  onOpenDescribeBuild,
  onOpenImportJson,
  onLoadTemplate,
  loading
}) => {
  // 1. Loading / Discovering in progress
  if (loading || discoveryStatus === 'discovering') {
    return (
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-900 overflow-y-auto">
        <div className="max-w-md w-full text-center space-y-6 bg-slate-800/90 border border-slate-700/80 p-8 rounded-2xl shadow-2xl backdrop-blur">
          <div className="w-16 h-16 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center mx-auto text-blue-400 shadow-inner">
            <RefreshCw size={30} className="animate-spin text-blue-400" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-bold text-white">Discovering AWS Infrastructure</h2>
            <p className="text-xs text-slate-400">
              Querying live AWS APIs in <span className="font-mono text-blue-300 font-semibold">{region}</span>...
            </p>
          </div>
          <div className="space-y-2 text-left bg-slate-900/60 p-4 rounded-xl border border-slate-700/60 text-xs">
            <div className="flex items-center gap-2 text-slate-300">
              <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
              <span>1. Describing VPCs, Subnets & Security Groups</span>
            </div>
            <div className="flex items-center gap-2 text-slate-300">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
              <span>2. Describing EC2 Compute & RDS Databases</span>
            </div>
            <div className="flex items-center gap-2 text-slate-300">
              <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></span>
              <span>3. Describing ALBs, Target Groups & S3 Buckets</span>
            </div>
            <div className="flex items-center gap-2 text-slate-300">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>4. Building Deterministic Dependency Graph</span>
            </div>
            <div className="flex items-center gap-2 text-slate-300">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
              <span>5. Ingesting CloudWatch Telemetry</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const hasAWSAccount = Boolean(accountId && accountId !== 'Validated');

  return (
    <div className="flex-1 flex flex-col items-center justify-start p-6 sm:p-10 bg-slate-900 overflow-y-auto">
      <div className="max-w-5xl w-full space-y-7 my-auto py-4">

        {/* Top Status Banner: AWS Connected via STS */}
        {mode === 'live' && hasAWSAccount && (
          <div className="bg-slate-800/90 border border-emerald-500/40 p-4 sm:p-5 rounded-2xl shadow-xl backdrop-blur flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-left">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
                <CheckCircle2 size={22} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-sm">AWS Connected via STS</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                    {region}
                  </span>
                </div>
                <div className="text-xs text-slate-400 font-mono mt-0.5">
                  Account: <span className="text-emerald-300 font-semibold">{accountId}</span>
                  {arn && <span className="hidden md:inline text-slate-500"> • {arn}</span>}
                </div>
              </div>
            </div>
            <button
              onClick={onDiscover}
              disabled={loading}
              className="w-full sm:w-auto px-5 py-2.5 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 rounded-xl font-bold text-xs text-white shadow-md shadow-blue-900/30 flex items-center justify-center gap-2 transition shrink-0"
            >
              <Search size={15} />
              <span>Discover Real Infrastructure</span>
            </button>
          </div>
        )}

        {/* Top Status Banner: Manual Mode Active */}
        {mode === 'manual' && (
          <div className="bg-slate-800/90 border border-cyan-500/40 p-4 sm:p-5 rounded-2xl shadow-xl backdrop-blur flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-left">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shrink-0">
                <Server size={22} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-sm">Manual Environment Active</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">
                    Custom Canvas
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  Build custom infrastructure node-by-node, use NLP description, or load a template below.
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <button
                onClick={onAddResource || onStartManual}
                className="flex-1 sm:flex-initial px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 rounded-xl font-bold text-xs text-white shadow-md shadow-cyan-900/30 flex items-center justify-center gap-1.5 transition"
              >
                <Plus size={15} />
                <span>Add Resource</span>
              </button>
              {onOpenBuildTwin && (
                <button
                  onClick={onOpenBuildTwin}
                  className="flex-1 sm:flex-initial px-4 py-2.5 bg-slate-700 hover:bg-slate-600 text-cyan-300 hover:text-white border border-slate-600 rounded-xl font-bold text-xs transition flex items-center justify-center gap-1.5"
                >
                  <Sparkles size={14} />
                  <span>Describe (NLP)</span>
                </button>
              )}
            </div>
          </div>
        )}

        {/* Top Status Banner: AWS Empty Scan */}
        {mode === 'live' && discoveryStatus === 'empty' && (
          <div className="bg-slate-800/90 border border-amber-500/40 p-4 rounded-2xl shadow-xl backdrop-blur flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-left">
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
                <AlertCircle size={22} />
              </div>
              <div>
                <span className="font-bold text-white text-sm">No Resources Found in {region}</span>
                <p className="text-xs text-slate-400">Verify that EC2, RDS, VPCs, or ALBs are provisioned in this region.</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={onDiscover}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-xl font-semibold text-xs text-white transition flex items-center gap-1.5 shadow"
              >
                <RefreshCw size={14} />
                <span>Re-scan</span>
              </button>
              <button
                onClick={onOpenConnect}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-xl font-semibold text-xs text-slate-200 border border-slate-600 transition flex items-center gap-1.5"
              >
                <Key size={14} className="text-amber-400" />
                <span>Change Region</span>
              </button>
            </div>
          </div>
        )}

        {/* Main Section Header */}
        <div className="text-center space-y-2">
          <div className="w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center mx-auto text-blue-400 shadow-inner">
            <Cloud size={28} />
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Choose How to Build Your Digital Twin
          </h1>
          <p className="text-sm text-slate-400 max-w-lg mx-auto">
            Select one of the four primary options below to connect live cloud services, construct manually, describe in plain English, or import architecture.
          </p>
        </div>

        {/* The Four Primary Options Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-left">
          
          {/* Option A: Connect AWS */}
          <div className="p-5 rounded-2xl border border-blue-600/40 bg-slate-800/80 hover:border-blue-500/80 hover:bg-slate-800 transition shadow-lg flex flex-col justify-between group">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
                <Key size={20} />
              </div>
              <div>
                <span className="text-[10px] font-mono text-blue-400 font-bold uppercase tracking-wider block">Option A</span>
                <h2 className="text-base font-bold text-white">Connect AWS</h2>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Connect live AWS credentials to automatically discover VPCs, EC2, RDS, and CloudWatch metrics.
              </p>
            </div>
            <div className="pt-5">
              <button
                onClick={onSelectAWS || onOpenConnect}
                disabled={loading}
                className="w-full py-2.5 px-3 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold text-xs text-white shadow-md shadow-blue-600/20 transition flex items-center justify-center gap-2 group-hover:shadow-blue-500/30"
              >
                <span>Connect AWS</span>
                <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          </div>

          {/* Option B: Build Manually */}
          <div className="p-5 rounded-2xl border border-cyan-600/40 bg-slate-800/80 hover:border-cyan-500/80 hover:bg-slate-800 transition shadow-lg flex flex-col justify-between group">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                <Server size={20} />
              </div>
              <div>
                <span className="text-[10px] font-mono text-cyan-400 font-bold uppercase tracking-wider block">Option B</span>
                <h2 className="text-base font-bold text-white">Build Manually</h2>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Create custom infrastructure from scratch on a blank canvas. Add custom nodes, servers, and links.
              </p>
            </div>
            <div className="pt-5">
              <button
                onClick={onSelectManual || onStartManual}
                disabled={loading}
                className="w-full py-2.5 px-3 bg-cyan-600 hover:bg-cyan-500 rounded-xl font-bold text-xs text-white shadow-md shadow-cyan-600/20 transition flex items-center justify-center gap-2 group-hover:shadow-cyan-500/30"
              >
                <span>Build Manually</span>
                <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          </div>

          {/* Option C: Describe & Build */}
          <div className="p-5 rounded-2xl border border-indigo-600/40 bg-slate-800/80 hover:border-indigo-500/80 hover:bg-slate-800 transition shadow-lg flex flex-col justify-between group">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                <Sparkles size={20} />
              </div>
              <div>
                <span className="text-[10px] font-mono text-indigo-400 font-bold uppercase tracking-wider block">Option C</span>
                <h2 className="text-base font-bold text-white">Describe & Build</h2>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Describe your system in plain English. The AI engine parses components and builds dependencies automatically.
              </p>
            </div>
            <div className="pt-5">
              <button
                onClick={onOpenDescribeBuild || onOpenBuildTwin}
                disabled={loading}
                className="w-full py-2.5 px-3 bg-indigo-600 hover:bg-indigo-500 rounded-xl font-bold text-xs text-white shadow-md shadow-indigo-600/20 transition flex items-center justify-center gap-2 group-hover:shadow-indigo-500/30"
              >
                <span>Describe & Build</span>
                <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          </div>

          {/* Option D: Import JSON */}
          <div className="p-5 rounded-2xl border border-emerald-600/40 bg-slate-800/80 hover:border-emerald-500/80 hover:bg-slate-800 transition shadow-lg flex flex-col justify-between group">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <FileCode size={20} />
              </div>
              <div>
                <span className="text-[10px] font-mono text-emerald-400 font-bold uppercase tracking-wider block">Option D</span>
                <h2 className="text-base font-bold text-white">Import JSON</h2>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Import a structured JSON file containing components, relationships, and metadata directly into the model.
              </p>
            </div>
            <div className="pt-5">
              <button
                onClick={onOpenImportJson || onOpenBuildTwin}
                disabled={loading}
                className="w-full py-2.5 px-3 bg-emerald-600 hover:bg-emerald-500 rounded-xl font-bold text-xs text-white shadow-md shadow-emerald-600/20 transition flex items-center justify-center gap-2 group-hover:shadow-emerald-500/30"
              >
                <span>Import JSON</span>
                <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          </div>

        </div>

        {/* Extra Options: Quick-Start Architecture Templates */}
        <div className="space-y-4 pt-2">
          <div className="flex items-center justify-between border-b border-slate-700/80 pb-2.5">
            <div className="flex items-center gap-2">
              <Zap size={16} className="text-amber-400" />
              <h3 className="text-sm font-bold text-white tracking-tight">Extra: 1-Click Architecture Templates</h3>
            </div>
            <span className="text-[11px] text-slate-400">Instant Digital Twin setup</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-left">
            {QUICK_START_TEMPLATES.map((tmpl) => (
              <div 
                key={tmpl.id}
                className="p-4 rounded-xl border border-slate-700/80 bg-slate-800/60 hover:bg-slate-800 hover:border-slate-600 transition flex flex-col justify-between space-y-3 shadow"
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className={`px-2 py-0.5 rounded text-[9px] font-bold border ${tmpl.badgeColor}`}>
                      {tmpl.badge}
                    </span>
                  </div>
                  <h4 className="text-xs font-bold text-white">{tmpl.label}</h4>
                  <p className="text-[11px] text-slate-400 leading-relaxed line-clamp-3">
                    {tmpl.description}
                  </p>
                </div>
                <button
                  onClick={() => onLoadTemplate && onLoadTemplate(tmpl)}
                  disabled={loading}
                  className="w-full py-2 px-2.5 bg-slate-700/80 hover:bg-slate-600 text-cyan-300 hover:text-white rounded-lg text-xs font-semibold transition flex items-center justify-center gap-1.5 border border-slate-600/80"
                >
                  <Sparkles size={12} className="text-cyan-400" />
                  <span>Load Template</span>
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Clean Footer */}
        <div className="pt-4 flex flex-wrap items-center justify-center gap-4 text-xs text-slate-500 border-t border-slate-800">
          <span className="flex items-center gap-1.5"><Layers size={13} /> Unified Digital Twin Pipeline</span>
          <span>•</span>
          <span className="flex items-center gap-1.5"><ShieldCheck size={13} /> Deterministic NetworkX Graph</span>
          <span>•</span>
          <span className="flex items-center gap-1.5"><Sparkles size={13} /> ML & Multi-Agent Layer</span>
        </div>

      </div>
    </div>
  );
};
