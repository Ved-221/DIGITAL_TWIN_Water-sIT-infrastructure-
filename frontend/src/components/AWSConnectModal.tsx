import React, { useState } from 'react';
import { X, Key, Shield, Globe, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { AWS_REGIONS } from '../utils/localization';

interface AWSConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConnected: (accountInfo: any) => void;
  apiBase: string;
}

export const AWSConnectModal: React.FC<AWSConnectModalProps> = ({
  isOpen,
  onClose,
  onConnected,
  apiBase
}) => {
  const [accessKeyId, setAccessKeyId] = useState('');
  const [secretAccessKey, setSecretAccessKey] = useState('');
  const [sessionToken, setSessionToken] = useState('');
  const [region, setRegion] = useState('ap-south-1');
  
  const [connecting, setConnecting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessKeyId.trim() || !secretAccessKey.trim()) {
      setStatusMessage({ type: 'error', text: 'AWS Access Key ID and Secret Access Key are required.' });
      return;
    }

    setConnecting(true);
    setStatusMessage(null);

    try {
      // 1. Authenticate via POST /api/aws/connect
      const res = await fetch(`${apiBase}/aws/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_key_id: accessKeyId.trim(),
          secret_access_key: secretAccessKey.trim(),
          session_token: sessionToken.trim() || null,
          region: region
        })
      });

      const data = await res.json();

      if (data.authenticated) {
        setStatusMessage({
          type: 'success',
          text: `Authenticated! Account: ${data.account_id} (${data.arn})`
        });

        setTimeout(() => {
          onConnected(data);
          onClose();
        }, 750);
      } else {
        setStatusMessage({
          type: 'error',
          text: data.error || 'Authentication failed. Please verify credentials and IAM permissions.'
        });
      }
    } catch (err: any) {
      setStatusMessage({
        type: 'error',
        text: `Network error connecting to Digital Twin backend: ${err.message}`
      });
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl max-w-lg w-full shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
        <div className="p-6 border-b border-slate-700/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400">
              <Key size={20} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">Connect AWS Environment</h3>
              <p className="text-xs text-slate-400">Validate credentials via STS and ingest real infrastructure topology</p>
            </div>
          </div>
          <button 
            onClick={onClose} 
            className="text-slate-400 hover:text-white p-1 rounded-md transition"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
              AWS Access Key ID *
            </label>
            <input
              type="text"
              value={accessKeyId}
              onChange={(e) => setAccessKeyId(e.target.value)}
              placeholder="AKIAIOSFODNN7EXAMPLE"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 font-mono"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
              AWS Secret Access Key *
            </label>
            <input
              type="password"
              value={secretAccessKey}
              onChange={(e) => setSecretAccessKey(e.target.value)}
              placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 font-mono"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
              Session Token <span className="text-slate-500 lowercase">(optional for temporary / SSO credentials)</span>
            </label>
            <input
              type="password"
              value={sessionToken}
              onChange={(e) => setSessionToken(e.target.value)}
              placeholder="AQoDYXdzEJr1..."
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 font-mono text-xs"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
              <Globe size={13} className="text-cyan-400" /> Target AWS Region
            </label>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
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

          {statusMessage && (
            <div className={`p-3 rounded-lg text-xs flex items-start gap-2 ${
              statusMessage.type === 'success' 
                ? 'bg-emerald-950/60 border border-emerald-800 text-emerald-200' 
                : 'bg-red-950/60 border border-red-800 text-red-200'
            }`}>
              {statusMessage.type === 'success' ? (
                <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
              )}
              <span className="leading-relaxed">{statusMessage.text}</span>
            </div>
          )}

          <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-700/60 text-[11px] text-slate-400 flex items-start gap-2">
            <Shield size={14} className="text-blue-400 shrink-0 mt-0.5" />
            <span>Credentials are held in memory for the active backend session and used solely to query read-only AWS APIs (EC2, RDS, VPC, CloudWatch). Credentials are never stored on disk or committed to source control.</span>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-700/60 hover:bg-slate-700 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={connecting}
              className="px-5 py-2 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white transition shadow-lg shadow-blue-900/30 flex items-center gap-2 disabled:opacity-50"
            >
              {connecting ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Validating via STS...</span>
                </>
              ) : (
                <span>Test & Connect AWS</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
