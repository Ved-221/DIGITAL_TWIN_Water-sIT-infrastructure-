import React, { useState } from 'react';
import { 
  X, Sparkles, FileCode2, ArrowRight, ArrowLeft, CheckCircle2, 
  AlertTriangle, Layers, Server, RefreshCw, Info, Database, 
  Cpu, HardDrive, Share2, ShieldAlert
} from 'lucide-react';
import { twinApi } from '../api/twinApi';
import type { 
  ParsedDigitalTwinPreview, 
  ParsedComponentPreview, 
  ParsedDependencyPreview,
  ApplyParsedTwinResponse 
} from '../types/twin';

interface BuildTwinModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTwinCreated: (result: ApplyParsedTwinResponse) => void;
}

const DOMAIN_OPTIONS = [
  { value: 'general', label: 'General IT / Heterogeneous Systems' },
  { value: 'cloud', label: 'Cloud & Web Microservices' },
  { value: 'water', label: 'Water & Utilities Distribution' },
  { value: 'manufacturing', label: 'Manufacturing & Industrial SCADA' },
  { value: 'healthcare', label: 'Healthcare & Hospital Informatics' },
  { value: 'banking', label: 'Banking & Financial Core Services' },
];

const EXAMPLE_TEMPLATES = [
  {
    label: 'Cloud Web Architecture',
    domain: 'cloud',
    text: 'Two application servers behind an Application Load Balancer. Both application servers connect to a PostgreSQL database. PostgreSQL connects to an S3 backup storage.',
  },
  {
    label: 'Water Utility Infrastructure',
    domain: 'water',
    text: 'SCADA monitoring workstation connects to high service pump station PLC controller. The PLC controller receives signals from flow meter sensor and pressure valve. SCADA workstation connects to central operational database.',
  },
  {
    label: 'Manufacturing Conveyor Line',
    domain: 'manufacturing',
    text: 'PLC master controller connects to conveyor motor drive and robotic sorting arm. Robotic arm connects to quality vision camera. Master controller reports status to manufacturing execution server.',
  },
];

const DEFAULT_STRUCTURED_JSON = JSON.stringify(
  {
    domain: 'cloud',
    components: [
      { name: 'Application Load Balancer', type: 'load_balancer', criticality: 'high', cost_per_month: 25 },
      { name: 'Web Server Alpha', type: 'server', criticality: 'high', cost_per_month: 50 },
      { name: 'Web Server Beta', type: 'server', criticality: 'high', cost_per_month: 50 },
      { name: 'PostgreSQL Database', type: 'database', criticality: 'critical', cost_per_month: 120 }
    ],
    dependencies: [
      { source_name: 'Application Load Balancer', target_name: 'Web Server Alpha', relationship_type: 'routes_traffic_to' },
      { source_name: 'Application Load Balancer', target_name: 'Web Server Beta', relationship_type: 'routes_traffic_to' },
      { source_name: 'Web Server Alpha', target_name: 'PostgreSQL Database', relationship_type: 'database_connection' },
      { source_name: 'Web Server Beta', target_name: 'PostgreSQL Database', relationship_type: 'database_connection' }
    ]
  },
  null,
  2
);

export const BuildTwinModal: React.FC<BuildTwinModalProps> = ({
  isOpen,
  onClose,
  onTwinCreated,
}) => {
  const [activeTab, setActiveTab] = useState<'describe' | 'structured'>('describe');
  const [step, setStep] = useState<'define' | 'review'>('define');
  
  // Define step inputs
  const [domain, setDomain] = useState('general');
  const [description, setDescription] = useState('');
  const [structuredJson, setStructuredJson] = useState(DEFAULT_STRUCTURED_JSON);
  const [clearExisting, setClearExisting] = useState(true);

  // Review step state
  const [parsedPreview, setParsedPreview] = useState<ParsedDigitalTwinPreview | null>(null);
  const [structuredPreviewData, setStructuredPreviewData] = useState<{
    domain: string;
    components: ParsedComponentPreview[];
    dependencies: ParsedDependencyPreview[];
    rawPayload: { components: any[]; dependencies: any[] };
  } | null>(null);

  // Status & Error
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleReset = () => {
    setStep('define');
    setError(null);
    setParsedPreview(null);
    setStructuredPreviewData(null);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  // Step 1 -> Step 2: Parse Natural Language Description
  const handleParseDescription = async () => {
    if (!description.trim()) {
      setError('Please provide a system description to parse.');
      return;
    }

    setLoading(true);
    setLoadingMessage('Analyzing system description & extracting topology...');
    setError(null);

    try {
      const preview = await twinApi.parseDescription({
        description: description.trim(),
        domain: domain || 'general',
      });

      if (!preview.components || preview.components.length === 0) {
        throw new Error('No components could be identified in the text. Try naming specific entities (e.g. servers, databases, sensors, controllers).');
      }

      setParsedPreview(preview);
      setStructuredPreviewData(null);
      setStep('review');
    } catch (err: any) {
      setError(err?.message || 'Failed to parse system description.');
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  // Step 1 -> Step 2: Validate Structured JSON Input
  const handleValidateStructured = () => {
    setError(null);
    try {
      const parsed = JSON.parse(structuredJson);
      if (!parsed || typeof parsed !== 'object') {
        throw new Error('JSON payload must be an object with "components" and "dependencies" arrays.');
      }
      if (!Array.isArray(parsed.components) || parsed.components.length === 0) {
        throw new Error('"components" must be a non-empty array of component definitions.');
      }

      const targetDomain = parsed.domain || domain || 'general';

      const previewComponents: ParsedComponentPreview[] = parsed.components.map((c: any, idx: number) => ({
        temp_id: c.id || c.temp_id || `comp_${idx + 1}`,
        name: c.name || `Component ${idx + 1}`,
        type: c.type || 'application',
        domain: c.domain || targetDomain,
        status: c.status || 'active',
        criticality: c.criticality || 'medium',
        properties: c.properties || {},
        metrics: c.metrics || null,
        metadata: c.metadata || {},
        source: 'manual_structured',
        source_id: c.source_id || c.arn || null,
        raw_mention: c.name || null,
      }));

      const previewDeps: ParsedDependencyPreview[] = (parsed.dependencies || []).map((d: any, idx: number) => ({
        source_temp_id: d.source_temp_id || d.source_id || d.source_name || `src_${idx}`,
        target_temp_id: d.target_temp_id || d.target_id || d.target_name || `tgt_${idx}`,
        source_name: d.source_name || d.source || d.source_component_id || 'Source',
        target_name: d.target_name || d.target || d.target_component_id || 'Target',
        relationship_type: d.relationship_type || d.type || 'connects_to',
        source: 'manual_structured',
        explicit_quote: d.explicit_quote || null,
        metadata: d.metadata || {},
      }));

      setStructuredPreviewData({
        domain: targetDomain,
        components: previewComponents,
        dependencies: previewDeps,
        rawPayload: {
          components: parsed.components,
          dependencies: parsed.dependencies || [],
        },
      });
      setParsedPreview(null);
      setStep('review');
    } catch (err: any) {
      setError(err?.message || 'Invalid structured JSON format.');
    }
  };

  // Step 2 -> Step 3: Create Digital Twin in Backend
  const handleCreateTwin = async () => {
    setLoading(true);
    setLoadingMessage('Creating Digital Twin & initializing dependency graph...');
    setError(null);

    try {
      let result: ApplyParsedTwinResponse;

      if (activeTab === 'describe' && parsedPreview) {
        result = await twinApi.applyParsedTwin({
          domain: parsedPreview.domain || domain,
          components: parsedPreview.components,
          dependencies: parsedPreview.dependencies,
          clear_existing: clearExisting,
        });
      } else if (activeTab === 'structured' && structuredPreviewData) {
        result = await twinApi.applyStructuredTwin({
          domain: structuredPreviewData.domain,
          components: structuredPreviewData.rawPayload.components,
          dependencies: structuredPreviewData.rawPayload.dependencies,
          clear_existing: clearExisting,
        });
      } else {
        throw new Error('No valid preview available to commit.');
      }

      onTwinCreated(result);
      handleClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to create Digital Twin.');
    } finally {
      setLoading(false);
      setLoadingMessage('');
    }
  };

  // Active items for review display
  const activeComponents = parsedPreview?.components || structuredPreviewData?.components || [];
  const activeDependencies = parsedPreview?.dependencies || structuredPreviewData?.dependencies || [];
  const activeAmbiguities = parsedPreview?.ambiguities || [];
  const activeDomain = parsedPreview?.domain || structuredPreviewData?.domain || domain;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700/90 rounded-2xl w-full max-w-3xl shadow-2xl overflow-hidden my-6 flex flex-col max-h-[90vh]">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-600 text-white flex items-center justify-center font-bold shadow-md shadow-blue-500/20">
              <Layers size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                <span>Build Digital Twin</span>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800">
                  Domain-Agnostic
                </span>
              </h2>
              <p className="text-xs text-slate-400">Describe physical, cloud, or industrial architecture to generate the Twin</p>
            </div>
          </div>

          <button
            onClick={handleClose}
            disabled={loading}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            title="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        {/* 3-Step Mental Model Progress Bar */}
        <div className="px-6 py-2.5 bg-slate-950/50 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className={`w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] ${
              step === 'define' ? 'bg-blue-600 text-white' : 'bg-emerald-600 text-white'
            }`}>
              {step === 'define' ? '1' : '✓'}
            </span>
            <span className={step === 'define' ? 'text-white font-semibold' : 'text-slate-300'}>
              1. Define System
            </span>
          </div>

          <div className="h-0.5 w-12 bg-slate-800" />

          <div className="flex items-center gap-2">
            <span className={`w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] ${
              step === 'review' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-500'
            }`}>
              2
            </span>
            <span className={step === 'review' ? 'text-white font-semibold' : 'text-slate-500'}>
              2. Review Topology
            </span>
          </div>

          <div className="h-0.5 w-12 bg-slate-800" />

          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] bg-slate-800 text-slate-500">
              3
            </span>
            <span className="text-slate-500">
              3. Generate Twin
            </span>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="px-6 py-3 bg-red-950/90 border-b border-red-800/80 text-xs text-red-200 flex items-start gap-2.5">
            <AlertTriangle size={16} className="text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <span className="font-semibold block">Validation Error</span>
              <span>{error}</span>
            </div>
            <button onClick={() => setError(null)} className="text-red-300 hover:text-white">
              <X size={14} />
            </button>
          </div>
        )}

        {/* Modal Body Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">

          {/* STEP 1: DEFINE SYSTEM */}
          {step === 'define' && (
            <div className="space-y-5">
              
              {/* Tab Selector */}
              <div className="flex rounded-xl p-1 bg-slate-950 border border-slate-800 max-w-sm">
                <button
                  type="button"
                  onClick={() => setActiveTab('describe')}
                  className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                    activeTab === 'describe' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Sparkles size={13} />
                  <span>Natural Language</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('structured')}
                  className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                    activeTab === 'structured' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <FileCode2 size={13} />
                  <span>Structured JSON</span>
                </button>
              </div>

              {/* Domain Selector */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  System Domain / Operational Context
                </label>
                <select
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                >
                  {DOMAIN_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* TAB A: Natural Language Description */}
              {activeTab === 'describe' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-300">
                      System Description
                    </label>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Domain-neutral NLP Parser
                    </span>
                  </div>

                  <textarea
                    rows={6}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe components, servers, databases, sensors, and their communication paths. Example: Two application servers behind an ALB. Both connect to PostgreSQL. PostgreSQL connects to an S3 backup storage."
                    className="w-full bg-slate-950 border border-slate-700/80 rounded-xl p-3.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 leading-relaxed font-sans"
                  />

                  {/* Template Quick Selectors */}
                  <div>
                    <span className="text-[11px] text-slate-400 block mb-1.5 font-medium">
                      Load an architecture template:
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {EXAMPLE_TEMPLATES.map((ex, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => {
                            setDescription(ex.text);
                            setDomain(ex.domain);
                          }}
                          className="px-2.5 py-1 bg-slate-800 hover:bg-slate-750 text-slate-300 hover:text-white border border-slate-700 rounded-lg text-[11px] transition flex items-center gap-1.5"
                        >
                          <span className="text-cyan-400">⚡</span>
                          <span>{ex.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB B: Structured JSON Input */}
              {activeTab === 'structured' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-300">
                      Structured Twin Specification (JSON)
                    </label>
                    <button
                      type="button"
                      onClick={() => setStructuredJson(DEFAULT_STRUCTURED_JSON)}
                      className="text-[11px] text-cyan-400 hover:underline flex items-center gap-1"
                    >
                      <RefreshCw size={11} /> Reset Template
                    </button>
                  </div>

                  <textarea
                    rows={9}
                    value={structuredJson}
                    onChange={(e) => setStructuredJson(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700/80 rounded-xl p-3.5 text-xs text-cyan-300 font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 leading-relaxed"
                  />
                </div>
              )}

              {/* Clear Existing Checkbox */}
              <div className="pt-2 border-t border-slate-800">
                <label className="flex items-center gap-2.5 text-xs text-slate-300 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={clearExisting}
                    onChange={(e) => setClearExisting(e.target.checked)}
                    className="rounded border-slate-700 bg-slate-950 text-blue-600 focus:ring-0 w-4 h-4 cursor-pointer"
                  />
                  <span>Clear previous components and start with a clean Digital Twin slate</span>
                </label>
              </div>

            </div>
          )}

          {/* STEP 2: REVIEW TOPOLOGY PREVIEW */}
          {step === 'review' && (
            <div className="space-y-5">
              
              {/* Trust & Provenance Notice */}
              <div className="p-3 bg-blue-950/40 border border-blue-800/60 rounded-xl text-xs text-blue-200 flex items-start gap-2.5">
                <Info size={16} className="text-cyan-400 shrink-0 mt-0.5" />
                <div className="space-y-0.5 leading-relaxed">
                  <span className="font-bold text-white block">Deterministic Extraction Verified</span>
                  <span>
                    Review detected components and relationships before creating the Twin. The system constructs deterministic graphs and does not silently invent connections.
                  </span>
                </div>
              </div>

              {/* Ambiguity Warnings (if any) */}
              {activeAmbiguities.length > 0 && (
                <div className="p-3 bg-amber-950/40 border border-amber-800/60 rounded-xl text-xs text-amber-200 space-y-1.5">
                  <div className="flex items-center gap-2 font-bold text-amber-300">
                    <ShieldAlert size={15} />
                    <span>Ambiguity Warnings Detected ({activeAmbiguities.length})</span>
                  </div>
                  <ul className="list-disc list-inside space-y-1 text-slate-300 text-[11px]">
                    {activeAmbiguities.map((amb, i) => (
                      <li key={i}>{amb}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* System Summary KPI Pill Bar */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800 text-center">
                  <span className="text-[10px] uppercase text-slate-400 block font-medium">Domain</span>
                  <span className="text-sm font-bold text-white capitalize">{activeDomain}</span>
                </div>
                <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800 text-center">
                  <span className="text-[10px] uppercase text-slate-400 block font-medium">Components</span>
                  <span className="text-sm font-bold text-cyan-400">{activeComponents.length}</span>
                </div>
                <div className="bg-slate-950/80 p-3 rounded-xl border border-slate-800 text-center">
                  <span className="text-[10px] uppercase text-slate-400 block font-medium">Dependencies</span>
                  <span className="text-sm font-bold text-purple-400">{activeDependencies.length}</span>
                </div>
              </div>

              {/* Components List */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                  <span className="flex items-center gap-1.5">
                    <Server size={14} className="text-cyan-400" />
                    <span>Parsed Components ({activeComponents.length})</span>
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
                  {activeComponents.map((c, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 bg-slate-950/60 border border-slate-800 rounded-xl flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-2 overflow-hidden">
                        <div className="w-6 h-6 rounded bg-slate-800 flex items-center justify-center text-slate-300 shrink-0 font-mono text-[10px]">
                          {c.type === 'database' ? <Database size={13} className="text-amber-400" /> :
                           c.type === 'storage' ? <HardDrive size={13} className="text-purple-400" /> :
                           c.type === 'load_balancer' ? <Share2 size={13} className="text-cyan-400" /> :
                           <Cpu size={13} className="text-blue-400" />}
                        </div>
                        <div className="overflow-hidden">
                          <span className="font-semibold text-white block truncate">{c.name}</span>
                          <span className="text-[10px] text-slate-400 capitalize">{c.type?.replace('_', ' ')}</span>
                        </div>
                      </div>
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono shrink-0 ml-2">
                        {c.criticality || 'medium'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Dependencies List */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
                  <span className="flex items-center gap-1.5">
                    <Share2 size={14} className="text-purple-400" />
                    <span>Discovered Dependencies ({activeDependencies.length})</span>
                  </span>
                </div>

                {activeDependencies.length === 0 ? (
                  <div className="p-3 bg-slate-950/40 rounded-xl border border-slate-800 text-xs text-slate-400 italic">
                    No explicit dependency relationships extracted. Components will be placed as independent nodes.
                  </div>
                ) : (
                  <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
                    {activeDependencies.map((d, idx) => (
                      <div
                        key={idx}
                        className="p-2 bg-slate-950/60 border border-slate-800 rounded-xl flex items-center justify-between text-xs font-mono"
                      >
                        <div className="flex items-center gap-2 text-slate-200">
                          <span className="font-semibold text-white">{d.source_name}</span>
                          <span className="text-slate-500">→</span>
                          <span className="text-cyan-300 text-[11px] px-1.5 py-0.5 rounded bg-slate-800">
                            {d.relationship_type?.replace(/_/g, ' ')}
                          </span>
                          <span className="text-slate-500">→</span>
                          <span className="font-semibold text-white">{d.target_name}</span>
                        </div>
                        {d.explicit_quote && (
                          <span className="text-[9px] text-slate-500 italic max-w-[150px] truncate" title={d.explicit_quote}>
                            "{d.explicit_quote}"
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

            </div>
          )}

        </div>

        {/* Modal Footer Controls */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/90 flex items-center justify-between">
          {step === 'define' ? (
            <>
              <button
                type="button"
                onClick={handleClose}
                disabled={loading}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={activeTab === 'describe' ? handleParseDescription : handleValidateStructured}
                disabled={loading}
                className="px-5 py-2.5 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white rounded-xl text-xs font-bold transition flex items-center gap-2 shadow-lg shadow-blue-900/30 disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    <span>{loadingMessage || 'Analyzing...'}</span>
                  </>
                ) : (
                  <>
                    <span>Parse & Preview Topology</span>
                    <ArrowRight size={14} />
                  </>
                )}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setStep('define')}
                disabled={loading}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition flex items-center gap-1.5"
              >
                <ArrowLeft size={14} />
                <span>Back to Edit</span>
              </button>

              <button
                type="button"
                onClick={handleCreateTwin}
                disabled={loading || activeComponents.length === 0}
                className="px-6 py-2.5 bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white rounded-xl text-xs font-bold transition flex items-center gap-2 shadow-lg shadow-emerald-950/40 disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    <span>{loadingMessage || 'Creating Digital Twin...'}</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={15} />
                    <span>Create Digital Twin</span>
                  </>
                )}
              </button>
            </>
          )}
        </div>

      </div>
    </div>
  );
};
