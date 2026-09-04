import React, { useState, useEffect } from 'react';
import { X, Plus, Edit2, Sliders, Info, Globe } from 'lucide-react';
import { AWS_REGIONS } from '../utils/localization';

interface ManualResourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (resourceData: any) => Promise<void>;
  editResource?: any | null;
}

const RESOURCE_TYPES = [
  { value: 'server', label: 'Compute Server / EC2 Instance', icon: '💻' },
  { value: 'database', label: 'Managed Database / RDS Instance', icon: '🗄️' },
  { value: 'load_balancer', label: 'Load Balancer / ALB', icon: '⚖️' },
  { value: 'storage', label: 'Object Storage / S3 Bucket', icon: '🪣' },
  { value: 'vpc', label: 'Virtual Private Cloud (VPC)', icon: '🌐' },
  { value: 'subnet', label: 'VPC Subnet', icon: '🗺️' },
  { value: 'security_group', label: 'Security Group / Firewall', icon: '🛡️' },
  { value: 'application', label: 'Application Service / Container', icon: '📦' },
  { value: 'api', label: 'API Gateway / Ingress Route', icon: '🚪' },
  { value: 'identity', label: 'IAM Role / Identity', icon: '🔑' },
];

export const ManualResourceModal: React.FC<ManualResourceModalProps> = ({
  isOpen,
  onClose,
  onSave,
  editResource
}) => {
  const [name, setName] = useState('');
  const [customId, setCustomId] = useState('');
  const [type, setType] = useState('server');
  const [criticality, setCriticality] = useState('medium');
  const [environment, setEnvironment] = useState('cloud');
  const [location, setLocation] = useState('ap-south-1');
  const [costPerMonth, setCostPerMonth] = useState<number | ''>(4000);
  
  // Simulation Assumptions
  const [showAssumptions, setShowAssumptions] = useState(false);
  const [assumedCpu, setAssumedCpu] = useState<number | ''>('');
  const [assumedMemory, setAssumedMemory] = useState<number | ''>('');
  const [assumedLatency, setAssumedLatency] = useState<number | ''>('');
  const [assumedErrorRate, setAssumedErrorRate] = useState<number | ''>('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editResource) {
      setName(editResource.name || '');
      setCustomId(editResource.id || '');
      setType(editResource.type || 'server');
      setCriticality(editResource.criticality || 'medium');
      setEnvironment(editResource.environment || 'cloud');
      setLocation(editResource.location || 'ap-south-1');
      setCostPerMonth(editResource.cost_per_month ?? 4000);

      const assumptions = editResource.metadata_col?.assumptions || {};
      setAssumedCpu(assumptions.cpu ?? (editResource.cpu ?? ''));
      setAssumedMemory(assumptions.memory ?? (editResource.memory ?? ''));
      setAssumedLatency(assumptions.latency ?? '');
      setAssumedErrorRate(assumptions.error_rate ?? '');
      if (assumptions.cpu || assumptions.memory || assumptions.latency || assumptions.error_rate) {
        setShowAssumptions(true);
      }
    } else {
      setName('');
      setCustomId('');
      setType('server');
      setCriticality('medium');
      setEnvironment('cloud');
      setLocation('ap-south-1');
      setCostPerMonth(4000);
      setAssumedCpu('');
      setAssumedMemory('');
      setAssumedLatency('');
      setAssumedErrorRate('');
      setShowAssumptions(false);
    }
    setError(null);
  }, [editResource, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Please provide a resource name.');
      return;
    }

    setSubmitting(true);
    setError(null);

    const assumptionsPayload = (assumedCpu !== '' || assumedMemory !== '' || assumedLatency !== '' || assumedErrorRate !== '') ? {
      cpu: assumedCpu !== '' ? Number(assumedCpu) : null,
      memory: assumedMemory !== '' ? Number(assumedMemory) : null,
      latency: assumedLatency !== '' ? Number(assumedLatency) : null,
      error_rate: assumedErrorRate !== '' ? Number(assumedErrorRate) : null,
    } : null;

    const payload: any = {
      name: name.trim(),
      type,
      criticality,
      environment,
      location: location.trim() || 'us-east-1',
      cost_per_month: costPerMonth !== '' ? Number(costPerMonth) : 0,
      assumptions: assumptionsPayload
    };

    if (!editResource && customId.trim()) {
      payload.id = customId.trim();
    }

    try {
      await onSave(payload);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to save resource.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden my-8">
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-700 bg-slate-850">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-blue-500/20 text-blue-400 flex items-center justify-center font-bold">
              {editResource ? <Edit2 size={18} /> : <Plus size={20} />}
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">
                {editResource ? 'Edit Manual Resource' : 'Add Manual Infrastructure Resource'}
              </h2>
              <p className="text-xs text-slate-400">
                {editResource ? `Modify properties for ${editResource.name}` : 'Configure custom node for your Digital Twin'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-700 transition"
          >
            <X size={18} />
          </button>
        </div>

        {error && (
          <div className="mx-5 mt-4 p-3 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 text-xs flex items-center gap-2">
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          
          {/* Resource Name & ID */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Resource Name <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Auth API Service"
                required
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 font-medium"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Resource ID {editResource ? '(Locked)' : '(Optional)'}
              </label>
              <input
                type="text"
                value={customId}
                onChange={(e) => setCustomId(e.target.value)}
                disabled={!!editResource}
                placeholder="e.g. auth-api-node"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 font-mono disabled:opacity-50"
              />
            </div>
          </div>

          {/* Resource Type */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Resource Type
            </label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            >
              {RESOURCE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.icon} {t.label}
                </option>
              ))}
            </select>
          </div>

          {/* Criticality & Environment */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Criticality Tier
              </label>
              <select
                value={criticality}
                onChange={(e) => setCriticality(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 capitalize"
              >
                <option value="low">Low Criticality</option>
                <option value="medium">Medium Criticality</option>
                <option value="high">High Criticality</option>
                <option value="critical">Mission Critical</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Environment
              </label>
              <select
                value={environment}
                onChange={(e) => setEnvironment(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                <option value="cloud">Cloud (AWS)</option>
                <option value="on_prem">On-Premises / Hybrid</option>
              </select>
            </div>
          </div>

          {/* Region & Monthly Cost */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center gap-1">
                <Globe size={12} className="text-cyan-400" /> Target Region
              </label>
              <select
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
              >
                {['India', 'Asia Pacific', 'US', 'Europe', 'Middle East', 'Africa', 'Canada', 'South America'].map((grp) => (
                  <optgroup key={grp} label={`── ${grp} ──`}>
                    {AWS_REGIONS.filter((r) => r.group === grp).map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.displayName}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Configured Monthly Cost (INR)
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2 text-slate-400 text-sm font-semibold">₹</span>
                <input
                  type="number"
                  step="1"
                  min="0"
                  value={costPerMonth}
                  onChange={(e) => setCostPerMonth(e.target.value === '' ? '' : parseFloat(e.target.value))}
                  placeholder="4000"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-7 pr-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 font-mono"
                />
              </div>
              <span className="text-[10px] text-slate-500 mt-0.5 block">Configured in Indian Rupees (INR)</span>
            </div>
          </div>

          {/* Collapsible Simulation Assumptions */}
          <div className="border border-slate-700/80 rounded-xl overflow-hidden bg-slate-900/40">
            <button
              type="button"
              onClick={() => setShowAssumptions(!showAssumptions)}
              className="w-full p-3 flex items-center justify-between text-xs font-semibold text-slate-300 hover:bg-slate-700/40 transition"
            >
              <span className="flex items-center gap-2">
                <Sliders size={14} className="text-cyan-400" />
                <span>Simulation Assumptions (Optional User Input)</span>
              </span>
              <span className="text-[10px] text-cyan-400 uppercase font-mono">
                {showAssumptions ? 'Hide ▲' : 'Configure ▼'}
              </span>
            </button>

            {showAssumptions && (
              <div className="p-3 pt-1 border-t border-slate-700/60 space-y-3">
                <div className="text-[11px] text-slate-400 bg-slate-800/80 p-2.5 rounded-lg border border-slate-700 flex items-start gap-2">
                  <Info size={14} className="text-cyan-400 shrink-0 mt-0.5" />
                  <span>
                    These are user-configured baseline values used strictly for failure and degradation simulation. They are explicitly distinguished from real observed AWS CloudWatch telemetry.
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-0.5">Assumed CPU (%)</label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={assumedCpu}
                      onChange={(e) => setAssumedCpu(e.target.value === '' ? '' : parseFloat(e.target.value))}
                      placeholder="e.g. 65"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-0.5">Assumed Memory (%)</label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={assumedMemory}
                      onChange={(e) => setAssumedMemory(e.target.value === '' ? '' : parseFloat(e.target.value))}
                      placeholder="e.g. 50"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-0.5">Assumed Latency (ms)</label>
                    <input
                      type="number"
                      min="0"
                      value={assumedLatency}
                      onChange={(e) => setAssumedLatency(e.target.value === '' ? '' : parseFloat(e.target.value))}
                      placeholder="e.g. 120"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-0.5">Assumed Error Rate (%)</label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.1"
                      value={assumedErrorRate}
                      onChange={(e) => setAssumedErrorRate(e.target.value === '' ? '' : parseFloat(e.target.value))}
                      placeholder="e.g. 0.05"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-700">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-300 hover:bg-slate-700 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-xl text-xs font-bold text-white shadow-lg shadow-blue-900/30 transition flex items-center gap-1.5"
            >
              {submitting ? 'Saving...' : editResource ? 'Update Resource' : 'Add Resource'}
            </button>
          </div>

        </form>
      </div>
    </div>
  );
};
