import React, { useState, useEffect } from 'react';
import { X, Share2, ArrowRight, ShieldAlert } from 'lucide-react';

interface ManualDependencyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (depData: any) => Promise<void>;
  components: any[];
  initialSourceId?: string | null;
  initialTargetId?: string | null;
}

const RELATIONSHIP_TYPES = [
  { value: 'routes_traffic_to', label: 'Routes Traffic To (e.g. ALB → Server / Server → Service)' },
  { value: 'database_connection', label: 'Database Connection (e.g. Server → RDS / DB)' },
  { value: 'storage_access', label: 'Storage Access (e.g. Server → S3 Bucket)' },
  { value: 'member_of_vpc', label: 'Member of VPC (e.g. Subnet → VPC)' },
  { value: 'enclosed_in_subnet', label: 'Enclosed in Subnet (e.g. Server → Subnet)' },
  { value: 'protected_by_security_group', label: 'Protected by Security Group' },
  { value: 'connects_to', label: 'Generic Dependency (Connects To)' },
];

export const ManualDependencyModal: React.FC<ManualDependencyModalProps> = ({
  isOpen,
  onClose,
  onSave,
  components,
  initialSourceId,
  initialTargetId,
}) => {
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [relationshipType, setRelationshipType] = useState('routes_traffic_to');
  const [criticality, setCriticality] = useState('medium');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (components.length > 0) {
      setSourceId(initialSourceId || components[0]?.id || '');
      setTargetId(initialTargetId || (components.length > 1 ? components[1]?.id : components[0]?.id) || '');
    }
    setRelationshipType('routes_traffic_to');
    setCriticality('medium');
    setError(null);
  }, [isOpen, initialSourceId, initialTargetId, components]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceId || !targetId) {
      setError('Please select both a source and target resource.');
      return;
    }
    if (sourceId === targetId) {
      setError('A resource cannot depend on itself (source and target must be different).');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await onSave({
        source_component_id: sourceId,
        target_component_id: targetId,
        relationship_type: relationshipType,
        criticality
      });
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to create dependency.');
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
            <div className="w-9 h-9 rounded-xl bg-purple-500/20 text-purple-400 flex items-center justify-center font-bold">
              <Share2 size={18} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white">Connect Infrastructure Resources</h2>
              <p className="text-xs text-slate-400">Define a verified dependency edge for the Digital Twin</p>
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
            <ShieldAlert size={15} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          
          {/* Source & Target Dropdowns */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-center">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Source Resource (Origin)
              </label>
              <select
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                required
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                {components.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.type})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Target Resource (Destination)
              </label>
              <select
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                required
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                {components.map((c) => (
                  <option key={c.id} value={c.id} disabled={c.id === sourceId}>
                    {c.name} ({c.type}) {c.id === sourceId ? '(Cannot self-loop)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Relationship Type */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Relationship Type
            </label>
            <select
              value={relationshipType}
              onChange={(e) => setRelationshipType(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            >
              {RELATIONSHIP_TYPES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          {/* Dependency Criticality */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Dependency Criticality
            </label>
            <select
              value={criticality}
              onChange={(e) => setCriticality(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 capitalize"
            >
              <option value="low">Low Criticality (Optional / Non-blocking)</option>
              <option value="medium">Medium Criticality (Normal operation)</option>
              <option value="high">High Criticality (Significant degradation if severed)</option>
              <option value="critical">Mission Critical (Total failure if severed)</option>
            </select>
          </div>

          {/* Flow preview */}
          {sourceId && targetId && (
            <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-700/60 text-xs flex items-center justify-center gap-2 text-slate-300">
              <span className="font-semibold text-cyan-400 font-mono truncate max-w-[140px]">
                {components.find((c) => c.id === sourceId)?.name || sourceId}
              </span>
              <span className="text-slate-500 font-mono text-[11px] px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 flex items-center gap-1">
                {relationshipType} <ArrowRight size={12} />
              </span>
              <span className="font-semibold text-purple-400 font-mono truncate max-w-[140px]">
                {components.find((c) => c.id === targetId)?.name || targetId}
              </span>
            </div>
          )}

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
              disabled={submitting || !sourceId || !targetId || sourceId === targetId}
              className="px-5 py-2.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 rounded-xl text-xs font-bold text-white shadow-lg shadow-purple-900/30 transition flex items-center gap-1.5"
            >
              {submitting ? 'Connecting...' : 'Create Dependency'}
            </button>
          </div>

        </form>
      </div>
    </div>
  );
};
