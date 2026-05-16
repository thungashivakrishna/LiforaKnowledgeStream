import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { Target, Activity, ShieldAlert, CheckCircle2, ChevronRight, UserCircle, BrainCircuit, Sparkles } from 'lucide-react'

const API_BASE = '/api/v1'

const PersonalizedProtocols = () => {
  const [profile, setProfile] = useState({
    conditions: [],
    goals: [],
    allergies: []
  })
  const [protocol, setProtocol] = useState([])
  const [loading, setLoading] = useState(false)
  
  const commonGoals = ["Longevity", "Metabolic Health", "Hypertrophy", "Cognitive Function", "Sleep Quality", "Stress Resilience"]
  const commonConditions = ["Hypertension", "Type 2 Diabetes", "Insulin Resistance", "Joint Pain", "Insomnia", "Anxiety"]

  const toggleSelection = (type, value) => {
    setProfile(prev => {
      const current = prev[type]
      const updated = current.includes(value) 
        ? current.filter(v => v !== value) 
        : [...current, value]
      return { ...prev, [type]: updated }
    })
  }

  const generateProtocol = async () => {
    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE}/library/personalized-protocol`, profile)
      setProtocol(response.data)
    } catch (error) {
      console.error('Error generating protocol:', error)
    } finally {
      setLoading(false)
    }
  }

  // Group by Framework
  const groupedProtocol = protocol.reduce((acc, item) => {
    const key = item.framework || "General Health"
    if (!acc[key]) acc[key] = []
    acc[key].push(item)
    return acc
  }, {})

  return (
    <div className="space-y-8 pb-20 max-w-6xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-4xl font-bold tracking-tight text-white flex items-center gap-3">
            <Sparkles className="w-10 h-10 text-brand-500 animate-pulse" />
            Personalized Protocols
          </h2>
          <p className="text-slate-400 mt-2 text-lg">Evidence-backed health strategies mapped to your biological profile.</p>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 bg-slate-900/50 rounded-full border border-slate-800 text-xs font-medium text-slate-500">
          <Activity className="w-4 h-4 text-emerald-500" />
          {protocol.length} Actionable Insights Identified
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Left Side: Profile Config */}
        <div className="lg:col-span-1 space-y-6">
          <div className="glass p-6 rounded-3xl border-brand-500/20 sticky top-8">
            <h3 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
              <UserCircle className="w-5 h-5 text-brand-400" />
              Your Profile
            </h3>
            
            <div className="space-y-8">
              <div>
                <label className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500 mb-4 block">Health Goals</label>
                <div className="grid grid-cols-1 gap-2">
                  {commonGoals.map(goal => (
                    <button
                      key={goal}
                      onClick={() => toggleSelection('goals', goal)}
                      className={`text-left text-xs px-4 py-3 rounded-xl border transition-all flex items-center justify-between group ${
                        profile.goals.includes(goal)
                          ? "bg-brand-600 border-brand-500 text-white shadow-lg shadow-brand-500/20"
                          : "bg-slate-900/50 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      {goal}
                      {profile.goals.includes(goal) && <CheckCircle2 className="w-4 h-4" />}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500 mb-4 block">Clinical Context</label>
                <div className="grid grid-cols-1 gap-2">
                  {commonConditions.map(cond => (
                    <button
                      key={cond}
                      onClick={() => toggleSelection('conditions', cond)}
                      className={`text-left text-xs px-4 py-3 rounded-xl border transition-all flex items-center justify-between ${
                        profile.conditions.includes(cond)
                          ? "bg-blue-600 border-blue-500 text-white shadow-lg shadow-blue-500/20"
                          : "bg-slate-900/50 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      {cond}
                      {profile.conditions.includes(cond) && <CheckCircle2 className="w-4 h-4" />}
                    </button>
                  ))}
                </div>
              </div>

              <button 
                onClick={generateProtocol}
                disabled={loading || (profile.goals.length === 0 && profile.conditions.length === 0)}
                className="w-full bg-brand-600 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold py-4 rounded-2xl shadow-lg shadow-brand-600/20 transition-all flex items-center justify-center gap-3 group"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                ) : (
                  <>
                    <BrainCircuit className="w-5 h-5 group-hover:rotate-12 transition-transform" />
                    GENERATE MAP
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Right Side: Protocol View */}
        <div className="lg:col-span-3">
          {protocol.length > 0 ? (
            <div className="space-y-12">
              {Object.entries(groupedProtocol).map(([framework, items]) => (
                <div key={framework} className="space-y-6">
                  <div className="flex items-center gap-4">
                    <h3 className="text-xl font-bold text-white uppercase tracking-widest flex items-center gap-3">
                      <div className="w-1.5 h-8 bg-brand-500 rounded-full" />
                      {framework}
                    </h3>
                    <div className="h-px bg-slate-800 flex-grow" />
                  </div>

                  <div className="grid grid-cols-1 gap-4">
                    {items.map((fact, idx) => (
                      <div key={idx} className="glass p-6 rounded-3xl border-slate-800/50 hover:border-brand-500/30 transition-all group relative overflow-hidden">
                        {/* Evidence Score Badge */}
                        <div className="absolute top-0 right-0">
                          <div className={`px-4 py-1 text-[10px] font-bold rounded-bl-2xl border-b border-l ${
                            fact.confidence > 0.85 ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-amber-500/10 border-amber-500/20 text-amber-400"
                          }`}>
                            {(fact.confidence * 100).toFixed(0)}% EVIDENCE
                          </div>
                        </div>

                        <div className="flex flex-col md:flex-row gap-6">
                          <div className="flex-grow">
                            <div className="flex items-center gap-2 mb-3">
                              {fact.topic && (
                                <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-bold uppercase tracking-wider">
                                  {fact.topic}
                                </span>
                              )}
                              <span className="text-[10px] text-slate-500 font-medium italic">
                                Extracted from {fact.document_title}
                              </span>
                            </div>

                            <p className="text-slate-100 text-xl mb-4 font-semibold leading-relaxed">
                              <span className="text-brand-400">{fact.subject}</span> {fact.predicate} <span className="text-blue-400">{fact.object}</span>
                            </p>

                            <blockquote className="border-l-2 border-slate-800 pl-4 py-1">
                              <p className="text-sm text-slate-400 italic leading-relaxed">
                                "{fact.fact_text}"
                              </p>
                            </blockquote>
                          </div>

                          <div className="flex md:flex-col items-center justify-center gap-2 border-t md:border-t-0 md:border-l border-slate-800/50 pt-4 md:pt-0 md:pl-6">
                            <a 
                              href={`/documents?id=${fact.document_id}`}
                              className="p-3 rounded-2xl bg-slate-900/50 border border-slate-800 text-slate-400 hover:text-white hover:border-brand-500 transition-all group/btn"
                              title="View Clinical Source"
                            >
                              <ChevronRight className="w-5 h-5 group-hover/btn:translate-x-1 transition-transform" />
                            </a>
                            <span className="text-[10px] font-bold text-slate-600 uppercase tracking-tighter hidden md:block">Source</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : !loading ? (
            <div className="h-full flex flex-col items-center justify-center py-32 glass rounded-[3rem] border-dashed border-slate-800/50">
              <div className="relative mb-8">
                <div className="absolute inset-0 bg-brand-500/20 blur-3xl rounded-full" />
                <Target className="w-24 h-24 text-slate-700 relative z-10" />
              </div>
              <h3 className="text-2xl font-bold text-slate-300">Ready to Map Your Protocol</h3>
              <p className="text-slate-500 text-center max-w-md mt-3 leading-relaxed">
                Select your biological profile on the left to extract the most relevant, evidence-backed interventions from the Lifora Knowledge Graph.
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default PersonalizedProtocols
