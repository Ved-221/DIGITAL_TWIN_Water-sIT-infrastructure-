import React, { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000/api';

export default function DependencyFormModal({ isOpen, onClose, onSave, components, selectedEnv, prefilledDependency }: any) {
  const [formData, setFormData] = useState({
    source_id: '',
    target_id: '',
    relationship_type: 'depends_on',
    criticality: 'medium',
    source_environment: selectedEnv
  });

  useEffect(() => {
    if (isOpen) {
      setFormData(prefilledDependency ? {
        source_id: prefilledDependency.source_id || '',
        target_id: prefilledDependency.target_id || '',
        relationship_type: 'depends_on',
        criticality: 'medium',
        source_environment: selectedEnv
      } : {
        source_id: '',
        target_id: '',
        relationship_type: 'depends_on',
        criticality: 'medium',
        source_environment: selectedEnv
      });
    }
  }, [isOpen, prefilledDependency, selectedEnv]);

  if (!isOpen) return null;

  const handleChange = (e: any) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: any) => {
    e.preventDefault();
    if (!formData.source_id || !formData.target_id) {
      alert("Please select both a source and target resource.");
      return;
    }
    if (formData.source_id === formData.target_id) {
      alert("A resource cannot depend on itself.");
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE}/manual/dependencies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      if (res.ok) {
        onSave();
        onClose();
      } else {
        alert("Error saving dependency");
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-slate-800 p-6 rounded-lg w-full max-w-md border border-slate-700">
        <h2 className="text-xl font-bold mb-4">Add Dependency</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-1 text-slate-300">Source Resource</label>
            <select required name="source_id" value={formData.source_id} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white">
              <option value="">Select Resource...</option>
              {components.map((c: any) => (
                <option key={c.id} value={c.id}>{c.name} ({c.type})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1 text-slate-300">Relationship Type</label>
            <select name="relationship_type" value={formData.relationship_type} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white">
              <option value="depends_on">Depends On</option>
              <option value="connects_to">Connects To</option>
              <option value="hosted_on">Hosted On</option>
              <option value="authenticates_via">Authenticates Via</option>
              <option value="stores_in">Stores In</option>
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1 text-slate-300">Target Resource</label>
            <select required name="target_id" value={formData.target_id} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white">
              <option value="">Select Resource...</option>
              {components.map((c: any) => (
                <option key={c.id} value={c.id}>{c.name} ({c.type})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1 text-slate-300">Criticality of Connection</label>
            <select name="criticality" value={formData.criticality} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          
          <div className="flex justify-end gap-2 mt-6">
            <button type="button" onClick={onClose} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded text-white font-medium">Cancel</button>
            <button type="submit" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white font-medium">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
}
