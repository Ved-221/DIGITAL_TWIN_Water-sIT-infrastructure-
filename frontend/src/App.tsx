import { useEffect, useState, useCallback } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  addEdge,
  Handle,
  Position,
  Panel
} from '@xyflow/react';
import type { Node, Edge, Connection } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import classNames from 'classnames';
import { 
  AlertTriangle, LayoutDashboard, Share2, Server, 
  RefreshCw, Key, XCircle, Search, RotateCcw, Plus, Link, Trash2
} from 'lucide-react';

import { AWSConnectModal } from './components/AWSConnectModal';
import { DashboardView } from './components/DashboardView';
import { EmptyState } from './components/EmptyState';
import { InspectorDrawer } from './components/InspectorDrawer';
import { ManualResourceModal } from './components/ManualResourceModal';
import { ManualDependencyModal } from './components/ManualDependencyModal';
import { calculateTopologyLayout } from './utils/topologyLayout';
import { formatINR, getRegionDisplayName } from './utils/localization';

const API_BASE = 'http://localhost:8000/api';

const iconMap: Record<string, string> = {
  application: '💻',
  server: '🖥️',
  database: '🗄️',
  network: '🌐',
  cloud_resource: '☁️',
  storage: '💾',
  api: '🔌',
  identity: '🔑',
  load_balancer: '⚖️',
  vpc: '🏢',
  subnet: '📦',
  security_group: '🛡️',
};

// Custom Node Component with Handles for Interactive Connection
const CustomNode = ({ data, selected }: { data: any; selected: boolean }) => {
  const isBlastRadius = data.blastRadius;
  const isProposed = data.discovery_source === 'proposed' || data.metadata_col?.is_proposed;
  const isAWS = (data.discovery_source === 'aws_api' || data.arn != null) && !isProposed;
  const isManual = data.discovery_source === 'manual' && !isProposed;

  return (
    <div
      className={classNames(
        'px-4 py-3 rounded-xl border transition-all duration-200 shadow-lg cursor-pointer min-w-[180px]',
        isBlastRadius
          ? 'bg-red-950/80 border-red-500 shadow-red-500/30 scale-105 ring-2 ring-red-500 animate-pulse'
          : selected
          ? 'bg-slate-800 border-blue-400 shadow-blue-500/20 ring-2 ring-blue-500/50'
          : isProposed
          ? 'bg-purple-950/70 border-purple-500/80 border-dashed hover:border-purple-400 hover:bg-purple-900/60 shadow-purple-950/50 ring-1 ring-purple-500/40'
          : 'bg-slate-800/90 border-slate-700 hover:border-slate-500 hover:bg-slate-800'
      )}
    >
      <Handle type="target" position={Position.Top} className="w-3 h-3 !bg-blue-400" />
      
      <div className="flex items-center gap-2.5">
        <span className="text-xl shrink-0">{iconMap[data.type] || '📦'}</span>
        <div className="overflow-hidden">
          <div className="font-bold text-white text-xs truncate max-w-[140px]">
            {data.name || data.id}
          </div>
          <div className="text-[10px] text-slate-400 capitalize truncate">
            {data.type?.replace('_', ' ')} • {data.criticality || 'medium'}
          </div>
        </div>
      </div>

      <div className="mt-2 pt-1.5 border-t border-slate-700/60 flex items-center justify-between text-[10px]">
        <span className="font-mono text-slate-400">
          {(isManual || isProposed) ? `${formatINR(data.cost_per_month ?? 0)}/mo` : `$${data.cost_per_month ?? 0}/mo`}
        </span>
        <span className={classNames(
          "font-mono px-1.5 py-0.5 rounded text-[9px] font-semibold",
          isProposed ? "bg-purple-950 text-purple-300 border border-purple-700" :
          isAWS ? "bg-emerald-950 text-emerald-400 border border-emerald-800" :
          isManual ? "bg-cyan-950 text-cyan-400 border border-cyan-800" :
          "bg-slate-700 text-slate-300"
        )}>
          {isProposed ? 'PROPOSED' : isAWS ? 'AWS' : isManual ? 'MANUAL' : 'SEED'}
        </span>
      </div>

      <Handle type="source" position={Position.Bottom} className="w-3 h-3 !bg-purple-400" />
    </div>
  );
};

const nodeTypes = { custom: CustomNode };

interface TwinState {
  mode: 'unconnected' | 'live' | 'demo' | 'manual';
  authenticated: boolean;
  account_id?: string;
  arn?: string;
  region?: string;
  discovery_status: 'idle' | 'discovering' | 'completed' | 'empty' | 'failed';
  discovery_summary?: any;
  last_sync?: string;
  error?: string;
  total_components: number;
  total_dependencies: number;
}

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [simResult, setSimResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [activeTab, setActiveTab] = useState<'graph' | 'dashboard'>('graph');
  
  const [twinState, setTwinState] = useState<TwinState | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [rawComponents, setRawComponents] = useState<any[]>([]);
  const [rawDependencies, setRawDependencies] = useState<any[]>([]);
  const [metricsMap, setMetricsMap] = useState<Record<string, any>>({});
  const [recommendations, setRecommendations] = useState<Record<string, any>>({});
  const [costReport, setCostReport] = useState<any>(null);
  const [healthReport, setHealthReport] = useState<any>(null);
  
  // Environment selection state: null = Startup Selection Screen, 'aws' = AWS Flow, 'manual' = Manual Builder
  const [selectedEnv, setSelectedEnv] = useState<'aws' | 'manual' | null>(() => {
    const saved = sessionStorage.getItem('infratwin_env');
    if (saved === 'aws' || saved === 'manual') return saved;
    return null;
  });

  // Modals state
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [isResourceModalOpen, setIsResourceModalOpen] = useState(false);
  const [isDependencyModalOpen, setIsDependencyModalOpen] = useState(false);
  const [editResource, setEditResource] = useState<any | null>(null);
  const [pendingSourceId, setPendingSourceId] = useState<string | null>(null);
  const [pendingTargetId, setPendingTargetId] = useState<string | null>(null);
  const [hasCycle, setHasCycle] = useState(false);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      // 1. Fetch Digital Twin Environment & Discovery State
      const stateRes = await fetch(`${API_BASE}/twin/state`);
      let curState: TwinState = {
        mode: 'unconnected',
        authenticated: false,
        discovery_status: 'idle',
        total_components: 0,
        total_dependencies: 0
      };

      if (stateRes.ok) {
        curState = await stateRes.json();
        setTwinState(curState);
      }

      // If backend explicitly reset to unconnected, reset client selection as well
      if (curState.mode === 'unconnected') {
        setSelectedEnv(null);
        sessionStorage.removeItem('infratwin_env');
        setRawComponents([]);
        setRawDependencies([]);
        setNodes([]);
        setEdges([]);
        setStats(null);
        setMetricsMap({});
        setRecommendations({});
        setSelectedNode(null);
        setHasCycle(false);
        return;
      }

      // If awaiting discovery without components, clear nodes & edges
      if (curState.mode === 'live' && curState.discovery_status === 'idle') {
        setRawComponents([]);
        setRawDependencies([]);
        setNodes([]);
        setEdges([]);
        setStats(null);
        setMetricsMap({});
        setRecommendations({});
        setSelectedNode(null);
        setHasCycle(false);
        return;
      }

      // 2. Fetch Active Components, Dependencies, and Stats
      const [compsRes, depsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/twin/components`),
        fetch(`${API_BASE}/twin/dependencies`),
        fetch(`${API_BASE}/twin/stats`),
      ]);

      const comps = await compsRes.json();
      const deps = await depsRes.json();
      const st = await statsRes.json();

      setRawComponents(comps);
      setRawDependencies(deps);
      setStats(st);

      // Restore active environment from backend if resources exist
      if (comps.length > 0) {
        const restoredEnv = curState.mode === 'live' ? 'aws' : 'manual';
        setSelectedEnv(restoredEnv);
        sessionStorage.setItem('infratwin_env', restoredEnv);
      }

      // If no components exist, clear nodes
      if (comps.length === 0) {
        setNodes([]);
        setEdges([]);
        setMetricsMap({});
        setRecommendations({});
        setSelectedNode(null);
        setHasCycle(false);
        return;
      }

      // 3. Fetch Telemetry & ML Recommendations for active resources
      const mRes = await fetch(`${API_BASE}/twin/metrics/latest`);
      if (mRes.ok) {
        const mData = await mRes.json();
        const mMap: Record<string, any> = {};
        if (Array.isArray(mData)) {
          mData.forEach((item: any) => {
            mMap[item.resource_id] = item;
          });
        }
        setMetricsMap(mMap);
      }

      const rRes = await fetch(`${API_BASE}/ml/recommendations`);
      if (rRes.ok) {
        const rData = await rRes.json();
        const rMap: Record<string, any> = {};
        (rData || []).forEach((item: any) => {
          rMap[item.resource_id] = item;
        });
        setRecommendations(rMap);
      }

      // 4. Fetch Live AWS Cost & Health Operational Events (if live)
      if (curState.mode === 'live') {
        try {
          const [cRes, hRes] = await Promise.all([
            fetch(`${API_BASE}/aws/cost`),
            fetch(`${API_BASE}/aws/health-events`),
          ]);
          if (cRes.ok) setCostReport(await cRes.json());
          if (hRes.ok) setHealthReport(await hRes.json());
        } catch (e) {
          console.debug("Live Cost/Health API fetch:", e);
        }
      } else {
        setCostReport(null);
        setHealthReport(null);
      }

      // 5. Dynamically Generate Hierarchical Topology Nodes & Edges
      setNodes((currentNodes) => {
        const layoutResult = calculateTopologyLayout(comps, deps, currentNodes);
        setEdges(layoutResult.edges);
        setHasCycle(layoutResult.hasCycle);
        return layoutResult.nodes;
      });
    } catch (err: any) {
      console.error("Error fetching twin data", err);
      setErrorMessage(`Failed to communicate with Digital Twin API: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handle interactive connection between handles
  const onConnect = useCallback(
    (params: Connection) => {
      if (twinState?.mode === 'manual') {
        setPendingSourceId(params.source);
        setPendingTargetId(params.target);
        setIsDependencyModalOpen(true);
      } else {
        setEdges((eds) => addEdge(params, eds));
      }
    },
    [twinState, setEdges]
  );

  const onNodeClick = (_: any, node: Node) => {
    setSelectedNode(node.data);
    setSimResult(null);
  };

  const onEdgeClick = (_: any, edge: Edge) => {
    if (twinState?.mode === 'manual' && edge.id) {
      if (window.confirm(`Delete manual dependency "${edge.label || edge.id}"?`)) {
        handleDeleteManualDependency(edge.id);
      }
    }
  };

  // Triggers Live AWS multi-resource discovery
  const handleDiscoverInfrastructure = async () => {
    setSyncing(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${API_BASE}/aws/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          mode: 'replace', 
          use_synthetic: false, 
          region: twinState?.region || 'us-east-1' 
        })
      });
      const data = await res.json();
      if (data.success) {
        await fetchData();
      } else {
        setErrorMessage(data.message || 'AWS discovery failed. Verify IAM permissions and connectivity.');
      }
    } catch (err: any) {
      setErrorMessage(`AWS discovery network error: ${err.message}`);
    } finally {
      setSyncing(false);
    }
  };

  // Activates Manual Infrastructure Builder mode
  const handleStartManual = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${API_BASE}/manual/start`, { method: 'POST' });
      if (res.ok) {
        setSelectedNode(null);
        setSimResult(null);
        await fetchData();
      } else {
        const err = await res.json();
        setErrorMessage(err.message || 'Failed to start manual builder.');
      }
    } catch (err: any) {
      setErrorMessage(`Manual builder error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Saves or edits a manual component
  const handleSaveManualResource = async (payload: any) => {
    const isEdit = !!editResource;
    const url = isEdit ? `${API_BASE}/manual/components/${editResource.id}` : `${API_BASE}/manual/components`;
    const method = isEdit ? 'PUT' : 'POST';

    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to save manual resource.');
    }

    const savedComp = await res.json();
    await fetchData();
    if (selectedNode && isEdit && selectedNode.id === editResource.id) {
      setSelectedNode(savedComp);
    }
  };

  // Deletes a manual component
  const handleDeleteManualResource = async (componentId: string) => {
    if (!window.confirm(`Delete manual component "${componentId}" and all its connected dependencies?`)) {
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/manual/components/${componentId}`, { method: 'DELETE' });
      if (res.ok) {
        if (selectedNode?.id === componentId) {
          setSelectedNode(null);
          setSimResult(null);
        }
        await fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorMessage(err.detail || 'Failed to delete manual resource.');
      }
    } catch (e: any) {
      setErrorMessage(`Delete error: ${e.message}`);
    }
  };

  // Connects two manual components
  const handleSaveManualDependency = async (payload: any) => {
    const res = await fetch(`${API_BASE}/manual/dependencies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to connect resources.');
    }

    await fetchData();
  };

  // Deletes a manual dependency edge
  const handleDeleteManualDependency = async (depId: string) => {
    try {
      const res = await fetch(`${API_BASE}/manual/dependencies/${depId}`, { method: 'DELETE' });
      if (res.ok) {
        await fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorMessage(err.detail || 'Failed to delete dependency.');
      }
    } catch (e: any) {
      setErrorMessage(`Delete dependency error: ${e.message}`);
    }
  };

  // Clears all manual infrastructure
  const handleClearManualEstate = async () => {
    if (!window.confirm("Clear all manual infrastructure? This will remove all user-created resources and dependencies.")) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/manual/clear`, { method: 'POST' });
      if (res.ok) {
        setSelectedNode(null);
        setSimResult(null);
        await fetchData();
      }
    } catch (e: any) {
      setErrorMessage(`Clear error: ${e.message}`);
    }
  };

  // Switches to AWS Environment
  const handleSwitchToAWS = async () => {
    setSelectedEnv('aws');
    sessionStorage.setItem('infratwin_env', 'aws');
    try {
      const res = await fetch(`${API_BASE}/aws/activate`, { method: 'POST' });
      if (res.ok) {
        setSelectedNode(null);
        setSimResult(null);
        await fetchData();
        if (!twinState?.authenticated && !twinState?.account_id) {
          setIsConnectModalOpen(true);
        }
      }
    } catch (e: any) {
      setErrorMessage(`Switch to AWS error: ${e.message}`);
    }
  };

  // Switches to Manual Environment
  const handleSwitchToManual = async () => {
    setSelectedEnv('manual');
    sessionStorage.setItem('infratwin_env', 'manual');
    try {
      const res = await fetch(`${API_BASE}/manual/activate`, { method: 'POST' });
      if (res.ok) {
        setSelectedNode(null);
        setSimResult(null);
        await fetchData();
      }
    } catch (e: any) {
      setErrorMessage(`Switch to Manual error: ${e.message}`);
    }
  };

  // Select AWS from Startup Selection Screen
  const handleSelectAWS = async () => {
    await handleSwitchToAWS();
  };

  // Select Manual from Startup Selection Screen
  const handleSelectManual = async () => {
    setSelectedEnv('manual');
    sessionStorage.setItem('infratwin_env', 'manual');
    await handleStartManual();
  };

  // Resets Digital Twin back to clean environment selection screen
  const handleResetEnvironment = async () => {
    if (!window.confirm("Reset Digital Twin? This will clear all loaded resources and return to the environment selection screen.")) {
      return;
    }
    setSyncing(true);
    setErrorMessage(null);
    sessionStorage.removeItem('infratwin_env');
    setSelectedEnv(null);
    try {
      const res = await fetch(`${API_BASE}/twin/reset`, { method: 'POST' });
      if (res.ok) {
        setSelectedNode(null);
        setSimResult(null);
        await fetchData();
      }
    } catch (err: any) {
      setErrorMessage(`Reset error: ${err.message}`);
    } finally {
      setSyncing(false);
    }
  };

  // Runs deterministic simulation & grounded AI explanation
  const handleSimulate = async (useMl: boolean = false) => {
    if (!selectedNode) return;
    setSimulating(true);
    setShowSolutions(null);
    setAppliedComparison(null);
    
    try {
      const activeEnv = selectedEnv || selectedNode.source_environment || "aws";
      const res = await fetch(`${API_BASE}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_component_id: selectedNode.id,
          action: useMl ? "auto" : "migrate",
          use_ml_recommendation: useMl,
          destination_env: "cloud"
        })
      });
      
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        console.error("Simulation failed:", errJson);
        alert(`Simulation could not be completed: ${errJson.detail || 'Server error'}`);
        return;
      }
      
      const data = await res.json();
      setSimResult(data);

      // Highlight affected blast radius nodes
      const affected = new Set(data.affected_components || []);
      setNodes((nds) =>
        nds.map((node) => ({
          ...node,
          data: {
            ...node.data,
            blastRadius: affected.has(node.id) || node.id === selectedNode.id,
          },
        }))
      );
    } catch (err: any) {
      console.error("Simulation failed", err);
      setErrorMessage(`Simulation failed: ${err.message}`);
    } finally {
      setSimulating(false);
    }
  };

  const isLiveAWS = selectedEnv === 'aws';
  const isManual = selectedEnv === 'manual';
  const hasResources = rawComponents.length > 0;

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-100 antialiased font-sans overflow-hidden">
      
      {/* Top Application Header */}
      <header className="h-16 border-b border-slate-800 bg-slate-950/80 backdrop-blur px-6 flex items-center justify-between z-20 shrink-0">
        
        {/* Brand & Active Mode Badge */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center font-black text-sm shadow-md shadow-blue-500/20">
              IT
            </div>
            <h1 className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
              InfraTwin
            </h1>
          </div>

          <div className="h-4 w-[1px] bg-slate-800" />

          {/* Dynamic Mode Badge */}
          <div className="flex items-center gap-2.5">
            {isLiveAWS ? (
              <div className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800 shadow-sm">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>LIVE AWS • Account {twinState?.account_id || 'Active'} ({getRegionDisplayName(twinState?.region || 'ap-south-1')}) • {rawComponents.length} Resources</span>
              </div>
            ) : isManual ? (
              <div className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800 shadow-sm">
                <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                <span>MANUAL ENVIRONMENT • Custom Infrastructure • {rawComponents.length} Resources</span>
              </div>
            ) : null}

            {hasCycle && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950/80 text-amber-300 border border-amber-800 shadow-sm" title="A cyclic dependency was detected in this topology. The layout engine applied a fallback hierarchy.">
                <AlertTriangle size={13} className="text-amber-400" />
                <span>Cyclic Dependency</span>
              </div>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2.5">
          
          {/* Dynamic Action Buttons based on Active Environment */}
          {isLiveAWS ? (
            <>
              {!hasResources && (
                <button
                  onClick={handleDiscoverInfrastructure}
                  disabled={syncing}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 rounded-lg text-xs font-bold text-white transition shadow-sm disabled:opacity-50"
                >
                  <Search size={14} className={syncing ? "animate-spin" : ""} />
                  <span>{syncing ? 'Discovering...' : 'Discover Infrastructure'}</span>
                </button>
              )}
              {hasResources && (
                <button
                  onClick={handleDiscoverInfrastructure}
                  disabled={syncing}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs font-semibold text-white transition shadow-sm disabled:opacity-50"
                >
                  <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
                  <span>{syncing ? 'Syncing...' : 'Re-sync AWS'}</span>
                </button>
              )}
              <button
                onClick={handleSwitchToManual}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-xs font-medium text-cyan-300 border border-slate-600 transition shadow-sm"
              >
                <Server size={13} />
                <span>Switch to Manual</span>
              </button>
              <button
                onClick={() => setIsConnectModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-xs font-medium text-slate-200 border border-slate-600 transition shadow-sm"
              >
                <Key size={14} className="text-emerald-400" />
                <span>Switch Account</span>
              </button>
              <button
                onClick={handleResetEnvironment}
                disabled={syncing}
                title="Disconnect and return to clean onboarding state"
                className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-800 hover:bg-red-950 text-slate-400 hover:text-red-300 rounded-lg text-xs border border-slate-700 transition shadow-sm"
              >
                <RotateCcw size={13} />
                <span>Reset</span>
              </button>
            </>
          ) : isManual ? (
            <>
              <button
                onClick={() => { setEditResource(null); setIsResourceModalOpen(true); }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-xs font-bold text-white transition shadow-sm"
              >
                <Plus size={14} />
                <span>+ Add Resource</span>
              </button>
              {rawComponents.length >= 2 && (
                <button
                  onClick={() => { setPendingSourceId(null); setPendingTargetId(null); setIsDependencyModalOpen(true); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-500 rounded-lg text-xs font-semibold text-white transition shadow-sm"
                >
                  <Link size={14} />
                  <span>+ Connect</span>
                </button>
              )}
              <button
                onClick={handleSwitchToAWS}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-xs font-medium text-emerald-300 border border-slate-600 transition shadow-sm"
              >
                <Key size={13} />
                <span>Switch to AWS</span>
              </button>
              {rawComponents.length > 0 && (
                <button
                  onClick={handleClearManualEstate}
                  className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-800 hover:bg-red-950 text-slate-400 hover:text-red-300 rounded-lg text-xs border border-slate-700 transition shadow-sm"
                  title="Clear all manual resources"
                >
                  <Trash2 size={13} />
                  <span>Clear</span>
                </button>
              )}
              <button
                onClick={handleResetEnvironment}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg text-xs border border-slate-700 transition shadow-sm"
                title="Reset to clean onboarding"
              >
                <RotateCcw size={13} />
                <span>Reset</span>
              </button>
            </>
          ) : null}

          {/* View Mode Toggle (Only enabled when resources exist) */}
          {hasResources && (
            <div className="flex bg-slate-900 rounded-lg p-1 border border-slate-700 ml-2">
              <button
                onClick={() => setActiveTab('graph')}
                className={classNames(
                  "px-3 py-1 text-xs font-medium rounded-md transition flex items-center gap-1.5",
                  activeTab === 'graph' ? "bg-blue-600 text-white shadow" : "text-slate-400 hover:text-white"
                )}
              >
                <Share2 size={13} />
                <span>Topology</span>
              </button>
              <button
                onClick={() => setActiveTab('dashboard')}
                className={classNames(
                  "px-3 py-1 text-xs font-medium rounded-md transition flex items-center gap-1.5",
                  activeTab === 'dashboard' ? "bg-blue-600 text-white shadow" : "text-slate-400 hover:text-white"
                )}
              >
                <LayoutDashboard size={13} />
                <span>Dashboard</span>
              </button>
            </div>
          )}

        </div>
      </header>

      {/* Dismissible Error Banner */}
      {errorMessage && (
        <div className="bg-red-950/90 border-b border-red-800 px-4 py-2.5 text-xs text-red-200 flex items-center justify-between z-10 animate-in fade-in">
          <div className="flex items-center gap-2">
            <AlertTriangle size={15} className="text-red-400 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button 
            onClick={() => setErrorMessage(null)} 
            className="text-red-300 hover:text-white p-1 rounded"
          >
            <XCircle size={15} />
          </button>
        </div>
      )}

      {/* Main Content Area */}
      {selectedEnv === null || !hasResources ? (
        <EmptyState
          mode={selectedEnv === 'aws' ? 'live' : selectedEnv === 'manual' ? 'manual' : 'unconnected'}
          discoveryStatus={twinState?.discovery_status || 'idle'}
          accountId={twinState?.account_id}
          region={twinState?.region}
          arn={twinState?.arn}
          onOpenConnect={() => setIsConnectModalOpen(true)}
          onDiscover={handleDiscoverInfrastructure}
          onStartManual={handleSelectManual}
          onSelectAWS={handleSelectAWS}
          onSelectManual={handleSelectManual}
          onAddResource={() => { setEditResource(null); setIsResourceModalOpen(true); }}
          loading={syncing || loading}
        />
      ) : activeTab === 'dashboard' ? (
        <DashboardView
          stats={stats}
          components={rawComponents}
          awsStatus={{
            authenticated: isLiveAWS,
            account_id: twinState?.account_id,
            arn: twinState?.arn,
            region: twinState?.region
          }}
          mode={twinState?.mode}
          metricsMap={metricsMap}
          costReport={costReport}
          healthReport={healthReport}
          onOpenConnect={() => setIsConnectModalOpen(true)}
          onSyncAWS={handleDiscoverInfrastructure}
          onAddManualResource={() => { setEditResource(null); setIsResourceModalOpen(true); }}
          syncing={syncing}
        />
      ) : (
        <div className="flex flex-1 overflow-hidden relative">
          
          {/* React Flow Topology Canvas */}
          <div className="flex-1 h-full bg-slate-900 relative">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={onNodeClick}
              onEdgeClick={onEdgeClick}
              onPaneClick={() => setSelectedNode(null)}
              nodeTypes={nodeTypes}
              fitView
              attributionPosition="bottom-left"
            >
              <Controls className="bg-slate-800 border-slate-700 fill-slate-400 text-slate-400" />
              <MiniMap 
                nodeColor={(node: any) => node.data?.blastRadius ? '#ef4444' : '#3b82f6'}
                maskColor="rgba(15, 23, 42, 0.7)"
                className="bg-slate-800 border-slate-700" 
              />
              <Background color="#334155" gap={16} size={1} />
            </ReactFlow>

            {/* Quick builder floating hint in Manual Mode */}
            {isManual && (
              <div className="absolute bottom-4 left-4 z-10 bg-slate-800/90 backdrop-blur border border-slate-700/80 px-3 py-2 rounded-xl text-[11px] text-slate-300 shadow-xl flex items-center gap-3">
                <span>Drag between node handles to create dependencies • Click an edge to delete it</span>
                <button
                  onClick={() => { setEditResource(null); setIsResourceModalOpen(true); }}
                  className="px-2 py-1 bg-blue-600 hover:bg-blue-500 rounded text-white font-bold transition flex items-center gap-1"
                >
                  <Plus size={11} /> Add Node
                </button>
              </div>
            )}
          </div>

          {/* 4-Phase Inspector Drawer */}
          {selectedNode && (
            <InspectorDrawer
              key={selectedNode.id}
              selectedNode={selectedNode}
              metricsMap={metricsMap}
              recommendations={recommendations}
              rawDependencies={rawDependencies}
              rawComponents={rawComponents}
              simResult={simResult}
              simulating={simulating}
              onSimulate={handleSimulate}
              onClose={() => setSelectedNode(null)}
              onEditManualResource={(node) => {
                setEditResource(node);
                setIsResourceModalOpen(true);
              }}
              onDeleteManualResource={(nodeId) => handleDeleteManualResource(nodeId)}
              onSolutionApplied={() => fetchData()}
              apiBase={API_BASE}
            />
          )}

        </div>
      )}

      {/* AWS Connection Modal */}
      <AWSConnectModal
        isOpen={isConnectModalOpen}
        onClose={() => setIsConnectModalOpen(false)}
        onConnected={async () => {
          setSelectedEnv('aws');
          sessionStorage.setItem('infratwin_env', 'aws');
          await fetchData();
        }}
        apiBase={API_BASE}
      />

      {/* Manual Resource Add/Edit Modal */}
      <ManualResourceModal
        isOpen={isResourceModalOpen}
        onClose={() => {
          setIsResourceModalOpen(false);
          setEditResource(null);
        }}
        onSave={handleSaveManualResource}
        editResource={editResource}
      />

      {/* Manual Dependency Add Modal */}
      <ManualDependencyModal
        isOpen={isDependencyModalOpen}
        onClose={() => {
          setIsDependencyModalOpen(false);
          setPendingSourceId(null);
          setPendingTargetId(null);
        }}
        onSave={handleSaveManualDependency}
        components={rawComponents}
        initialSourceId={pendingSourceId}
        initialTargetId={pendingTargetId}
      />

    </div>
  );
}
