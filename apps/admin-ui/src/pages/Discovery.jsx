import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Search, 
  Play, 
  Pause,
  Zap, 
  ShieldAlert, 
  CheckCircle2, 
  Loader2, 
  Filter, 
  Activity, 
  Server, 
  Layers,
  ChevronRight,
  Globe
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import { format } from 'date-fns';

const API_BASE = '/api/v1';

const Discovery = () => {
  const [sources, setSources] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  
  // Trigger Form
  const [mode, setMode] = useState('FOCUSED');
  const [selectedSources, setSelectedSources] = useState([]);
  const [topicInput, setTopicInput] = useState('');

  // Expanded Details State
  const [expandedRunId, setExpandedRunId] = useState(null);
  const [runDetails, setRunDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  useEffect(() => {
    fetchSources();
    fetchRuns();
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchSources = async () => {
    try {
      const response = await axios.get(`${API_BASE}/sources`);
      setSources(response.data.items || []);
    } catch (err) {
      console.error('Failed to load sources:', err);
    }
  };

  const fetchRuns = async () => {
    try {
      const response = await axios.get(`${API_BASE}/discovery/runs`);
      setRuns(response.data.items || []);
    } catch (err) {
      console.error('Failed to fetch runs:', err);
    }
  };

  const handleTriggerJob = async () => {
    setTriggering(true);
    try {
      // Optional: Create a filter profile first if there are topic inputs.
      // For simplicity and direct triggering as available in the route, launch direct run.
      let profileId = null;
      if (topicInput.trim()) {
        const profilePayload = {
          name: `Manual Trigger - ${format(new Date(), 'MMM d HH:mm')}`,
          mode: mode,
          topics: topicInput.split(',').map(t => t.trim()).filter(Boolean),
          max_candidates: 50,
          per_source_limit: 15
        };
        const profileResp = await axios.post(`${API_BASE}/discovery/profiles`, profilePayload);
        profileId = profileResp.data.id;
      }

      const runPayload = {
        mode: mode,
        source_ids: selectedSources,
        filter_profile_id: profileId,
        framework_scope: []
      };

      await axios.post(`${API_BASE}/discovery/runs`, runPayload);
      setTopicInput('');
      setSelectedSources([]);
      fetchRuns();
    } catch (err) {
      console.error('Job trigger error:', err);
      alert('Failed to initiate the discovery cycle. Check server logs.');
    } finally {
      setTriggering(false);
    }
  };
  const handleTerminateJob = async (runId) => {
    if (!window.confirm("Are you sure you want to terminate this workflow and all active child processes?")) return;
    try {
      await axios.delete(`${API_BASE}/discovery/runs/${runId}`);
      fetchRuns();
    } catch (err) {
      console.error('Failed to terminate:', err);
      alert('Could not terminate workflow.');
    }
  };

  const toggleRunDetails = async (runId) => {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      setRunDetails(null);
      return;
    }
    
    setExpandedRunId(runId);
    setLoadingDetails(true);
    try {
      const resp = await axios.get(`${API_BASE}/discovery/runs/${runId}`);
      setRunDetails(resp.data);
    } catch (err) {
      console.error("Failed to load run details", err);
    } finally {
      setLoadingDetails(false);
    }
  };
  return (
    <div className="space-y-8 pb-12">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2 flex items-center gap-3">
          <Zap className="w-8 h-8 text-amber-400 fill-amber-400/20" />
          Discovery & Extraction Orchestrator
        </h1>
        <p className="text-slate-400">Continuously acquire and digest new scientific literature and clinical frameworks.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        {/* Job Trigger & Configuration Panel */}
        <div className="xl:col-span-1">
          <div className="glass p-6 rounded-2xl border border-slate-800 space-y-6 shadow-xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-brand-500/5 blur-3xl rounded-full -mr-10 -mt-10 pointer-events-none"></div>
            
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Activity className="w-5 h-5 text-brand-400" />
                Initiate Extraction Cycle
              </h2>
              <p className="text-xs text-slate-500 mt-1">Configure parameters to focus the automated background crawler.</p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-black tracking-widest uppercase text-slate-500 mb-2">Targeted Focus (Optional)</label>
                <textarea 
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 placeholder-slate-700 text-sm focus:border-brand-500 focus:outline-none transition-colors h-24 resize-none"
                  placeholder="E.g. PCOS, Insulin Resistance, High Cortisol, Adenomyosis, Spearmint Tea..."
                  value={topicInput}
                  onChange={(e) => setTopicInput(e.target.value)}
                />
                <p className="text-[10px] text-slate-600 mt-1 flex items-center gap-1">
                  <Filter className="w-3 h-3" />
                  Leave blank to crawl generally across all authorized sources.
                </p>
              </div>

              <div>
                <label className="block text-xs font-black tracking-widest uppercase text-slate-500 mb-2">Discovery Mode</label>
                <div className="grid grid-cols-3 gap-2">
                  {['GENERIC', 'FOCUSED', 'HYBRID'].map((m) => (
                    <button
                      key={m}
                      onClick={() => setMode(m)}
                      className={clsx(
                        "py-2 px-1 text-center rounded-lg border text-[10px] font-bold tracking-wider transition-all",
                        mode === m 
                          ? "bg-brand-500/10 border-brand-500 text-brand-400 shadow-sm shadow-brand-500/10" 
                          : "bg-slate-900/50 border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-700"
                      )}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-black tracking-widest uppercase text-slate-500 mb-2">Filter by Source</label>
                <div className="max-h-40 overflow-y-auto custom-scrollbar bg-slate-950 border border-slate-800 rounded-xl p-2 space-y-1">
                  {sources.map((src) => (
                    <label 
                      key={src.id} 
                      className={clsx(
                        "flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors text-xs",
                        selectedSources.includes(src.id) ? "bg-slate-800/50 text-slate-200" : "text-slate-400 hover:bg-slate-900 hover:text-slate-300"
                      )}
                    >
                      <input 
                        type="checkbox" 
                        className="accent-brand-500" 
                        checked={selectedSources.includes(src.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedSources([...selectedSources, src.id]);
                          } else {
                            setSelectedSources(selectedSources.filter(id => id !== src.id));
                          }
                        }}
                      />
                      <span className="truncate">{src.name}</span>
                    </label>
                  ))}
                  {sources.length === 0 && <div className="p-2 text-slate-600 text-center text-[10px]">No sources loaded</div>}
                </div>
              </div>

              <button 
                onClick={handleTriggerJob}
                disabled={triggering}
                className="w-full py-3 bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white rounded-xl font-bold shadow-xl shadow-brand-900/20 flex items-center justify-center gap-2 transition-all duration-200 disabled:opacity-50"
              >
                {triggering ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Play className="w-4 h-4 fill-current" />
                )}
                {triggering ? "Launching Workflow..." : "Start Knowledge Extraction"}
              </button>
            </div>
          </div>
        </div>

        {/* Background Monitoring / Status Dash */}
        <div className="xl:col-span-2 space-y-6">
          {/* Live Status Overview Header */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="glass p-4 rounded-xl border border-slate-800 flex items-center gap-4">
              <div className="p-3 bg-blue-500/10 rounded-lg border border-blue-500/20 text-blue-400">
                <Server className="w-6 h-6" />
              </div>
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Total Runs</div>
                <div className="text-2xl font-bold text-white">{runs.length}</div>
              </div>
            </div>

            <div className="glass p-4 rounded-xl border border-slate-800 flex items-center gap-4">
              <div className="p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/20 text-emerald-400">
                <Layers className="w-6 h-6" />
              </div>
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Docs Discovered</div>
                <div className="text-2xl font-bold text-white">
                  {runs.reduce((acc, curr) => acc + (curr.candidate_count || 0), 0)}
                </div>
              </div>
            </div>

            <div className="glass p-4 rounded-xl border border-slate-800 flex items-center gap-4">
              <div className={clsx(
                "p-3 rounded-lg border",
                runs.some(r => r.status === 'RUNNING' || r.status === 'PENDING') 
                  ? "bg-amber-500/10 border-amber-500/20 text-amber-400" 
                  : "bg-slate-800 border-slate-700 text-slate-400"
              )}>
                <Activity className={clsx("w-6 h-6", runs.some(r => r.status === 'RUNNING') && "animate-pulse")} />
              </div>
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Job State</div>
                <div className="text-sm font-bold text-white">
                  {runs.some(r => r.status === 'RUNNING' || r.status === 'PENDING') ? "COLLECTING DATA" : "IDLE"}
                </div>
              </div>
            </div>
          </div>

          {/* Table of Runs */}
          <div className="glass rounded-2xl border border-slate-800 overflow-hidden flex flex-col min-h-[400px]">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-bold text-slate-100 flex items-center gap-2">
                <Globe className="w-4 h-4 text-brand-400" />
                Extraction Ticker & Pipeline State
              </h3>
            </div>
            <div className="flex-1 overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-900/50 text-[10px] uppercase font-black tracking-widest text-slate-500 border-b border-slate-800">
                    <th className="px-6 py-3">Status</th>
                    <th className="px-6 py-3">Mode</th>
                    <th className="px-6 py-3">Timestamp</th>
                    <th className="px-6 py-3">Results</th>
                    <th className="px-6 py-3 text-right">Control</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {runs.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="px-6 py-16 text-center">
                        <div className="flex flex-col items-center text-slate-600">
                          <Search className="w-12 h-12 mb-4 opacity-30" />
                          <p className="font-bold text-slate-400">No Extraction History</p>
                          <p className="text-xs">Trigger an extraction cycle to populate this feed.</p>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    runs.flatMap((run) => [
                      <tr key={run.id} className="hover:bg-slate-800/30 transition-colors cursor-pointer" onClick={() => toggleRunDetails(run.id)}>
                        <td className="px-6 py-4">
                          <span className={clsx(
                            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-wider border",
                            run.status === 'COMPLETED' ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
                            run.status === 'RUNNING' ? "bg-amber-500/10 text-amber-400 border-amber-500/20" :
                            run.status === 'FAILED' ? "bg-rose-500/10 text-rose-400 border-rose-500/20" :
                            "bg-slate-800 text-slate-400 border-slate-700"
                          )}>
                            {run.status === 'RUNNING' && <Loader2 className="w-3 h-3 animate-spin" />}
                            {run.status === 'COMPLETED' && <CheckCircle2 className="w-3 h-3" />}
                            {run.status === 'FAILED' && <ShieldAlert className="w-3 h-3" />}
                            {run.status}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className="text-xs font-semibold text-slate-300">{run.mode}</span>
                        </td>
                        <td className="px-6 py-4 text-xs text-slate-500 font-mono">
                          {format(new Date(run.created_at), 'MMM dd, HH:mm:ss')}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-slate-200">{run.candidate_count || 0}</span>
                            <span className="text-[10px] font-bold text-slate-600 uppercase">Units</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                          {run.status === 'RUNNING' ? (
                            <button 
                              onClick={() => handleTerminateJob(run.id)}
                              className="p-2 bg-slate-800 hover:bg-rose-900/30 text-slate-400 hover:text-rose-400 rounded-lg transition-colors border border-transparent hover:border-rose-500/30" title="Terminate Workflow">
                              <Pause className="w-4 h-4" />
                            </button>
                          ) : (
                            <button 
                              onClick={() => toggleRunDetails(run.id)}
                              className={clsx(
                                "p-2 rounded-lg transition-colors border", 
                                expandedRunId === run.id ? "bg-brand-500/20 text-brand-400 border-brand-500/30" : "bg-slate-900 text-slate-600 border-slate-800"
                              )}>
                              <ChevronRight className={clsx("w-4 h-4 transition-transform", expandedRunId === run.id && "rotate-90")} />
                            </button>
                          )}
                        </td>
                      </tr>,
                      expandedRunId === run.id && (
                        <tr key={`${run.id}-details`} className="bg-slate-950/50 border-t-0">
                          <td colSpan="5" className="px-6 py-4">
                            {loadingDetails ? (
                              <div className="flex items-center justify-center py-8 gap-2 text-slate-500 text-sm">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Loading extraction details...
                              </div>
                            ) : (
                              <div className="space-y-3">
                                <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400">Processed Items & Status</h4>
                                {(!runDetails?.candidates || runDetails.candidates.length === 0) ? (
                                  <p className="text-xs text-slate-600 italic">No candidates recorded yet for this run.</p>
                                ) : (
                                  <div className="max-h-60 overflow-y-auto custom-scrollbar border border-slate-800 rounded-lg">
                                    <table className="w-full text-[11px] text-left text-slate-400">
                                      <thead className="sticky top-0 bg-slate-900 text-[9px] font-black uppercase tracking-widest text-slate-500 border-b border-slate-800">
                                        <tr>
                                          <th className="px-3 py-2">Decision</th>
                                          <th className="px-3 py-2">Target URL / Title</th>
                                          <th className="px-3 py-2 text-right">Evaluation Score</th>
                                        </tr>
                                      </thead>
                                      <tbody className="divide-y divide-slate-800/50">
                                        {runDetails.candidates.map((c) => (
                                          <tr key={c.id} className="hover:bg-slate-800/20">
                                            <td className="px-3 py-2">
                                              <span className={clsx(
                                                "px-1.5 py-0.5 rounded font-bold uppercase text-[9px]",
                                                c.decision === 'INGEST_NOW' ? "bg-emerald-500/10 text-emerald-400" : "bg-slate-800 text-slate-500"
                                              )}>{c.decision}</span>
                                            </td>
                                            <td className="px-3 py-2 max-w-md truncate">
                                              <span className="block text-slate-200 font-semibold truncate">{c.title || "Untitled"}</span>
                                              <span className="block text-[9px] text-slate-500 truncate">{c.canonical_url}</span>
                                            </td>
                                            <td className="px-3 py-2 text-right font-mono text-slate-300 font-bold">
                                              {(c.score * 100).toFixed(0)}%
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      )
                    ])
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Discovery;

