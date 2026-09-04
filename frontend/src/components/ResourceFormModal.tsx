import React, { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000/api';

export default function ResourceFormModal({ isOpen, onClose, onSave, existingResource = null, selectedEnv }: any) {
  const [formData, setFormData] = useState({
    name: '',
    type: 'server',
    environment: 'on_prem',
    criticality: 'medium',
    status: 'active',
    cost_per_month: 0,
    cpu: '',
    memory: '',
    location: 'Manual-Datacenter',
    owner: 'Manual',
    source_environment: selectedEnv
  });

  useEffect(() => {
    if (isOpen) {
      if (existingResource) {
        setFormData({ ...existingResource });
      } else {
        setFormData({
          name: '',
          type: 'server',
          environment: 'on_prem',
          criticality: 'medium',
          status: 'active',
          cost_per_month: 0,
          cpu: '',
          memory: '',
          location: 'Manual-Datacenter',
          owner: 'Manual',
          source_environment: selectedEnv
        });
      }
    }
  }, [isOpen, existingResource, selectedEnv]);

  if (!isOpen) return null;

  const handleChange = (e: any) => {
    const { name, value } = e.target;
    setFormData((prev: any) => ({
      ...prev,
      [name]: name === 'cost_per_month' || name === 'cpu' || name === 'memory' ? parseFloat(value) || 0 : value
    }));
  };

  const handleSubmit = async (e: any) => {
    e.preventDefault();
    const method = existingResource ? 'PUT' : 'POST';
    const url = existingResource ? `${API_BASE}/manual/components/${existingResource.id}` : `${API_BASE}/manual/components`;
    
    const payload = { ...formData };
    if (payload.cpu === '') payload.cpu = null;
    if (payload.memory === '') payload.memory = null;

    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        onSave();
        onClose();
      } else {
        alert("Error saving resource");
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-slate-800 p-6 rounded-lg w-full max-w-md border border-slate-700">
        <h2 className="text-xl font-bold mb-4">{existingResource ? 'Edit Resource' : 'Add Resource'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-1 text-slate-300">Name</label>
            <input required type="text" name="name" value={formData.name} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm mb-1 text-slate-300">Type</label>
              <select name="type" value={formData.type} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white">
                <option value="application">Application</option>
                <option value="server">Server</option>
                <option value="database">Database</option>
                <option value="network">Network</option>
                <option value="cloud_resource">Cloud Resource</option>
                <option value="storage">Storage</option>
                <option value="api">API</option>
                <option value="identity">Identity</option>
              </select>
            </div>
            <div>
              <label className="block text-sm mb-1 text-slate-300">Environment</label>
              <select name="environment" value={formData.environment} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white">
                <option value="on_prem">On-Prem</option>
                <option value="cloud">Cloud</option>
                <option value="hybrid">Hybrid</option>
                <option value="kubernetes">Kubernetes</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm mb-1 text-slate-300">Criticality</label>
              <select name="criticality" value={formData.criticality} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label className="block text-sm mb-1 text-slate-300">Status</label>
              <select name="status" value={formData.status} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white">
                <option value="active">Active</option>
                <option value="degraded">Degraded</option>
                <option value="offline">Offline</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm mb-1 text-slate-300">Estimated Cost per Month ($)</label>
            <input type="number" name="cost_per_month" value={formData.cost_per_month} onChange={handleChange} className="w-full bg-slate-900 border border-slate-600 rounded p-2 text-white" />
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
