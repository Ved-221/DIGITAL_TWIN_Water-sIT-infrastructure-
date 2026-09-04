import React from 'react';
import { 
  Cloud, Server, Key, ArrowRight, ShieldCheck, 
  Search, CheckCircle2, AlertCircle, RefreshCw, Layers, Sparkles, Plus 
} from 'lucide-react';

interface EmptyStateProps {
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
  loading: boolean;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  mode,
  discoveryStatus,
  accountId,
  region = 'us-east-1',
  arn,
  onOpenConnect,
  onDiscover,
  onStartManual,
  onSelectAWS,
  onSelectManual,
  onAddResource,
  onOpenBuildTwin,
  loading
}) => {
  // 1. Loading / Discovering in progress
  if (loading || discoveryStatus === 'discovering') {
    return (
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-900">
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
              <span>5. Batching CloudWatch Telemetry Ingestion</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 2. AWS Environment (Awaiting Discovery or Credentials)
  if (mode === 'live' && discoveryStatus === 'idle') {
    const hasAccount = Boolean(accountId && accountId !== 'Validated');
    return (
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-900">
        <div className="max-w-lg w-full text-center space-y-6 bg-slate-800/90 border border-slate-700/80 p-8 rounded-2xl shadow-2xl backdrop-blur">
          <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto text-emerald-400 shadow-inner">
            {hasAccount ? <CheckCircle2 size={32} /> : <Key size={30} />}
          </div>

          <div className="space-y-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              {hasAccount ? 'AWS Connected ✓' : 'AWS Environment'}
            </div>
            <h2 className="text-2xl font-extrabold text-white">
              {hasAccount ? 'Identity Validated via STS' : 'Connect AWS Infrastructure'}
            </h2>
            {hasAccount ? (
              <div className="text-xs text-slate-300 bg-slate-900/60 p-3 rounded-lg border border-slate-700/60 font-mono space-y-1">
                <div>Account: <span className="text-emerald-400 font-bold">{accountId}</span></div>
                <div>Region: <span className="text-cyan-400 font-bold">{region}</span></div>
                {arn && <div className="text-slate-400 text-[11px] truncate">Role: {arn}</div>}
              </div>
            ) : (
              <p className="text-xs text-slate-400 max-w-sm mx-auto pt-1">
                Authenticate your AWS credentials via STS to discover your actual VPCs, Subnets, EC2, RDS, and ALBs.
              </p>
            )}
            <p className="text-xs text-slate-400 max-w-sm mx-auto pt-1">
              {hasAccount
                ? 'Ready to construct your Digital Twin. Click below to discover actual AWS resources and derive relationships deterministically.'
                : 'Click below to connect your AWS credentials.'}
            </p>
          </div>

          <div className="space-y-3 pt-2">
            {hasAccount ? (
              <button
                onClick={onDiscover}
                className="w-full py-3.5 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 rounded-xl font-bold text-sm text-white shadow-lg shadow-blue-900/30 flex items-center justify-center gap-2 transition group"
              >
                <Search size={18} className="group-hover:scale-110 transition-transform" />
                <span>Discover Real Infrastructure</span>
              </button>
            ) : (
              <button
                onClick={onOpenConnect}
                className="w-full py-3.5 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 rounded-xl font-bold text-sm text-white shadow-lg shadow-blue-900/30 flex items-center justify-center gap-2 transition group"
              >
                <Key size={18} className="group-hover:scale-110 transition-transform" />
                <span>Connect AWS Credentials</span>
              </button>
            )}
            <p className="text-[11px] text-slate-500">
              Reads live EC2, RDS, VPCs, ALBs, S3, Security Groups & CloudWatch
            </p>
          </div>
        </div>
      </div>
    );
  }

  // 3. Manual Mode with 0 Resources: Empty Builder Canvas
  if (mode === 'manual') {
    return (
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-900">
        <div className="max-w-lg w-full text-center space-y-6 bg-slate-800/90 border border-slate-700/80 p-8 rounded-2xl shadow-2xl backdrop-blur">
          <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center mx-auto text-cyan-400 shadow-inner">
            <Server size={30} />
          </div>

          <div className="space-y-2">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-800">
              <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
              Manual Environment
            </div>
            <h2 className="text-2xl font-extrabold text-white">No Infrastructure Created Yet</h2>
            <p className="text-xs text-slate-400 max-w-sm mx-auto pt-1">
              Create your custom infrastructure topology from scratch. Add servers, databases, load balancers, and VPCs, then connect their dependencies to run digital twin simulations and ML analysis.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              onClick={onAddResource || onStartManual}
              className="flex-1 py-3.5 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 rounded-xl font-bold text-sm text-white shadow-lg shadow-blue-900/30 flex items-center justify-center gap-2 transition group"
            >
              <Plus size={18} />
              <span>+ Add Resource</span>
            </button>
            {onOpenBuildTwin && (
              <button
                onClick={onOpenBuildTwin}
                className="flex-1 py-3.5 bg-slate-850 hover:bg-slate-800 text-cyan-300 hover:text-white border border-slate-700/80 rounded-xl font-bold text-sm shadow-lg transition flex items-center justify-center gap-2"
              >
                <Sparkles size={18} className="text-cyan-400" />
                <span>Describe System (NLP)</span>
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 4. Discovered but Empty (AWS returned 0 resources)
  if (mode === 'live' && discoveryStatus === 'empty') {
    return (
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-900">
        <div className="max-w-md w-full text-center space-y-6 bg-slate-800/90 border border-slate-700/80 p-8 rounded-2xl shadow-2xl backdrop-blur">
          <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center mx-auto text-amber-400 shadow-inner">
            <AlertCircle size={30} />
          </div>

          <div className="space-y-2">
            <h2 className="text-xl font-bold text-white">No Resources Found in {region}</h2>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Verify that EC2 instances, RDS databases, VPCs, ALBs, or S3 buckets are actively provisioned in this region.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              onClick={onDiscover}
              className="flex-1 py-3 bg-blue-600 hover:bg-blue-500 rounded-xl font-semibold text-xs text-white transition flex items-center justify-center gap-2 shadow"
            >
              <RefreshCw size={15} />
              <span>Re-scan {region}</span>
            </button>
            <button
              onClick={onOpenConnect}
              className="flex-1 py-3 bg-slate-700 hover:bg-slate-600 rounded-xl font-semibold text-xs text-slate-200 border border-slate-600 transition flex items-center justify-center gap-2"
            >
              <Key size={15} className="text-amber-400" />
              <span>Change AWS Region</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 5. Default Fresh Startup / Environment Selection Screen (Unconnected)
  return (
    <div className="flex-1 flex items-center justify-center p-8 bg-slate-900">
      <div className="max-w-2xl w-full text-center space-y-7 bg-slate-800/90 border border-slate-700/80 p-10 rounded-2xl shadow-2xl backdrop-blur">
        
        {/* Brand Icon */}
        <div className="w-16 h-16 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center mx-auto text-blue-400 shadow-inner">
          <Cloud size={32} />
        </div>

        {/* Title and Subtitle */}
        <div className="space-y-2">
          <h1 className="text-3xl font-extrabold text-white tracking-tight">InfraTwin</h1>
          <p className="text-base text-slate-300 font-medium">
            Choose how you want to create your Digital Twin
          </p>
        </div>

        {/* Three Options */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 text-left">
          {/* Option 1: AWS Environment */}
          <div className="p-5 rounded-2xl border border-blue-600/40 bg-slate-900/60 hover:border-blue-500/80 transition shadow-lg flex flex-col justify-between group">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
                <Key size={20} />
              </div>
              <h2 className="text-base font-bold text-white">AWS Environment</h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                Connect your AWS account to discover real VPCs, EC2, RDS, and CloudWatch metrics.
              </p>
            </div>
            <div className="pt-5">
              <button
                onClick={onSelectAWS || onOpenConnect}
                disabled={loading}
                className="w-full py-2.5 px-3 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold text-xs text-white shadow-md shadow-blue-600/20 transition flex items-center justify-center gap-2 group-hover:shadow-blue-500/30"
              >
                <span>Select AWS</span>
                <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          </div>

          {/* Option 2: Manual Environment */}
          <div className="p-5 rounded-2xl border border-cyan-600/40 bg-slate-900/60 hover:border-cyan-500/80 transition shadow-lg flex flex-col justify-between group">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
                <Server size={20} />
              </div>
              <h2 className="text-base font-bold text-white">Manual Builder</h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                Create custom infrastructure and connect dependencies node-by-node on a canvas.
              </p>
            </div>
            <div className="pt-5">
              <button
                onClick={onSelectManual || onStartManual}
                disabled={loading}
                className="w-full py-2.5 px-3 bg-cyan-600 hover:bg-cyan-500 rounded-xl font-bold text-xs text-white shadow-md shadow-cyan-600/20 transition flex items-center justify-center gap-2 group-hover:shadow-cyan-500/30"
              >
                <span>Select Manual</span>
                <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          </div>

          {/* Option 3: Describe & Build Twin */}
          <div className="p-5 rounded-2xl border border-indigo-600/40 bg-slate-900/60 hover:border-indigo-500/80 transition shadow-lg flex flex-col justify-between group">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                <Sparkles size={20} />
              </div>
              <h2 className="text-base font-bold text-white">Describe & Build</h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                Describe your system in English or import JSON to generate a domain-agnostic Twin.
              </p>
            </div>
            <div className="pt-5">
              <button
                onClick={onOpenBuildTwin}
                disabled={loading}
                className="w-full py-2.5 px-3 bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 rounded-xl font-bold text-xs text-white shadow-md shadow-indigo-600/20 transition flex items-center justify-center gap-2 group-hover:shadow-indigo-500/30"
              >
                <span>Build Your Twin</span>
                <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          </div>
        </div>

        {/* Clean Footer */}
        <div className="pt-2 flex flex-wrap items-center justify-center gap-4 text-xs text-slate-500 border-t border-slate-700/60">
          <span className="flex items-center gap-1.5"><Layers size={13}/> Unified Digital Twin Pipeline</span>
          <span>•</span>
          <span className="flex items-center gap-1.5"><ShieldCheck size={13}/> Deterministic Graph</span>
          <span>•</span>
          <span className="flex items-center gap-1.5"><Sparkles size={13}/> Grounded Gemini</span>
        </div>

      </div>
    </div>
  );
};
