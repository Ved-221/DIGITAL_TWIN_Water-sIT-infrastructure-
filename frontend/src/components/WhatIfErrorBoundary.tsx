import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw, X } from 'lucide-react';

interface Props {
  children: ReactNode;
  onClose?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class WhatIfErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('WhatIfErrorBoundary caught an unhandled error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="fixed inset-y-0 right-0 z-50 w-full sm:w-[540px] bg-slate-900 border-l border-red-800 shadow-2xl flex flex-col justify-between p-6 text-white font-sans">
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2 text-red-400">
                <AlertTriangle size={20} />
                <h3 className="text-sm font-bold uppercase tracking-wider">What-If Analysis</h3>
              </div>
              {this.props.onClose && (
                <button
                  type="button"
                  onClick={this.props.onClose}
                  className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition"
                  title="Close What-If Panel"
                >
                  <X size={18} />
                </button>
              )}
            </div>

            <div className="bg-red-950/70 border border-red-850 rounded-xl p-4 text-xs space-y-2">
              <div className="flex items-center gap-2 text-red-300 font-bold">
                <AlertTriangle size={16} className="text-red-400 shrink-0" />
                <span>What-If analysis could not be loaded.</span>
              </div>
              <p className="text-red-200/90 font-mono text-[11px] bg-red-900/40 p-2.5 rounded border border-red-800/60 break-words">
                {this.state.error?.message || 'An unexpected rendering error occurred inside the What-If panel.'}
              </p>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg transition flex items-center gap-1.5"
            >
              <RefreshCw size={13} />
              <span>Retry</span>
            </button>
            {this.props.onClose && (
              <button
                type="button"
                onClick={this.props.onClose}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-xs font-bold rounded-lg transition"
              >
                Close
              </button>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
