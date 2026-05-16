import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { Activity, TrendingUp, Target, ShieldCheck, BrainCircuit, AlertCircle } from 'lucide-react'

const API_BASE = 'http://localhost:8000/api/v1'

const KnowledgeIntelligence = () => {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchIntelligence()
  }, [])

  const fetchIntelligence = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE}/library/intelligence`)
      setStats(response.data)
    } catch (error) {
      console.error('Error fetching intelligence:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-8 pb-20">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
          <BrainCircuit className="w-8 h-8 text-brand-500" />
          Knowledge Intelligence
        </h2>
        <p className="text-slate-400 mt-1">Audit the quality, quantity, and semantic richness of the ingested knowledge base.</p>
      </div>

      {/* High-Level Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass p-6 rounded-2xl">
          <div className="flex items-center gap-4 mb-4">
            <div className="p-3 bg-blue-500/10 rounded-xl">
              <Activity className="w-6 h-6 text-blue-400" />
            </div>
            <div>
              <p className="text-slate-400 text-sm font-medium">Total Facts</p>
              <h3 className="text-2xl font-bold text-white">{stats?.total_facts.toLocaleString()}</h3>
            </div>
          </div>
          <div className="text-xs text-slate-500 flex items-center gap-1">
            <TrendingUp className="w-3 h-3 text-emerald-500" />
            <span>Fact density increasing by source</span>
          </div>
        </div>

        <div className="glass p-6 rounded-2xl">
          <div className="flex items-center gap-4 mb-4">
            <div className="p-3 bg-brand-500/10 rounded-xl">
              <ShieldCheck className="w-6 h-6 text-brand-400" />
            </div>
            <div>
              <p className="text-slate-400 text-sm font-medium">Avg Confidence</p>
              <h3 className="text-2xl font-bold text-white">{(stats?.avg_confidence * 100).toFixed(1)}%</h3>
            </div>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div 
              className="h-full bg-brand-500" 
              style={{ width: `${stats?.avg_confidence * 100}%` }}
            ></div>
          </div>
        </div>

        <div className="glass p-6 rounded-2xl">
          <div className="flex items-center gap-4 mb-4">
            <div className="p-3 bg-purple-500/10 rounded-xl">
              <Target className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <p className="text-slate-400 text-sm font-medium">Frameworks</p>
              <h3 className="text-2xl font-bold text-white">{Object.keys(stats?.framework_distribution || {}).length}</h3>
            </div>
          </div>
          <p className="text-xs text-slate-500">Cross-domain semantic distribution</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Framework Distribution */}
        <div className="glass p-8 rounded-2xl">
          <h4 className="text-xl font-bold text-white mb-6">Knowledge Distribution</h4>
          <div className="space-y-6">
            {Object.entries(stats?.framework_distribution || {}).map(([fw, count]) => (
              <div key={fw}>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-slate-300">{fw.replace(/_/g, ' ')}</span>
                  <span className="text-sm font-bold text-white">{count} facts</span>
                </div>
                <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-brand-500/80" 
                    style={{ width: `${(count / stats.total_facts) * 100}%` }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent High-Value Findings */}
        <div className="glass p-8 rounded-2xl overflow-hidden flex flex-col">
          <h4 className="text-xl font-bold text-white mb-6">Recent Actionable Intelligence</h4>
          <div className="flex-1 overflow-y-auto space-y-4 custom-scrollbar pr-2">
            {stats?.recent_findings.map((f) => (
              <div key={f.id} className="bg-slate-900/40 border border-slate-800 p-4 rounded-xl hover:border-brand-500/30 transition-all">
                <div className="flex justify-between items-start mb-2">
                  <span className="text-[10px] font-bold text-brand-400 uppercase tracking-wider bg-brand-500/5 px-2 py-0.5 rounded border border-brand-500/10">
                    Confidence: {(f.confidence * 100).toFixed(0)}%
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">{f.document_title || 'Unknown Source'}</span>
                </div>
                <p className="text-slate-200 text-sm italic mb-2">"{f.fact_text}"</p>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-slate-400">{f.subject}</span>
                  <span className="text-brand-500 font-bold">→</span>
                  <span className="text-slate-400 font-medium">{f.predicate}</span>
                  <span className="text-brand-500 font-bold">→</span>
                  <span className="text-slate-400">{f.object}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Quality Audit Warning */}
      {stats?.avg_confidence < 0.7 && (
        <div className="bg-amber-500/10 border border-amber-500/20 p-6 rounded-2xl flex gap-4">
          <AlertCircle className="w-6 h-6 text-amber-500 flex-shrink-0" />
          <div>
            <h5 className="font-bold text-amber-500 mb-1">Low Confidence Threshold Warning</h5>
            <p className="text-sm text-slate-400">
              The average knowledge confidence is currently below the 70% benchmark. This typically indicates a high volume of ambiguous documents or model halluncinations. Consider adjusting your Discovery filters or using a more powerful extraction model.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default KnowledgeIntelligence
