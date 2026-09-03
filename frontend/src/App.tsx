import { useEffect, useState, useCallback } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
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
import { AlertTriangle, Clock, DollarSign, Activity, LayoutDashboard, Share2, Server, Cloud, HeartPulse, Monitor, Database, Network, HardDrive, Key, Plug, Box, Shield, ShieldAlert, ShieldCheck } from 'lucide-react';

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
  
  const envColor = data.environment === 'cloud' || data.environment === 'cloud_resource' 
    ? 'text-green-400' 
    : data.environment === 'on_prem' 
      ? 'text-yellow-400' 
      : 'text-slate-400';

  return (
    <div className={classNames(
      "px-4 py-2 shadow-lg rounded-md border-2 min-w-[160px] transition-all",
      selected ? "border-blue-500 bg-slate-800" : "border-slate-600 bg-slate-800",
      isBlastRadius && !selected ? "border-red-500 bg-red-950/40" : ""
    )}>
      <Handle type="target" position={Position.Top} className="w-2 h-2 bg-slate-400" />
      <div className="flex items-center space-x-2">
        <span className="text-blue-300 p-1 bg-slate-700 rounded-md">
          <IconComponent size={24} />
        </span>
        <div>
          <div className="text-sm font-bold text-white">{data.name}</div>
          <div className="text-xs capitalize text-slate-400">
            {data.type} • <span className={envColor}>{data.environment}</span>
          </div>
        </div>
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
  const [view, setView] = useState<'graph' | 'dashboard'>('graph');
  const [stats, setStats] = useState<any>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [loading, setLoading] = useState(true);
  
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [simResult, setSimResult] = useState<any>(null);
  const [simulating, setSimulating] = useState(false);

  const [healthData, setHealthData] = useState<any>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState(false);

  const [complianceData, setComplianceData] = useState<any>(null);
  const [complianceLoading, setComplianceLoading] = useState(false);

  const onConnect = useCallback(
    (params: Connection | Edge) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

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

    if (data.id && typeof data.id === 'string' && data.id.startsWith('aws_')) {
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
  }, [setNodes]);

  useEffect(() => {
    async function fetchData() {
      try {
        const [compsRes, depsRes, statsRes] = await Promise.all([
          fetch(`${API_BASE}/twin/components`),
          fetch(`${API_BASE}/twin/dependencies`),
          fetch(`${API_BASE}/twin/stats`)
        ]);
        
        const comps = await compsRes.json();
        const deps = await depsRes.json();
        const statsData = await statsRes.json();
        
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
          if (d.relationship_type === 'depends_on') edgeColor = '#3b82f6'; // blue-500
          else if (d.relationship_type === 'connects_to') edgeColor = '#10b981'; // emerald-500
          else if (d.relationship_type === 'hosted_on') edgeColor = '#f59e0b'; // amber-500
          else if (d.relationship_type === 'authenticates_via') edgeColor = '#8b5cf6'; // violet-500
          else if (d.relationship_type === 'stores_in') edgeColor = '#06b6d4'; // cyan-500

          return {
            id: d.id,
            source: d.source_id,
            target: d.target_id,
            animated: true,
            label: d.relationship_type.replace('_', ' '),
            style: { stroke: edgeColor, strokeWidth: 2 },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: edgeColor,
            },
          };
        });

        setNodes(newNodes);
        setEdges(newEdges);
      } catch (err) {
        console.error("Error fetching twin data", err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [setNodes, setEdges]);

  const handleSimulate = async () => {
    if (!selectedNode) return;
    setSimulating(true);
    
    try {
      const res = await fetch(`${API_BASE}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_component_id: selectedNode.id,
          action: "migrate",
          destination_env: "cloud"
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

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-200">
      <header className="p-4 border-b border-slate-700 flex justify-between items-center bg-slate-800 z-10">
        <div className="flex items-center gap-6">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-teal-400 bg-clip-text text-transparent">
            InfraTwin
          </h1>
          <nav className="flex gap-2">
            <button 
              onClick={() => setView('dashboard')}
              className={classNames("flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition", view === 'dashboard' ? "bg-slate-700 text-white" : "text-slate-400 hover:text-white")}
            >
              <LayoutDashboard size={16} /> Dashboard
            </button>
            <button 
              onClick={() => setView('graph')}
              className={classNames("flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition", view === 'graph' ? "bg-slate-700 text-white" : "text-slate-400 hover:text-white")}
            >
              <Share2 size={16} /> Digital Twin
            </button>
          </nav>
        </div>
        <div className="text-slate-400 text-sm">
          {view === 'graph' ? (selectedNode ? `Selected: ${selectedNode.name}` : 'Select a component to simulate change') : 'Executive View'}
        </div>
      </header>
      
      <main className="flex-1 relative flex overflow-hidden">
        {view === 'dashboard' ? (
          <div className="flex-1 overflow-y-auto p-8 bg-slate-900">
             <div className="max-w-6xl mx-auto">
                <h2 className="text-3xl font-bold text-white mb-8">Infrastructure Health & Risk</h2>
                
                {stats && (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
                    <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg">
                      <div className="flex items-center gap-3 mb-2 text-slate-400"><Server size={20} className="text-blue-400"/> Total Components</div>
                      <div className="text-4xl font-bold text-white">{stats.total_components}</div>
                    </div>
                    <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg">
                      <div className="flex items-center gap-3 mb-2 text-slate-400"><AlertTriangle size={20} className="text-red-400"/> Critical Services</div>
                      <div className="text-4xl font-bold text-white">{stats.critical_services_count}</div>
                    </div>
                    <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg">
                      <div className="flex items-center gap-3 mb-2 text-slate-400"><DollarSign size={20} className="text-emerald-400"/> Monthly Run Rate</div>
                      <div className="text-4xl font-bold text-white">${stats.total_monthly_cost.toLocaleString()}</div>
                    </div>
                    <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg flex flex-col justify-center">
                      <div className="flex items-center justify-between mb-2">
                        <span className="flex items-center gap-2 text-slate-400"><Server size={16}/> On-Prem</span>
                        <span className="font-bold text-white">{stats.on_prem_count}</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-2 mb-4">
                        <div className="bg-slate-500 h-2 rounded-full" style={{ width: `${(stats.on_prem_count/stats.total_components)*100}%`}}></div>
                      </div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="flex items-center gap-2 text-slate-400"><Cloud size={16}/> Cloud</span>
                        <span className="font-bold text-white">{stats.cloud_count}</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-2">
                        <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${(stats.cloud_count/stats.total_components)*100}%`}}></div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="bg-slate-800 p-8 rounded-xl border border-slate-700 shadow-lg flex items-center gap-6">
                  <div className="p-4 bg-emerald-900/30 text-emerald-400 rounded-full">
                    <HeartPulse size={48} />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white mb-2">Infrastructure is Stable</h3>
                    <p className="text-slate-400">All core applications and databases are currently operating normally. No active critical outages detected. Switch to the Digital Twin tab to run proactive risk simulations before making changes.</p>
                  </div>
                </div>
             </div>
          </div>
        ) : (
          <>
            <div className="flex-1 relative">
              {loading ? (
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="animate-pulse text-lg text-slate-400">Loading infrastructure...</span>
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
                  className="bg-slate-900"
                >
                  <Controls className="bg-slate-800 text-white fill-white border-slate-700" />
                  <MiniMap className="bg-slate-800" nodeColor="#334155" maskColor="rgba(15, 23, 42, 0.7)" />
                  <Background color="#334155" gap={16} />
                  
                  <Panel position="bottom-left" className="bg-slate-800 p-4 rounded-lg shadow-lg border border-slate-700">
                    <h4 className="text-sm font-bold text-white mb-2">Dependency Legend</h4>
                    <div className="flex flex-col gap-2 text-xs">
                      <div className="flex items-center gap-2"><div className="w-4 h-1 bg-blue-500 rounded"></div> <span className="text-slate-300">Depends On</span></div>
                      <div className="flex items-center gap-2"><div className="w-4 h-1 bg-emerald-500 rounded"></div> <span className="text-slate-300">Connects To</span></div>
                      <div className="flex items-center gap-2"><div className="w-4 h-1 bg-amber-500 rounded"></div> <span className="text-slate-300">Hosted On</span></div>
                      <div className="flex items-center gap-2"><div className="w-4 h-1 bg-violet-500 rounded"></div> <span className="text-slate-300">Authenticates Via</span></div>
                      <div className="flex items-center gap-2"><div className="w-4 h-1 bg-cyan-500 rounded"></div> <span className="text-slate-300">Stores In</span></div>
                    </div>
                  </Panel>
                </ReactFlow>
              )}
            </div>

            {/* Simulation Sidebar */}
            <div className={classNames(
              "w-[400px] bg-slate-800 border-l border-slate-700 p-6 flex flex-col gap-6 transition-transform shadow-xl shrink-0 overflow-y-auto",
              selectedNode ? "translate-x-0" : "translate-x-full hidden"
            )}>
              {selectedNode && (
                <>
                  <div>
                    <h2 className="text-xl font-bold text-white mb-1">{selectedNode.name}</h2>
                    <div className="text-sm text-slate-400 capitalize">{selectedNode.type} • {selectedNode.environment}</div>
                    <div className="mt-4 flex gap-2">
                      <span className="px-2 py-1 bg-slate-700 rounded text-xs font-medium text-slate-300">Crit: {selectedNode.criticality}</span>
                      <span className="px-2 py-1 bg-slate-700 rounded text-xs font-medium text-slate-300">Cost: ${selectedNode.cost_per_month}/mo</span>
                    </div>
                  </div>

                  {/* CloudWatch Health Section */}
                  {selectedNode.id && selectedNode.id.startsWith('aws_') && (
                    <div className="border-t border-slate-700 pt-4">
                      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-white">
                        <Cloud size={18} className="text-blue-400" />
                        CloudWatch Health
                      </h3>
                      
                      {healthLoading ? (
                        <div className="flex items-center gap-2 text-slate-400 text-sm">
                          <Activity className="animate-spin" size={16} /> Loading metrics...
                        </div>
                      ) : healthError ? (
                        <div className="text-red-400 text-sm flex items-center gap-2 bg-red-950/40 p-3 rounded border border-red-900/50">
                          <AlertTriangle size={16} /> CloudWatch data unavailable
                        </div>
                      ) : healthData ? (
                        <div className="bg-slate-700/30 border border-slate-600 rounded-lg p-4 space-y-3 shadow-inner">
                          <div className="flex justify-between items-center text-sm">
                            <span className="text-slate-400">Status</span>
                            <span className={classNames("font-semibold capitalize", healthData.status === 'healthy' ? 'text-emerald-400' : 'text-amber-400')}>
                              {healthData.status}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-sm">
                            <span className="text-slate-400">CPU Utilization</span>
                            <span className="font-semibold text-white">
                              {healthData.metrics?.cpu_utilization != null ? `${healthData.metrics.cpu_utilization}%` : '—'}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-sm">
                            <span className="text-slate-400">Memory Utilization</span>
                            <span className="font-semibold text-white">
                              {healthData.metrics?.memory_utilization != null ? `${healthData.metrics.memory_utilization} MB` : '—'}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-sm border-t border-slate-600 pt-3 mt-3">
                            <span className="text-slate-400">Active Alarms</span>
                            <span className={classNames("font-semibold", healthData.alarms?.length > 0 ? "text-red-400" : "text-emerald-400")}>
                              {healthData.alarms?.length || 0}
                            </span>
                          </div>
                          {healthData.alarms?.length > 0 && (
                            <ul className="text-xs text-red-300 space-y-1 mt-2">
                              {healthData.alarms.map((al: string, i: number) => (
                                <li key={i}>• {al}</li>
                              ))}
                            </ul>
                          )}
                          <div className="text-[10px] text-slate-500 mt-3 pt-2 border-t border-slate-700/50 text-right uppercase tracking-wider font-semibold">
                            Source: Amazon CloudWatch
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}

                  {/* Config Compliance Section */}
                  {selectedNode.id && selectedNode.id.startsWith('aws_') && (
                    <div className="border-t border-slate-700 pt-4">
                      <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-white">
                        <Shield size={18} className="text-violet-400" />
                        Security & Compliance
                      </h3>
                      
                      {complianceLoading ? (
                        <div className="flex items-center gap-2 text-slate-400 text-sm">
                          <Activity className="animate-spin" size={16} /> Verifying compliance...
                        </div>
                      ) : complianceData ? (
                        <div className="bg-slate-700/30 border border-slate-600 rounded-lg p-4 space-y-3 shadow-inner">
                          {complianceData.status === 'NO_RULES_EVALUATED' || complianceData.status === 'NOT_APPLICABLE' ? (
                            <div className="text-sm text-slate-400">No Config rules evaluated for this resource.</div>
                          ) : complianceData.status === 'ERROR' ? (
                            <div className="text-sm text-red-400">Error retrieving compliance data.</div>
                          ) : (
                            <>
                              <div className="flex justify-between items-center text-sm">
                                <span className="text-slate-400">Overall Status</span>
                                <span className={classNames("font-bold flex items-center gap-1", 
                                  complianceData.status === 'COMPLIANT' ? 'text-emerald-400' : 'text-red-400'
                                )}>
                                  {complianceData.status === 'COMPLIANT' ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
                                  {complianceData.status}
                                </span>
                              </div>
                              {complianceData.rules?.length > 0 && (
                                <div className="mt-3 pt-3 border-t border-slate-600 space-y-2">
                                  <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-2">Evaluated Rules</div>
                                  {complianceData.rules.map((rule: any, idx: number) => (
                                    <div key={idx} className="flex items-start justify-between gap-2 text-xs">
                                      <span className="text-slate-300 break-words">{rule.rule_name}</span>
                                      <span className={classNames("font-semibold shrink-0", 
                                        rule.compliance === 'COMPLIANT' ? 'text-emerald-400' : 'text-red-400'
                                      )}>
                                        {rule.compliance}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </>
                          )}
                          <div className="text-[10px] text-slate-500 mt-3 pt-2 border-t border-slate-700/50 text-right uppercase tracking-wider font-semibold">
                            Source: AWS Config
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}

                  <div className="border-t border-slate-700 pt-4">
                    <h3 className="text-lg font-semibold mb-3">Simulate Change</h3>
                    <p className="text-sm text-slate-400 mb-4">
                      Test the impact of migrating this component to the Cloud.
                    </p>
                    <button 
                      onClick={handleSimulate}
                      disabled={simulating}
                      className="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-md font-semibold transition flex items-center justify-center gap-2 shadow-lg shadow-blue-900/20"
                    >
                      {simulating ? <Activity className="animate-spin" size={18} /> : <Activity size={18} />}
                      Run Simulation
                    </button>
                  </div>

                  {simResult && (
                    <div className="border-t border-slate-700 pt-6 flex-1 flex flex-col">
                      <h3 className="text-lg font-semibold mb-4 text-white">Simulation Results</h3>
                      
                      <div className="grid grid-cols-2 gap-3 mb-6">
                        <div className="bg-slate-700/50 p-4 rounded-lg border border-slate-600">
                          <div className="text-slate-400 text-xs mb-1 flex items-center gap-1"><AlertTriangle size={12}/> Risk Score</div>
                          <div className={classNames(
                            "text-2xl font-bold",
                            simResult.risk_level === 'CRITICAL' ? 'text-red-400' :
                            simResult.risk_level === 'HIGH' ? 'text-orange-400' : 'text-yellow-400'
                          )}>
                            {simResult.risk_score} <span className="text-sm font-normal text-slate-500">/ 100</span>
                          </div>
                        </div>
                        
                        <div className="bg-slate-700/50 p-4 rounded-lg border border-slate-600">
                          <div className="text-slate-400 text-xs mb-1 flex items-center gap-1"><Clock size={12}/> Est. Downtime</div>
                          <div className="text-2xl font-bold text-white">
                            {simResult.estimated_downtime_minutes} <span className="text-sm font-normal text-slate-500">min</span>
                          </div>
                        </div>

                        <div className="bg-slate-700/50 p-4 rounded-lg border border-slate-600">
                          <div className="text-slate-400 text-xs mb-1 flex items-center gap-1"><AlertTriangle size={12}/> Blast Radius</div>
                          <div className="text-2xl font-bold text-red-400">
                            {simResult.affected_count} <span className="text-sm font-normal text-slate-500">nodes</span>
                          </div>
                        </div>

                        <div className="bg-slate-700/50 p-4 rounded-lg border border-slate-600">
                          <div className="text-slate-400 text-xs mb-1 flex items-center gap-1"><DollarSign size={12}/> Cost Delta</div>
                          <div className="text-2xl font-bold text-emerald-400">
                            +${simResult.cost_delta_monthly.toFixed(0)}<span className="text-sm font-normal text-slate-500">/mo</span>
                          </div>
                        </div>
                      </div>

                      {simResult.critical_flags?.length > 0 && (
                        <div className="mb-6">
                          <h4 className="text-sm font-semibold text-slate-300 mb-2">Critical Warnings</h4>
                          <ul className="space-y-2">
                            {simResult.critical_flags.map((flag: string, idx: number) => (
                              <li key={idx} className="bg-red-950/40 border border-red-900/50 text-red-200 text-sm p-3 rounded-lg flex items-start gap-2 shadow-sm">
                                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-400" />
                                {flag}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {simResult.financial_analysis && (
                        <div className="mt-4 mb-4 space-y-4">
                          <h4 className="text-sm font-semibold text-blue-400 flex items-center gap-2">
                            <span className="text-lg">🤖</span> Multi-Agent Analysis
                          </h4>
                          
                          <div className="bg-slate-700/30 border border-emerald-900/50 p-4 rounded-xl text-sm shadow-inner">
                            <h5 className="font-semibold text-emerald-400 mb-2 flex items-center gap-2"><DollarSign size={16}/> Financial Analyst Agent</h5>
                            <p className="text-slate-300 leading-relaxed">{simResult.financial_analysis}</p>
                          </div>
                          
                          <div className="bg-slate-700/30 border border-red-900/50 p-4 rounded-xl text-sm shadow-inner">
                            <h5 className="font-semibold text-red-400 mb-2 flex items-center gap-2"><AlertTriangle size={16}/> Security & Risk Agent</h5>
                            <p className="text-slate-300 leading-relaxed">{simResult.risk_analysis}</p>
                          </div>
                          
                          <div className="bg-slate-700/30 border border-blue-900/50 p-5 rounded-xl text-sm shadow-inner">
                            <h5 className="font-semibold text-blue-400 mb-2 flex items-center gap-2"><LayoutDashboard size={16}/> Lead Cloud Architect (Synthesis)</h5>
                            <p className="text-white font-medium leading-relaxed">{simResult.architect_recommendation}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
