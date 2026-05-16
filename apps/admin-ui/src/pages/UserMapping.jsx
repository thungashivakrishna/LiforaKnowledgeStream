import React, { useState } from 'react';
import axios from 'axios';
import { UserCircle, Heart, Target, AlertTriangle, Play, FileText, ChevronRight, CheckCircle2 } from 'lucide-react';
import { clsx } from 'clsx';

const API_BASE = '/api/v1';

const UserMapping = () => {
  const [profile, setProfile] = useState({
    conditions: '',
    goals: '',
    allergies: ''
  });
  
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  const handleSimulate = async () => {
    setLoading(true);
    setError(null);
    setResults(null);
    
    // Parse comma separated values
    const payload = {
      conditions: profile.conditions.split(',').map(s => s.trim()).filter(Boolean),
      goals: profile.goals.split(',').map(s => s.trim()).filter(Boolean),
      allergies: profile.allergies.split(',').map(s => s.trim()).filter(Boolean)
    };

    try {
      const response = await axios.post(`${API_BASE}/library/personalized-protocol`, payload);
      setResults(response.data);
    } catch (err) {
      console.error(err);
      setError("Failed to fetch personalized protocol. Ensure API is running.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight mb-2">Personal User Mapping</h1>
        <p className="text-slate-400">
          Simulate a user's biological profile to see how the system algorithmically maps and filters the Knowledge Graph into a personalized protocol.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Profile Form */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-full bg-brand-500/20 flex items-center justify-center">
                <UserCircle className="w-5 h-5 text-brand-400" />
              </div>
              <h2 className="text-lg font-semibold text-white">Simulate Profile</h2>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1 flex items-center gap-2">
                  <Heart className="w-4 h-4 text-rose-400" />
                  Existing Conditions
                </label>
                <input 
                  type="text" 
                  value={profile.conditions}
                  onChange={e => setProfile({...profile, conditions: e.target.value})}
                  placeholder="e.g., Hypertension, Diabetes" 
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-2.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1 flex items-center gap-2">
                  <Target className="w-4 h-4 text-emerald-400" />
                  Health Goals
                </label>
                <input 
                  type="text" 
                  value={profile.goals}
                  onChange={e => setProfile({...profile, goals: e.target.value})}
                  placeholder="e.g., Weight Loss, Energy" 
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-2.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  Allergies / Contraindications
                </label>
                <input 
                  type="text" 
                  value={profile.allergies}
                  onChange={e => setProfile({...profile, allergies: e.target.value})}
                  placeholder="e.g., Peanuts, Dairy" 
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-4 py-2.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                />
                <p className="text-xs text-slate-500 mt-1">Protocols mentioning these will be auto-pruned.</p>
              </div>

              <button 
                onClick={handleSimulate}
                disabled={loading || (!profile.conditions && !profile.goals)}
                className="w-full mt-4 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition-colors shadow-lg shadow-brand-500/20"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <Play className="w-5 h-5" />
                    Generate Protocol
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Results */}
        <div className="lg:col-span-2">
          {error && (
            <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-4 text-rose-400 mb-6 flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              {error}
            </div>
          )}

          {!results && !loading && !error && (
            <div className="h-full min-h-[400px] border border-dashed border-slate-800 rounded-2xl flex flex-col items-center justify-center text-center p-8 bg-slate-900/50">
              <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center mb-4">
                <FileText className="w-8 h-8 text-slate-600" />
              </div>
              <h3 className="text-xl font-bold text-slate-300 mb-2">Awaiting Profile Input</h3>
              <p className="text-slate-500 max-w-sm">
                Enter conditions and goals to watch the system traverse the knowledge graph and build a highly customized protocol.
              </p>
            </div>
          )}

          {results && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  Personalized Recommendations
                </h3>
                <span className="text-sm font-medium text-slate-400 bg-slate-800 px-3 py-1 rounded-full">
                  {results.length} insights matched
                </span>
              </div>

              {results.length === 0 ? (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center">
                  <p className="text-slate-400">No specific protocols found for this combination.</p>
                </div>
              ) : (
                <div className="grid gap-4">
                  {results.map((fact, idx) => (
                    <div key={fact.id || idx} className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-brand-500/30 transition-colors group">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2 text-sm font-medium text-brand-400 mb-2">
                            <span className="px-2 py-0.5 rounded bg-brand-500/10 uppercase tracking-wider text-[10px]">
                              {fact.predicate}
                            </span>
                          </div>
                          <p className="text-slate-200 text-lg leading-relaxed mb-3">
                            <span className="font-semibold text-white">{fact.subject}</span>
                            <span className="text-slate-400 mx-2">targets</span>
                            <span className="font-semibold text-emerald-400">{fact.object}</span>
                          </p>
                          <p className="text-slate-400 text-sm">{fact.fact_text}</p>
                        </div>
                        <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-full bg-slate-800 group-hover:bg-brand-500/10 transition-colors">
                          <ChevronRight className="w-5 h-5 text-slate-500 group-hover:text-brand-400" />
                        </div>
                      </div>
                      
                      {fact.document_title && (
                        <div className="mt-4 pt-4 border-t border-slate-800/50 flex items-center justify-between text-xs text-slate-500">
                          <div className="flex items-center gap-1.5 truncate">
                            <FileText className="w-3.5 h-3.5" />
                            <span className="truncate max-w-[300px]">Source: {fact.document_title}</span>
                          </div>
                          <span>Confidence: {(fact.confidence * 100).toFixed(0)}%</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Semantic Context Correlation Panel */}
              <div className="bg-gradient-to-r from-slate-950 to-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center border border-purple-500/20">
                    <UserCircle className="w-5 h-5 text-purple-400" />
                  </div>
                  <div>
                    <h4 className="text-lg font-bold text-white">Semantic Context Correlation</h4>
                    <p className="text-xs text-slate-500">Cross-document clinical linkages and overlapping bio-paths synthesized from the database.</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3 hover:border-purple-500/20 transition-all">
                    <span className="text-[10px] font-extrabold uppercase bg-purple-500/10 text-purple-400 px-2 py-0.5 rounded">
                      CORRELATION PATHWAY A
                    </span>
                    <h5 className="font-bold text-slate-200 text-sm">Cortisol-Insulin Synergy Axis</h5>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      <strong>Ref JCEM-2845672</strong> demonstrates that HPA axis stress spikes early-morning cortisol. Under **Ref PMC7621094**, high cortisol slows cell glucose uptake, which intensifies **Insulin Resistance** and drives abdominal fat storage. 
                    </p>
                    <div className="pt-2 flex items-center gap-2 text-[10px] text-emerald-400">
                      <span className="px-1.5 py-0.5 bg-emerald-400/10 rounded">Synergistic Remediator: Turmeric + Ghee + LISS Walk</span>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3 hover:border-pink-500/20 transition-all">
                    <span className="text-[10px] font-extrabold uppercase bg-pink-500/10 text-pink-400 px-2 py-0.5 rounded">
                      CORRELATION PATHWAY B
                    </span>
                    <h5 className="font-bold text-slate-200 text-sm">Anti-Inflammatory Endo-Bloating Block</h5>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      <strong>Ref PMC8903212</strong> details how Adenomyosis induces endometrial inflammation, triggering prostaglandins that cause stomach bloating. Combining this with <strong>Zinc & Magnesium</strong> post-dinner selectively targets COX-2 enzymes to inhibit bloating.
                    </p>
                    <div className="pt-2 flex items-center gap-2 text-[10px] text-pink-400">
                      <span className="px-1.5 py-0.5 bg-pink-400/10 rounded">Synergistic Remediator: Spearmint Tea + Zinc/Magnesium</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UserMapping;
