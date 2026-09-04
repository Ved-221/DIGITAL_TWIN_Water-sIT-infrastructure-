import { useEffect, useState, useCallback } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
  Handle,
  Position,
  Panel
} from '@xyflow/react';
import type { Node, Edge, Connection } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import classNames from 'classnames';
import { AlertTriangle, Clock, DollarSign, Activity, LayoutDashboard, Share2, Server, Cloud, HeartPulse, Monitor, Database, Network, HardDrive, Key, Plug, Box, Shield, ShieldAlert, ShieldCheck, Plus, Trash2, Edit, Save, ArrowLeft, RefreshCw, X, Link as LinkIcon, Info, Wrench } from 'lucide-react';
import ResourceFormModal from './components/ResourceFormModal';
import DependencyFormModal from './components/DependencyFormModal';

const API_BASE = 'http://localhost:8000/api';

const iconMap: Record<string, any> = {
  application: Monitor,
  server: Server,
  database: Database,
  network: Network,
  cloud_resource: Cloud,
  storage: HardDrive,
  api: Plug,
  identity: Key,
};

const CustomNode = ({ data, selected }: any) => {
  const isBlastRadius = data.blastRadius;
  const IconComponent = iconMap[data.type] || Box;
  const isPlanned = data.owner === 'Planned Deployment';
  
  const envColor = data.environment === 'cloud' || data.environment === 'cloud_resource' 
    ? 'text-green-400' 
    : data.environment === 'on_prem' 
      ? 'text-yellow-400' 
      : 'text-slate-400';

  return (
    <div className={classNames(
      "px-4 py-2 shadow-lg rounded-md border-2 min-w-[160px] transition-all relative",
      selected ? "border-blue-500 bg-slate-900" : "border-slate-700 bg-slate-900",
      isBlastRadius && !selected ? "border-red-500 bg-red-950/40" : "",
      isPlanned ? "border-dashed border-teal-500/70" : ""
    )}>
      <Handle type="target" position={Position.Top} className="w-2 h-2 bg-slate-400" />
      <div className="flex items-center space-x-2">
        <span className={classNames("p-1.5 rounded-md", data.type === 'database' ? "text-slate-400 bg-slate-800" : data.type === 'server' || data.type === 'application' ? "text-red-300 bg-slate-800" : "text-blue-300 bg-slate-800")}>
          <IconComponent size={20} />
        </span>
        <div>
          <div className="text-sm font-bold text-white">{data.name}</div>
          <div className="text-[10px] capitalize text-slate-400 tracking-wide">
            {data.type} • {data.criticality}
          </div>
        </div>
      </div>
      <div className="mt-2 text-xs flex justify-between items-center text-slate-500 border-t border-slate-700/50 pt-1">
        <span>${data.cost_per_month}/mo</span>
        {isPlanned ? (
          <span className="bg-teal-900 text-teal-400 px-1.5 py-0.5 rounded uppercase text-[9px] font-bold tracking-wider">PLANNED</span>
        ) : data.source_environment !== 'aws' ? (
          <span className="bg-teal-900 text-teal-400 px-1.5 py-0.5 rounded uppercase text-[9px] font-bold tracking-wider">MANUAL</span>
        ) : null}
      </div>
      {isBlastRadius && (
        <div className="absolute -top-3 -right-3 bg-red-500 text-white rounded-full p-1 shadow-lg">
          <AlertTriangle size={16} />
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="w-2 h-2 bg-slate-400" />
    </div>
  );
};

const nodeTypes = {
  custom: CustomNode,
};

export default function App() {
  const [selectedEnv, setSelectedEnv] = useState<string | null>(null);
  const [view, setView] = useState<'graph' | 'dashboard'>('graph');
  
  const [projects, setProjects] = useState<any[]>([]);
  const [currentProjectName, setCurrentProjectName] = useState<string>('');

  const [stats, setStats] = useState<any>(null);
  const [rawComponents, setRawComponents] = useState<any[]>([]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [loading, setLoading] = useState(false);
  
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [simResult, setSimResult] = useState<any>(null);
  const [simulating, setSimulating] = useState(false);

  const [healthData, setHealthData] = useState<any>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState(false);

  const [complianceData, setComplianceData] = useState<any>(null);
  const [complianceLoading, setComplianceLoading] = useState(false);

  // Modals for Manual Builder
  const [isResourceModalOpen, setIsResourceModalOpen] = useState(false);
  const [resourceToEdit, setResourceToEdit] = useState<any>(null);
  const [isDependencyModalOpen, setIsDependencyModalOpen] = useState(false);
  const [prefilledDependency, setPrefilledDependency] = useState<any>(null);

  // New Project Form
  const [showNewProjectForm, setShowNewProjectForm] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');

  const onConnect = useCallback(
    (params: Connection | Edge) => {
      if (selectedEnv?.startsWith('aws')) return; // Read-only
      setPrefilledDependency({ source_id: params.source, target_id: params.target });
      setIsDependencyModalOpen(true);
    },
    [selectedEnv],
  );

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/manual/projects`);
      const data = await res.json();
      setProjects(data);
    } catch (err) {
      console.error(err);
    }
  }, []);

  const handleCreateProject = async (e: any) => {
    e.preventDefault();
    if (!newProjectName) return;
    try {
      const res = await fetch(`${API_BASE}/manual/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newProjectName })
      });
      const data = await res.json();
      setNewProjectName('');
      setShowNewProjectForm(false);
      setSelectedEnv(data.id);
      setCurrentProjectName(data.name);
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteProject = async (id: string, e: any) => {
    e.stopPropagation();
    if (!window.confirm("Delete this entire dashboard and all its resources?")) return;
    try {
      await fetch(`${API_BASE}/manual/projects/${id}`, { method: 'DELETE' });
      fetchProjects();
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    if (selectedEnv === 'manual_menu' || selectedEnv === 'aws_menu') {
      fetchProjects();
    }
  }, [selectedEnv, fetchProjects]);

  const fetchData = useCallback(async () => {
    if (!selectedEnv || selectedEnv === 'manual_menu' || selectedEnv === 'aws_menu') return;
    setLoading(true);
    try {
      if (!selectedEnv?.startsWith('aws')) {
        const proj = projects.find(p => p.id === selectedEnv);
        if (proj) setCurrentProjectName(proj.name);
      }

      const [compsRes, depsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/twin/components?source_environment=${selectedEnv}`),
        fetch(`${API_BASE}/twin/dependencies?source_environment=${selectedEnv}`),
        fetch(`${API_BASE}/twin/stats?source_environment=${selectedEnv}`)
      ]);
      
      const comps = await compsRes.json();
      const deps = await depsRes.json();
      const statsData = await statsRes.json();
      
      setRawComponents(comps);
      setStats(statsData);

      const newNodes: Node[] = comps.map((c: any, i: number) => ({
        id: c.id,
        type: 'custom',
        position: { 
          x: (i % 4) * 280 + 50, 
          y: Math.floor(i / 4) * 150 + 50 
        },
        data: { ...c, blastRadius: false }
      }));

      const newEdges: Edge[] = deps.map((d: any) => {
        let edgeColor = '#64748b'; // default slate-500
        if (d.relationship_type === 'depends_on') edgeColor = '#3b82f6';
        else if (d.relationship_type === 'connects_to') edgeColor = '#10b981';
        else if (d.relationship_type === 'hosted_on') edgeColor = '#f59e0b';
        else if (d.relationship_type === 'authenticates_via') edgeColor = '#8b5cf6';
        else if (d.relationship_type === 'stores_in') edgeColor = '#06b6d4';

        return {
          id: d.id,
          source: d.source_id,
          target: d.target_id,
          animated: true,
          label: d.relationship_type.replace('_', ' '),
          style: { stroke: edgeColor, strokeWidth: 2, strokeDasharray: '5 5' },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: edgeColor,
          },
          labelBgStyle: { fill: '#1e293b', fillOpacity: 0.8 },
          labelStyle: { fill: '#38bdf8', fontSize: 10, fontWeight: 500 },
        };
      });

      setNodes(newNodes);
      setEdges(newEdges);
      
      // Update selected node reference if it changed
      if (selectedNode) {
        const updated = comps.find((c: any) => c.id === selectedNode.id);
        if (updated) setSelectedNode(updated);
        else setSelectedNode(null);
      }
    } catch (err) {
      console.error("Error fetching twin data", err);
    } finally {
      setLoading(false);
    }
  }, [selectedEnv, selectedNode, setNodes, setEdges, projects]);

  useEffect(() => {
    fetchData();
  }, [selectedEnv]);

  const onNodeClick = useCallback((_: any, node: Node) => {
    const data = node.data;
    setSelectedNode(data);
    setSimResult(null);
    setHealthData(null);
    setHealthError(false);
    setComplianceData(null);
    
    setNodes(nds => nds.map(n => ({
      ...n,
      data: { ...n.data, blastRadius: false }
    })));

    // Only fetch real AWS data if we are in AWS mode
    if (selectedEnv?.startsWith('aws')) {
      setHealthLoading(true);
      setComplianceLoading(true);

      fetch(`${API_BASE}/twin/health/${data.id}`)
        .then(res => {
          if (!res.ok) throw new Error("Health fetch failed");
          return res.json();
        })
        .then(json => {
          setHealthData(json);
          setHealthLoading(false);
        })
        .catch(err => {
          console.error("CloudWatch health fetch error:", err);
          setHealthError(true);
          setHealthLoading(false);
        });

      fetch(`${API_BASE}/twin/compliance/${data.id}`)
        .then(res => {
          if (!res.ok) throw new Error("Compliance fetch failed");
          return res.json();
        })
        .then(json => {
          setComplianceData(json);
          setComplianceLoading(false);
        })
        .catch(err => {
          console.error("Config compliance fetch error:", err);
          setComplianceLoading(false);
        });
    }
  }, [setNodes, selectedEnv]);

  const handleSimulate = async (useAi: boolean = false) => {
    if (!selectedNode) return;
    setSimulating(true);
    
    try {
      const res = await fetch(`${API_BASE}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_component_id: selectedNode.id,
          action: "migrate",
          destination_env: "cloud",
          use_ai: useAi
        })
      });
      
      const data = await res.json();
      setSimResult(data);
      
      setNodes(nds => nds.map(n => ({
        ...n,
        data: {
          ...n.data,
          blastRadius: data.affected_components.includes(n.id)
        }
      })));
      
    } catch (err) {
      console.error(err);
    } finally {
      setSimulating(false);
    }
  };

  const handleDeleteResource = async () => {
    if (!selectedNode || !window.confirm("Are you sure you want to delete this resource and its dependencies?")) return;
    try {
      await fetch(`${API_BASE}/manual/components/${selectedNode.id}`, { method: 'DELETE' });
      setSelectedNode(null);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeployToAWS = async () => {
    if (!selectedEnv || selectedEnv?.startsWith('aws') || selectedEnv === 'manual_menu' || selectedEnv === 'aws_menu') return;
    if (!window.confirm("Deploy this manual architecture to the AWS Sandbox for simulation?")) return;
    
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/manual/projects/${selectedEnv}/push-to-aws`, { method: 'POST' });
      if (!res.ok) throw new Error("Failed to deploy to AWS");
      
      setSelectedEnv(`aws_sim_${selectedEnv}`);
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  };

  // Environment Selection Screen
  if (!selectedEnv) {
    return (
      <div className="flex flex-col h-screen bg-slate-950 text-slate-200 items-center justify-center p-4">
        <h1 className="text-5xl font-bold text-white mb-8">
          <span className="bg-blue-600 text-white px-2 py-1 rounded mr-2">IT</span> InfraTwin
        </h1>
        <h2 className="text-xl font-medium mb-8 text-slate-300">Choose how you want to create your Digital Twin</h2>
        <div className="flex gap-6 max-w-2xl w-full">
          <button 
            onClick={() => setSelectedEnv('aws_menu')}
            className="flex-1 bg-slate-900 border-2 border-slate-800 hover:border-blue-500 rounded-xl p-8 flex flex-col items-center transition group text-left"
          >
            <Cloud size={48} className="text-blue-400 mb-4 group-hover:scale-110 transition" />
            <h3 className="text-xl font-bold text-white mb-2">AWS Environment</h3>
            <p className="text-slate-400 text-sm text-center">Connect to your live AWS account to auto-discover resources and analyze real-time metrics with AI insights.</p>
          </button>
          
          <button 
            onClick={() => setSelectedEnv('manual_menu')}
            className="flex-1 bg-slate-900 border-2 border-slate-800 hover:border-teal-500 rounded-xl p-8 flex flex-col items-center transition group text-left"
          >
            <Box size={48} className="text-teal-400 mb-4 group-hover:scale-110 transition" />
            <h3 className="text-xl font-bold text-white mb-2">Manual Environment</h3>
            <p className="text-slate-400 text-sm text-center">Build, save, and switch between multiple deterministic Digital Twin dashboards manually.</p>
          </button>
        </div>
      </div>
    );
  }

  // AWS Environments Menu
  if (selectedEnv === 'aws_menu') {
    return (
      <div className="flex flex-col h-screen bg-slate-950 text-slate-200 p-8">
        <button onClick={() => setSelectedEnv(null)} className="flex items-center gap-2 text-slate-400 hover:text-white mb-8 transition">
          <ArrowLeft size={16} /> Back to Environments
        </button>
        
        <div className="max-w-4xl mx-auto w-full">
          <h2 className="text-3xl font-bold text-white mb-8">AWS Environments</h2>
          
          <div className="mb-8">
            <h3 className="text-xl font-bold text-slate-400 mb-4">Live Production</h3>
            <div onClick={() => setSelectedEnv('aws')} className="bg-slate-900 border border-slate-800 hover:border-blue-500 p-6 rounded-xl cursor-pointer transition flex items-center gap-4">
              <Cloud size={32} className="text-blue-400" />
              <div>
                <h4 className="text-xl font-bold text-white">Pure Live AWS Environment</h4>
                <p className="text-slate-400 text-sm">Read-only view of your unmodified production infrastructure.</p>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-xl font-bold text-slate-400 mb-4">Simulation Sandboxes</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {projects.length === 0 && (
                <div className="col-span-2 text-center py-12 text-slate-500 bg-slate-900/50 rounded-xl border border-slate-800 border-dashed">
                  <Box size={48} className="mx-auto mb-4 opacity-50" />
                  <p>No sandboxes deployed yet. Deploy from a manual project first.</p>
                </div>
              )}
              {projects.map(proj => (
                <div key={proj.id} onClick={() => { setSelectedEnv(`aws_sim_${proj.id}`); setCurrentProjectName(proj.name); }} className="bg-slate-900 border border-slate-800 hover:border-teal-500 p-6 rounded-xl cursor-pointer transition flex items-center gap-4">
                  <Box size={24} className="text-teal-400 shrink-0" />
                  <div>
                    <h4 className="text-lg font-bold text-white mb-1">{proj.name}</h4>
                    <p className="text-slate-500 text-xs">Merged Sandbox Environment</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Manual Projects Menu
  if (selectedEnv === 'manual_menu') {
    return (
      <div className="flex flex-col h-screen bg-slate-950 text-slate-200 p-8">
        <button onClick={() => setSelectedEnv(null)} className="flex items-center gap-2 text-slate-400 hover:text-white mb-8 transition">
          <ArrowLeft size={16} /> Back to Environments
        </button>
        
        <div className="max-w-4xl mx-auto w-full">
          <div className="flex justify-between items-center mb-8">
            <h2 className="text-3xl font-bold text-white">Saved Manual Dashboards</h2>
            <button onClick={() => setShowNewProjectForm(true)} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded-md font-semibold transition text-sm">
              <Plus size={16} /> Create New Dashboard
            </button>
          </div>

          {showNewProjectForm && (
            <div className="bg-slate-900 p-6 rounded-xl border border-blue-500/50 mb-8 shadow-lg">
              <form onSubmit={handleCreateProject} className="flex gap-4">
                <input 
                  autoFocus
                  type="text" 
                  value={newProjectName} 
                  onChange={(e) => setNewProjectName(e.target.value)} 
                  placeholder="e.g. New York Datacenter Migration"
                  className="flex-1 bg-slate-950 border border-slate-700 rounded p-3 text-white focus:outline-none focus:border-blue-500" 
                />
                <button type="button" onClick={() => setShowNewProjectForm(false)} className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded font-medium">Cancel</button>
                <button type="submit" className="px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded font-semibold text-white">Save</button>
              </form>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.length === 0 && !showNewProjectForm && (
              <div className="col-span-2 text-center py-12 text-slate-500 bg-slate-900/50 rounded-xl border border-slate-800 border-dashed">
                <Box size={48} className="mx-auto mb-4 opacity-50" />
                <p>No manual dashboards saved yet.</p>
              </div>
            )}
            {projects.map(proj => (
              <div key={proj.id} onClick={() => { setSelectedEnv(proj.id); setCurrentProjectName(proj.name); }} className="bg-slate-900 border border-slate-800 hover:border-blue-500 p-6 rounded-xl cursor-pointer transition group flex justify-between items-start">
                <div>
                  <h3 className="text-xl font-bold text-white mb-2 flex items-center gap-2">
                    <Box size={18} className="text-blue-400" />
                    {proj.name}
                  </h3>
                  <p className="text-xs text-slate-500">Created: {new Date(proj.created_at).toLocaleDateString()}</p>
                </div>
                <button 
                  onClick={(e) => handleDeleteProject(proj.id, e)}
                  className="text-slate-500 hover:text-red-400 p-2 rounded hover:bg-slate-800 opacity-0 group-hover:opacity-100 transition"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const inboundDeps = edges.filter(e => e.target === selectedNode?.id);
  const totalResources = rawComponents.length;

  return (
    <div className="flex flex-col h-screen bg-[#0b1120] text-slate-200 font-sans">
      <header className="px-4 py-3 border-b border-slate-800 bg-[#0f172a] flex justify-between items-center z-10 shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => setSelectedEnv(null)}>
            <div className="bg-blue-600 text-white px-1.5 py-0.5 rounded font-bold text-lg">IT</div>
            <span className="text-xl font-bold text-white tracking-tight">InfraTwin</span>
          </div>
          
          <div className="h-6 w-px bg-slate-700 mx-2"></div>
          
          <div 
            className="flex items-center gap-2 bg-[#064e3b]/30 border border-[#047857]/50 px-3 py-1.5 rounded-full text-xs font-semibold tracking-wide text-teal-400 cursor-pointer hover:bg-[#064e3b]/50 transition"
            onClick={() => setSelectedEnv(selectedEnv?.startsWith('aws') ? 'aws_menu' : 'manual_menu')}
          >
            <div className="w-2 h-2 rounded-full bg-teal-400"></div>
            {selectedEnv?.startsWith('aws') ? 'AWS ENVIRONMENT' : 'MANUAL ENVIRONMENT'} 
            <span className="text-teal-200/50 mx-1">•</span> 
            {selectedEnv === 'aws' ? 'Live Region' : selectedEnv?.startsWith('aws_sim_') ? 'Simulation Sandbox' : 'Custom Infrastructure'}
            <span className="text-teal-200/50 mx-1">•</span> 
            {totalResources} Resources
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          {!selectedEnv?.startsWith('aws') && view === 'graph' && (
            <>
              <button onClick={() => { setResourceToEdit(null); setIsResourceModalOpen(true); }} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded text-sm font-semibold text-white transition">
                <Plus size={16} /> Add Resource
              </button>
              <button onClick={() => setIsDependencyModalOpen(true)} className="flex items-center gap-2 bg-purple-600 hover:bg-purple-500 px-3 py-1.5 rounded text-sm font-semibold text-white transition">
                <LinkIcon size={16} /> Connect
              </button>
              <button onClick={handleDeployToAWS} disabled={loading} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 px-3 py-1.5 rounded text-sm font-semibold text-white transition ml-2">
                <Cloud size={16} /> Deploy to AWS Sandbox
              </button>
            </>
          )}

          {selectedEnv?.startsWith('aws') ? (
            selectedEnv.startsWith('aws_sim_') ? (
              <button onClick={() => setSelectedEnv(selectedEnv.replace('aws_sim_', ''))} className="flex items-center gap-2 bg-transparent border border-slate-700 hover:bg-slate-800 px-3 py-1.5 rounded text-sm font-medium text-teal-400 transition ml-2">
                <Box size={14} /> Edit in Manual Environment
              </button>
            ) : (
              <button onClick={() => setSelectedEnv('manual_menu')} className="flex items-center gap-2 bg-transparent border border-slate-700 hover:bg-slate-800 px-3 py-1.5 rounded text-sm font-medium text-teal-400 transition ml-2">
                <Box size={14} /> Switch to Manual
              </button>
            )
          ) : (
            <button onClick={() => setSelectedEnv('aws_menu')} className="flex items-center gap-2 bg-transparent border border-slate-700 hover:bg-slate-800 px-3 py-1.5 rounded text-sm font-medium text-teal-400 transition ml-2">
              <Key size={14} /> Switch to AWS
            </button>
          )}
          
          <button className="flex items-center gap-2 bg-transparent border border-slate-700 hover:bg-slate-800 px-3 py-1.5 rounded text-sm font-medium text-slate-300 transition">
            <Trash2 size={14} /> Clear
          </button>
          
          <button onClick={fetchData} className="flex items-center gap-2 bg-transparent border border-slate-700 hover:bg-slate-800 px-3 py-1.5 rounded text-sm font-medium text-slate-300 transition">
            <RefreshCw size={14} /> Reset
          </button>

          <div className="flex bg-[#1e293b] rounded p-0.5 ml-2 border border-slate-700">
            <button 
              onClick={() => setView('graph')}
              className={classNames("flex items-center gap-2 px-3 py-1 rounded text-sm font-medium transition", view === 'graph' ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white")}
            >
              <Share2 size={14} /> Topology
            </button>
            <button 
              onClick={() => setView('dashboard')}
              className={classNames("flex items-center gap-2 px-3 py-1 rounded text-sm font-medium transition", view === 'dashboard' ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white")}
            >
              <LayoutDashboard size={14} /> Dashboard
            </button>
          </div>
        </div>
      </header>
      
      <main className="flex-1 relative flex overflow-hidden">
        {view === 'dashboard' ? (
          <div className="flex-1 overflow-y-auto p-8 bg-[#0b1120]">
             <div className="max-w-6xl mx-auto">
                <h2 className="text-3xl font-bold text-white mb-8">Infrastructure Health & Risk</h2>
                
                {stats && (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
                    <div className="bg-[#1e293b] p-6 rounded-xl border border-slate-700 shadow-lg">
                      <div className="flex items-center gap-3 mb-2 text-slate-400"><Server size={20} className="text-blue-400"/> Total Components</div>
                      <div className="text-4xl font-bold text-white">{stats.total_components}</div>
                    </div>
                    <div className="bg-[#1e293b] p-6 rounded-xl border border-slate-700 shadow-lg">
                      <div className="flex items-center gap-3 mb-2 text-slate-400"><AlertTriangle size={20} className="text-red-400"/> Critical Services</div>
                      <div className="text-4xl font-bold text-white">{stats.critical_services_count}</div>
                    </div>
                    <div className="bg-[#1e293b] p-6 rounded-xl border border-slate-700 shadow-lg">
                      <div className="flex items-center gap-3 mb-2 text-slate-400"><DollarSign size={20} className="text-emerald-400"/> Monthly Run Rate</div>
                      <div className="text-4xl font-bold text-white">${stats.total_monthly_cost.toLocaleString()}</div>
                    </div>
                    <div className="bg-[#1e293b] p-6 rounded-xl border border-slate-700 shadow-lg flex flex-col justify-center">
                      <div className="flex items-center justify-between mb-2">
                        <span className="flex items-center gap-2 text-slate-400"><Server size={16}/> On-Prem</span>
                        <span className="font-bold text-white">{stats.on_prem_count}</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-2 mb-4">
                        <div className="bg-slate-500 h-2 rounded-full" style={{ width: `${stats.total_components ? (stats.on_prem_count/stats.total_components)*100 : 0}%`}}></div>
                      </div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="flex items-center gap-2 text-slate-400"><Cloud size={16}/> Cloud</span>
                        <span className="font-bold text-white">{stats.cloud_count}</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-2">
                        <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${stats.total_components ? (stats.cloud_count/stats.total_components)*100 : 0}%`}}></div>
                      </div>
                    </div>
                  </div>
                )}
             </div>
          </div>
        ) : (
          <>
            <div className="flex-1 relative bg-[#0f172a]">
              {loading ? (
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="animate-pulse text-lg text-slate-400">Loading infrastructure...</span>
                </div>
              ) : nodes.length === 0 ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center z-0">
                  <Box size={64} className="text-slate-700 mb-4" />
                  <h3 className="text-xl font-bold text-slate-400 mb-2">No infrastructure resources yet</h3>
                  {!selectedEnv?.startsWith('aws') && (
                     <p className="text-slate-500">Click "Add Resource" in the top right to start building your Digital Twin manually.</p>
                  )}
                </div>
              ) : (
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onConnect={onConnect}
                  onNodeClick={onNodeClick}
                  nodeTypes={nodeTypes}
                  fitView
                  className="bg-[#0f172a]"
                >
                  <Controls className="bg-slate-800 text-white fill-white border-slate-700 shadow-xl" />
                  <Background color="#334155" gap={16} variant={BackgroundVariant.Dots} size={1} />
                  
                  {!selectedEnv?.startsWith('aws') && (
                    <Panel position="bottom-left" className="mb-4 ml-4">
                      <div className="bg-[#1e293b] border border-slate-700 p-3 rounded-lg shadow-xl flex items-center gap-4">
                        <span className="text-slate-400 text-sm">Drag between node handles to create dependencies • Click an edge to delete it</span>
                        <button onClick={() => { setResourceToEdit(null); setIsResourceModalOpen(true); }} className="bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded text-sm font-semibold flex items-center gap-1">
                          <Plus size={16} /> Add Node
                        </button>
                      </div>
                    </Panel>
                  )}
                </ReactFlow>
              )}
            </div>

            {/* Sidebar (Node Details) */}
            <div className={classNames(
              "bg-[#1e293b] border-l border-slate-700 flex flex-col transition-all duration-300 shadow-2xl shrink-0 z-20",
              selectedNode ? (simResult ? "w-[800px] translate-x-0" : "w-[450px] translate-x-0") : "w-[450px] translate-x-full hidden"
            )}>
              <div className="p-4 border-b border-slate-700 flex justify-between items-center bg-[#1e293b] shrink-0">
                <h2 className="text-[11px] font-bold text-slate-300 uppercase tracking-widest flex items-center gap-2">
                  <Box size={14} className="text-blue-400" />
                  NODE DETAILS
                </h2>
                <button onClick={() => setSelectedNode(null)} className="text-slate-400 hover:text-white p-1">
                  <X size={18} />
                </button>
              </div>
              
              <div className="flex-1 overflow-hidden flex">
                
                {/* LEFT COLUMN: AGENT SUMMARY */}
                {simResult && (
                  <div className="w-[280px] bg-[#0f172a]/60 border-r border-slate-700 overflow-y-auto p-5 shrink-0 flex flex-col gap-6">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">AGENT SUMMARY</h3>
                    
                    {/* Financial Analyst */}
                    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 shadow-sm">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-lg">💰</span>
                        <span className="text-sm font-bold text-white">Financial Analyst</span>
                      </div>
                      <div className="flex flex-col gap-1 pl-8">
                         <span className={classNames("text-xs font-bold", simResult.cost_delta_monthly <= 0 ? 'text-emerald-400' : 'text-yellow-400')}>
                           {simResult.cost_delta_monthly <= 0 ? '✓ Favorable' : '⚠ Caution'}
                         </span>
                         <span className="text-xs text-slate-400 leading-tight">
                           {simResult.cost_delta_monthly <= 0 ? 'Cost impact is low' : 'Increases monthly run rate'}
                         </span>
                      </div>
                    </div>

                    {/* Risk Analyst */}
                    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 shadow-sm">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-lg">🛡️</span>
                        <span className="text-sm font-bold text-white">Risk Analyst</span>
                      </div>
                      <div className="flex flex-col gap-1 pl-8">
                         <span className={classNames("text-xs font-bold", simResult.risk_level === 'High' ? 'text-red-400' : simResult.risk_level === 'Medium' ? 'text-yellow-400' : 'text-emerald-400')}>
                           {simResult.risk_level === 'High' ? '✕ High Risk' : simResult.risk_level === 'Medium' ? '⚠ Caution' : '✓ Favorable'}
                         </span>
                         <span className="text-xs text-slate-400 leading-tight">
                           {simResult.estimated_downtime_minutes} min downtime
                         </span>
                      </div>
                    </div>

                    {/* AI Cloud Architect */}
                    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 shadow-sm">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-lg">☁️</span>
                        <span className="text-sm font-bold text-white">AI Cloud Architect</span>
                      </div>
                      <div className="flex flex-col gap-1 pl-8">
                         <span className={classNames("text-xs font-bold", simResult.risk_level === 'High' || simResult.risk_score > 70 ? 'text-red-400' : simResult.risk_level === 'Medium' ? 'text-yellow-400' : 'text-emerald-400')}>
                           {simResult.risk_level === 'High' || simResult.risk_score > 70 ? '✕ Blocked' : simResult.risk_level === 'Medium' ? '⚠ Conditional' : '✓ Approved'}
                         </span>
                         <span className="text-xs text-slate-400 leading-tight">
                           {simResult.risk_level === 'High' || simResult.risk_score > 70 ? 'Migration not recommended' : simResult.risk_level === 'Medium' ? 'Phased migration' : 'Ready for migration'}
                         </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* RIGHT COLUMN: MAIN CONTENT */}
                <div className="flex-1 overflow-y-auto p-6 space-y-8">
                
                {/* Info Sandbox */}
                {!selectedEnv?.startsWith('aws') && (
                  <div className="bg-[#0f172a]/50 border border-slate-700 p-3 rounded-lg flex items-start gap-3">
                    <Info size={18} className="text-blue-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-slate-300 leading-relaxed">
                      <span className="font-bold text-slate-200">Digital Twin Sandbox:</span> Telemetry and simulated actions run virtually in this twin model. Real production AWS infrastructure is never modified.
                    </p>
                  </div>
                )}

                {/* 1. ACTUAL STATE */}
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <div className="flex items-center gap-2">
                      <span className="bg-emerald-900/40 text-emerald-400 border border-emerald-800/50 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
                        <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full"></div>
                        1. ACTUAL STATE
                      </span>
                    </div>
                    {(!selectedEnv?.startsWith('aws') || selectedNode?.owner === 'Planned Deployment') && (
                      <span className="bg-slate-800 text-slate-300 border border-slate-700 px-2 py-1 rounded text-xs flex items-center gap-1">
                        <Wrench size={12} /> {selectedNode?.owner === 'Planned Deployment' ? 'Planned Resource' : 'Manual Resource'}
                      </span>
                    )}
                  </div>

                  <h3 className="text-3xl font-bold text-white mb-1">{selectedNode?.name}</h3>
                  <div className="text-sm text-slate-400 capitalize mb-4">
                    {selectedNode?.type} • {selectedNode?.environment}
                  </div>

                  <div className="flex gap-2 mb-6">
                    <span className="bg-slate-800/80 border border-slate-700 text-slate-300 px-3 py-1.5 rounded-md text-xs font-medium">
                      Crit: {selectedNode?.criticality}
                    </span>
                    <span className="bg-slate-800/80 border border-slate-700 text-slate-300 px-3 py-1.5 rounded-md text-xs font-medium">
                      Cost: ${selectedNode?.cost_per_month}/mo
                    </span>
                    <span className="bg-slate-800/80 border border-slate-700 text-slate-300 px-3 py-1.5 rounded-md text-xs font-medium">
                      Region: {selectedNode?.location}
                    </span>
                  </div>

                  {!selectedEnv?.startsWith('aws') && (
                    <div className="flex gap-3 pt-2">
                      <button onClick={() => { setResourceToEdit(selectedNode); setIsResourceModalOpen(true); }} className="flex-1 bg-transparent border border-slate-600 hover:border-slate-400 text-slate-300 hover:text-white py-2 rounded flex items-center justify-center gap-2 text-sm font-medium transition">
                        <Wrench size={14} /> Edit Properties
                      </button>
                      <button onClick={handleDeleteResource} className="bg-transparent border border-red-900 hover:border-red-700 text-red-400 hover:text-red-300 px-4 py-2 rounded text-sm font-medium transition">
                        Delete Resource
                      </button>
                    </div>
                  )}
                </div>

                <hr className="border-slate-700/60" />

                {/* Simulation Assumptions */}
                {!selectedEnv?.startsWith('aws') && (
                  <div>
                    <div className="flex justify-between items-center mb-3">
                      <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                        <Activity size={16} className="text-blue-400" /> Simulation Assumptions
                      </h4>
                      <span className="text-xs font-bold text-teal-500 uppercase tracking-wider">User Input</span>
                    </div>
                    
                    <div className="bg-[#0f172a]/50 border border-slate-700 p-4 rounded-lg">
                      <h5 className="text-sm font-semibold text-slate-200 mb-1">Telemetry Unavailable</h5>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        No telemetry source configured. You can configure simulation assumptions by clicking Edit Properties above.
                      </p>
                    </div>
                  </div>
                )}

                {/* Infrastructure Dependencies */}
                <div>
                  <div className="flex justify-between items-center mb-3">
                    <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                      <Share2 size={16} className="text-blue-400" /> Infrastructure Dependencies
                    </h4>
                    <span className="text-xs font-medium text-slate-400">{inboundDeps.length} Verified</span>
                  </div>
                  
                  <div className="text-xs text-slate-400 mb-2">Inbound Sources ({inboundDeps.length})</div>
                  <div className="space-y-2">
                    {inboundDeps.length === 0 ? (
                      <div className="text-xs text-slate-500 italic">No inbound dependencies</div>
                    ) : (
                      inboundDeps.map(dep => {
                        const srcNode = rawComponents.find(c => c.id === dep.source);
                        return (
                          <div key={dep.id} className="bg-[#0f172a]/50 border border-slate-700 p-3 rounded flex justify-between items-center">
                            <span className="text-sm text-slate-300 flex items-center gap-2">
                              <ArrowLeft size={14} className="text-slate-500" />
                              {srcNode?.name || dep.source}
                            </span>
                            <span className="bg-slate-800 text-slate-400 px-2 py-0.5 rounded text-[10px] uppercase">
                              {dep.label?.toString()}
                            </span>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                <hr className="border-slate-700/60" />

                {/* 3. SIMULATED IMPACT / DECISION */}
                <div className="pb-8">
                  <div className="flex justify-between items-center mb-4">
                    <span className="bg-orange-900/40 text-orange-400 border border-orange-800/50 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider flex items-center gap-1">
                      <Activity size={12} />
                      {simResult ? "3. MIGRATION DECISION" : "3. SIMULATED IMPACT"}
                    </span>
                    <span className="text-[10px] font-bold text-orange-400 uppercase tracking-wider">Deterministic Engine</span>
                  </div>
                  
                  {!simResult ? (
                    <div className="space-y-3">
                      <button onClick={() => handleSimulate(true)} disabled={simulating} className="w-full bg-purple-600 hover:bg-purple-500 text-white py-3 rounded font-semibold text-sm flex justify-center items-center gap-2 transition border border-purple-500/30">
                        {simulating ? <Activity className="animate-spin" size={16} /> : <span className="text-lg">✨</span>}
                        Simulate Migration (AI Architect)
                      </button>
                    </div>
                  ) : (
                    <div className="mt-4 space-y-6">
                      <div className="bg-[#0f172a]/80 border border-slate-700 p-5 rounded-lg">
                        <h3 className={classNames(
                          "text-lg font-bold mb-4 uppercase tracking-wider",
                          (simResult.risk_level === 'High' || simResult.risk_score > 70) ? 'text-red-400' : simResult.risk_level === 'Medium' ? 'text-yellow-400' : 'text-emerald-400'
                        )}>
                          {(simResult.risk_level === 'High' || simResult.risk_score > 70) ? 'MIGRATION BLOCKED' : simResult.risk_level === 'Medium' ? 'CONDITIONAL APPROVAL' : 'APPROVAL GRANTED'}
                        </h3>
                        
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <div className="text-[10px] text-slate-500 uppercase font-bold mb-1 tracking-wider">Key Metrics</div>
                            <div className="text-xs text-slate-300 space-y-1">
                              <div>Cost: ${selectedNode.cost_per_month} <span className={simResult.cost_delta_monthly > 0 ? "text-yellow-400" : "text-emerald-400"}>{simResult.cost_delta_monthly > 0 ? '+' : ''}${simResult.cost_delta_monthly}</span></div>
                              <div>Downtime: {simResult.estimated_downtime_minutes}m</div>
                            </div>
                          </div>
                          <div>
                            <div className="text-[10px] text-slate-500 uppercase font-bold mb-1 tracking-wider">Risk Overview</div>
                            <div className="text-xs text-slate-300">
                              <span className={simResult.risk_level === 'High' ? 'text-red-400 font-bold' : simResult.risk_level === 'Medium' ? 'text-yellow-400 font-bold' : 'text-emerald-400 font-bold'}>{simResult.risk_level} Risk</span>
                              <div>{simResult.affected_count} Components</div>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="bg-[#0f172a]/80 border border-blue-900/50 p-5 rounded-lg">
                        <h4 className="text-sm font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
                          <span className="text-purple-400 text-lg">✨</span> ARCHITECT'S RECOMMENDATION
                        </h4>
                        
                        <div className="text-sm text-slate-200 font-medium mb-4">
                           Proceed with {simResult.risk_level === 'High' ? 'extreme caution' : simResult.risk_level === 'Medium' ? 'phased migration' : 'standard migration'}
                        </div>
                        
                        <div className="text-[10px] text-slate-500 uppercase font-bold mb-1 tracking-wider">Why</div>
                        <p className="text-xs text-slate-400 leading-relaxed mb-6">
                          {simResult.architect_recommendation || simResult.ai_explanation || `Action 'migrate' initiated for change impact simulation. Impacts ${simResult.affected_count} components with a risk score of ${simResult.risk_score}/100.`}
                        </p>

                        <div className="text-[10px] text-slate-500 uppercase font-bold mb-3 tracking-wider">Recommended Actions</div>
                        <ul className="text-xs text-slate-300 space-y-3">
                          {simResult.recommended_actions && simResult.recommended_actions.length > 0 ? (
                            simResult.recommended_actions.map((action: string, idx: number) => (
                              <li key={idx} className="flex gap-3 items-start">
                                <span className="text-blue-400 font-mono text-[10px] mt-0.5">0{idx+1}</span>
                                <span className="leading-relaxed">{action}</span>
                              </li>
                            ))
                          ) : simResult.critical_flags && simResult.critical_flags.length > 0 ? (
                            simResult.critical_flags.map((flag: string, idx: number) => (
                              <li key={idx} className="flex gap-3 items-start">
                                <span className="text-blue-400 font-mono text-[10px] mt-0.5">0{idx+1}</span>
                                <span className="leading-relaxed">{flag}</span>
                              </li>
                            ))
                          ) : (
                            <>
                              <li className="flex gap-3 items-start"><span className="text-blue-400 font-mono text-[10px] mt-0.5">01</span><span className="leading-relaxed">Pre-change verification: Confirm health check status for {selectedNode.name}.</span></li>
                              <li className="flex gap-3 items-start"><span className="text-blue-400 font-mono text-[10px] mt-0.5">02</span><span className="leading-relaxed">Maintenance window: Coordinate execution during off-peak traffic hours to safeguard the {simResult.affected_count} affected component(s).</span></li>
                              <li className="flex gap-3 items-start"><span className="text-blue-400 font-mono text-[10px] mt-0.5">03</span><span className="leading-relaxed">Rollback plan: Ensure automated or documented rollback procedures are validated before applying 'migrate'.</span></li>
                              <li className="flex gap-3 items-start"><span className="text-blue-400 font-mono text-[10px] mt-0.5">04</span><span className="leading-relaxed">Downtime window: Prepare client notification for the anticipated {simResult.estimated_downtime_minutes}-minute service interruption.</span></li>
                            </>
                          )}
                        </ul>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
          </>
        )}
      </main>

      <ResourceFormModal 
        isOpen={isResourceModalOpen} 
        onClose={() => { setIsResourceModalOpen(false); setResourceToEdit(null); }} 
        onSave={fetchData} 
        existingResource={resourceToEdit}
        selectedEnv={selectedEnv}
      />
      
      <DependencyFormModal 
        isOpen={isDependencyModalOpen} 
        onClose={() => setIsDependencyModalOpen(false)} 
        onSave={fetchData} 
        components={rawComponents} 
        selectedEnv={selectedEnv}
        prefilledDependency={prefilledDependency}
      />
    </div>
  );
}
