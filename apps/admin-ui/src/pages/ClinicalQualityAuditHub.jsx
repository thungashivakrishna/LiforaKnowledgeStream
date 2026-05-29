import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { motion } from 'framer-motion'
import { clsx } from 'clsx'
import {
  ShieldCheck, Activity, Award, CheckCircle, AlertTriangle, Layers, Search, RefreshCw, ChevronRight, HelpCircle, ExternalLink
} from 'lucide-react'

const API_BASE = 'http://localhost:8000/api/v1'

const StatCard = ({ title, value, icon: Icon, subtitle, color = 'brand' }) => (
  <motion.div
    initial={{ opacity: 0, y: 15 }}
    animate={{ opacity: 1, y: 0 }}
    className="bg-slate-900/60 border border-slate-800 backdrop-blur-md rounded-2xl p-6 relative overflow-hidden group hover:border-brand-500/30 transition-all duration-300"
  >
    <div className="flex items-center gap-4 mb-3">
      <div className={clsx("p-3 rounded-xl", color === 'red' ? 'bg-red-500/10' : color === 'green' ? 'bg-emerald-500/10' : 'bg-brand-500/10')}>
        <Icon className={clsx("w-6 h-6", color === 'red' ? 'text-red-400' : color === 'green' ? 'text-emerald-400' : 'text-brand-400')} />
      </div>
      <h3 className="text-slate-400 font-medium text-sm">{title}</h3>
    </div>
    <div className="text-3xl font-extrabold text-white">{value}</div>
    {subtitle && <p className="text-xs text-slate-500 mt-2 font-medium">{subtitle}</p>}
  </motion.div>
)

const ClinicalQualityAuditHub = () => {
  const navigate = useNavigate()
  const [metrics, setMetrics] = useState(null)
  const [pathways, setPathways] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [gradeFilter, setGradeFilter] = useState('ALL')
  const [typeFilter, setTypeFilter] = useState('ALL')
  const [activeTab, setActiveTab] = useState('pathways') // 'pathways' | 'sources' | 'audits'

  const fetchData = async () => {
    try {
      setLoading(true)
      const [mRes, pRes] = await Promise.all([
        axios.get(`${API_BASE}/library/clinical-quality/metrics`),
        axios.get(`${API_BASE}/library/clinical-quality/pathways`)
      ])
      setMetrics(mRes.data)
      setPathways(pRes.data)
    } catch (error) {
      console.error('Error fetching clinical quality metrics:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full py-40">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-500"></div>
      </div>
    )
  }

  const loeDistribution = metrics?.evidence_grade_distribution || {}
  const gradeA_Count = loeDistribution.GRADE_A || 0
  const gradeB_Count = loeDistribution.GRADE_B || 0
  const gradeC_Count = loeDistribution.GRADE_C || 0
  const gradeD_Count = loeDistribution.GRADE_D || 0
  const totalAuditedDocs = gradeA_Count + gradeB_Count + gradeC_Count + gradeD_Count

  // Filtered pathways
  const filteredPathways = pathways.filter(p => {
    const matchesSearch = 
      (p.subject || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (p.object || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (p.fact_text || '').toLowerCase().includes(searchQuery.toLowerCase())
    
    const matchesGrade = gradeFilter === 'ALL' || (p.evidence_grade || 'GRADE_D') === gradeFilter
    const matchesType = typeFilter === 'ALL' || (p.subject_type || 'OTHER') === typeFilter || (p.object_type || 'OTHER') === typeFilter

    return matchesSearch && matchesGrade && matchesType
  })

  const GRADE_BADGES = {
    GRADE_A: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    GRADE_B: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    GRADE_C: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    GRADE_D: 'bg-slate-500/10 text-slate-400 border-slate-500/20'
  }

  const GRADE_LABELS = {
    GRADE_A: 'Grade A: RCTs/Guidelines',
    GRADE_B: 'Grade B: Cohort Studies',
    GRADE_C: 'Grade C: Observational Studies',
    GRADE_D: 'Grade D: Expert Opinion / Consensus'
  }

  const ENTITY_BADGES = {
    INTERVENTION: 'bg-purple-500/10 text-purple-400 border-purple-500/10',
    BIOMARKER: 'bg-blue-500/10 text-blue-400 border-blue-500/10',
    SYMPTOM: 'bg-rose-500/10 text-rose-400 border-rose-500/10',
    CONDITION: 'bg-amber-500/10 text-amber-400 border-amber-500/10',
    OTHER: 'bg-slate-500/10 text-slate-400 border-slate-500/10'
  }

  return (
    <div className="space-y-8 pb-20">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
            <Award className="w-8 h-8 text-brand-500" />
            Clinical Quality Audit Hub
          </h2>
          <p className="text-slate-400 mt-1 text-sm">Dynamically audit, verify, and explore the clinical evidence strength and pathway structure.</p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-xl text-sm font-semibold border border-slate-700/50 transition-all self-start sm:self-center"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh Stats
        </button>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Typed Pathway Facts"
          value={filteredPathways.length.toLocaleString()}
          icon={Activity}
          subtitle={`Out of ${metrics?.total_facts.toLocaleString()} total facts extracted`}
          color="brand"
        />
        <StatCard
          title="Clinical Evidence Grade"
          value={gradeA_Count > 0 ? "Vetted" : "Structured"}
          icon={ShieldCheck}
          subtitle={`${gradeA_Count + gradeB_Count + gradeC_Count} scientifically graded studies`}
          color="green"
        />
        <StatCard
          title="Average Fact Trust"
          value={`${(metrics?.avg_confidence * 100).toFixed(1)}%`}
          icon={CheckCircle}
          subtitle="Dynamic Critic Agent confidence rating"
          color="brand"
        />
        <StatCard
          title="Critic Audit Flags"
          value={metrics?.critic_audits.length || 0}
          icon={AlertTriangle}
          subtitle="Flagged hallucinations or deviations in original data"
          color={metrics?.critic_audits.length > 0 ? 'red' : 'green'}
        />
      </div>

      {/* Evidence Quality Distribution Heatmap */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-md">
        <h3 className="font-bold text-white text-lg mb-4 flex items-center gap-2">
          <Layers className="w-5 h-5 text-brand-500" />
          Clinical Evidence Quality Distribution (Level of Evidence)
        </h3>
        
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-6">
          {[
            { grade: 'GRADE_A', count: gradeA_Count, pct: totalAuditedDocs ? (gradeA_Count / totalAuditedDocs * 100) : 0, color: 'bg-emerald-500', label: 'Grade A (RCTs / Guidelines)' },
            { grade: 'GRADE_B', count: gradeB_Count, pct: totalAuditedDocs ? (gradeB_Count / totalAuditedDocs * 100) : 0, color: 'bg-blue-500', label: 'Grade B (Cohort Studies)' },
            { grade: 'GRADE_C', count: gradeC_Count, pct: totalAuditedDocs ? (gradeC_Count / totalAuditedDocs * 100) : 0, color: 'bg-amber-500', label: 'Grade C (Observational Studies)' },
            { grade: 'GRADE_D', count: gradeD_Count, pct: totalAuditedDocs ? (gradeD_Count / totalAuditedDocs * 100) : 0, color: 'bg-slate-500', label: 'Grade D (Expert Consensus)' }
          ].map(row => (
            <div key={row.grade} className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/40">
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{row.label}</span>
              <div className="flex justify-between items-baseline mt-1">
                <span className="text-xl font-bold text-white">{row.count} docs</span>
                <span className="text-xs text-slate-400">{row.pct.toFixed(0)}%</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden mt-3">
                <div className={clsx("h-full", row.color)} style={{ width: `${row.pct}%` }}></div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Main Tabs Container */}
      <div className="space-y-6">
        <div className="flex border-b border-slate-800">
          {[
            { id: 'pathways', label: 'Clinical Mapped Pathways' },
            { id: 'sources', label: 'Source Reputation Ledger' },
            { id: 'audits', label: 'Critic Audit Log' }
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={clsx(
                "px-6 py-3 text-sm font-semibold transition-all border-b-2 -mb-[2px]",
                activeTab === t.id ? 'border-brand-500 text-white font-bold' : 'border-transparent text-slate-400 hover:text-slate-200'
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab CONTENT 1: Clinical Pathways Explorer */}
        {activeTab === 'pathways' && (
          <div className="space-y-4">
            <div className="flex flex-col md:flex-row gap-4">
              {/* Search Bar */}
              <div className="flex-1 relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  type="text"
                  placeholder="Search pathways (e.g. Inositol, Testosterone, Insulin)..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 transition-colors"
                />
              </div>

              {/* Filters */}
              <div className="flex flex-wrap gap-2">
                <select
                  value={gradeFilter}
                  onChange={(e) => setGradeFilter(e.target.value)}
                  className="px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-400 focus:outline-none focus:border-brand-500"
                >
                  <option value="ALL">All Levels of Evidence</option>
                  <option value="GRADE_A">Grade A (RCTs/Guidelines)</option>
                  <option value="GRADE_B">Grade B (Cohorts)</option>
                  <option value="GRADE_C">Grade C (Observational)</option>
                  <option value="GRADE_D">Grade D (Consensus)</option>
                </select>

                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-400 focus:outline-none focus:border-brand-500"
                >
                  <option value="ALL">All Entity Schemas</option>
                  <option value="INTERVENTION">Interventions</option>
                  <option value="BIOMARKER">Biomarkers</option>
                  <option value="SYMPTOM">Symptoms</option>
                  <option value="CONDITION">Conditions</option>
                </select>
              </div>
            </div>

            {/* Mapped Relationships Table */}
            <div className="bg-slate-900/30 border border-slate-800/80 rounded-2xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-500 text-left border-b border-slate-800 bg-slate-950/40">
                      <th className="p-4 font-semibold text-xs uppercase tracking-wider">Subject Entity (Source)</th>
                      <th className="p-4 font-semibold text-xs uppercase tracking-wider">Clinical Predicate</th>
                      <th className="p-4 font-semibold text-xs uppercase tracking-wider">Object Entity (Target)</th>
                      <th className="p-4 font-semibold text-xs uppercase tracking-wider">Primary Source Document</th>
                      <th className="p-4 font-semibold text-xs text-right uppercase tracking-wider">LoE Grade</th>
                      <th className="p-4 font-semibold text-xs text-right uppercase tracking-wider">Audited Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPathways.map((p, idx) => (
                      <tr key={idx} className="border-b border-slate-800/40 hover:bg-slate-950/20 transition-all">
                        <td className="p-4">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-white">{p.subject}</span>
                            <span className={clsx("text-[9px] font-bold px-2 py-0.5 rounded border uppercase", ENTITY_BADGES[p.subject_type] || ENTITY_BADGES.OTHER)}>
                              {p.subject_type}
                            </span>
                          </div>
                        </td>
                        <td className="p-4 text-brand-400 font-semibold font-mono text-xs">{p.predicate}</td>
                        <td className="p-4">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-slate-300">{p.object}</span>
                            <span className={clsx("text-[9px] font-bold px-2 py-0.5 rounded border uppercase", ENTITY_BADGES[p.object_type] || ENTITY_BADGES.OTHER)}>
                              {p.object_type}
                            </span>
                          </div>
                        </td>
                        <td className="p-4">
                          {p.document_id ? (
                            <button
                              onClick={() => navigate('/documents', { state: { selectedDocId: p.document_id } })}
                              className="text-brand-400 hover:text-brand-350 font-medium hover:underline transition-all text-xs text-left max-w-[200px] truncate flex items-center gap-1.5 capitalize"
                              title={p.document_title}
                            >
                              <ExternalLink className="w-3 h-3 flex-shrink-0 opacity-70" />
                              {p.document_title}
                            </button>
                          ) : (
                            <span className="text-slate-500 text-xs italic">No Source Ref</span>
                          )}
                        </td>
                        <td className="p-4 text-right">
                          <span className={clsx("text-[10px] font-bold px-2.5 py-1 rounded border", GRADE_BADGES[p.evidence_grade || 'GRADE_D'] || GRADE_BADGES.GRADE_D)}>
                            {(p.evidence_grade || 'GRADE_D').replace('_', ' ')}
                          </span>
                        </td>
                        <td className="p-4 text-right font-mono font-bold text-white">{((p.confidence || 0) * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                    {filteredPathways.length === 0 && (
                      <tr>
                        <td colSpan={5} className="p-8 text-center text-slate-500 font-medium">No matching pathway relationships found.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab CONTENT 2: Source Reputation Ledger */}
        {activeTab === 'sources' && (
          <div className="bg-slate-900/30 border border-slate-800/80 rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-500 text-left border-b border-slate-800 bg-slate-950/40">
                    <th className="p-4 font-semibold text-xs uppercase tracking-wider">Domain Name</th>
                    <th className="p-4 font-semibold text-xs uppercase tracking-wider">Reputation Type</th>
                    <th className="p-4 font-semibold text-xs text-right uppercase tracking-wider">Documents Ingested</th>
                    <th className="p-4 font-semibold text-xs text-right uppercase tracking-wider">Avg Priority Score</th>
                  </tr>
                </thead>
                <tbody>
                  {metrics?.domain_ledger.map((d, i) => (
                    <tr key={i} className="border-b border-slate-800/40 hover:bg-slate-950/20 transition-all">
                      <td className="p-4 font-bold text-white">{d.name}</td>
                      <td className="p-4">
                        <span className="text-slate-400 font-mono text-xs uppercase tracking-wide bg-slate-800/40 px-2.5 py-1 rounded border border-slate-800">
                          {d.source_type.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="p-4 text-right text-slate-300 font-bold">{d.document_count}</td>
                      <td className="p-4 text-right font-mono font-bold text-brand-400">{(d.avg_priority_score * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                  {(!metrics?.domain_ledger || metrics?.domain_ledger.length === 0) && (
                    <tr>
                      <td colSpan={4} className="p-8 text-center text-slate-500">No reputable domains audited yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab CONTENT 3: Critic Audit Logs */}
        {activeTab === 'audits' && (
          <div className="space-y-4">
            <div className="bg-amber-500/10 border border-amber-500/20 p-4 rounded-xl flex gap-3 text-sm text-slate-400">
              <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
              <span>The logs below capture real-time hallucination audits compiled by our Critic Agent comparing raw pipeline outputs against primary clinical source texts.</span>
            </div>
            
            <div className="space-y-4">
              {metrics?.critic_audits.map((a, i) => (
                <div key={i} className="bg-slate-900/50 border border-slate-800 p-6 rounded-2xl flex flex-col gap-3">
                  <div className="flex justify-between items-start gap-4">
                    <span className="text-[10px] font-bold text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded tracking-wider uppercase">
                      Hallucination Flagged
                    </span>
                    {a.document_id ? (
                      <button
                        onClick={() => navigate('/documents', { state: { selectedDocId: a.document_id } })}
                        className="text-slate-400 hover:text-brand-400 transition-colors text-xs font-mono font-medium hover:underline text-right truncate max-w-[300px] flex items-center gap-1.5"
                        title={a.document_title}
                      >
                        <ExternalLink className="w-3 h-3 flex-shrink-0 opacity-70" />
                        {a.document_title}
                      </button>
                    ) : (
                      <span className="text-slate-500 text-xs font-mono truncate max-w-[300px]">{a.document_title}</span>
                    )}
                  </div>
                  <div>
                    <span className="text-slate-500 text-xs uppercase tracking-wider block font-bold mb-1">Extracted Fact</span>
                    <p className="text-slate-200 text-sm italic">"{a.fact_text}"</p>
                  </div>
                  <div className="border-t border-slate-800/60 pt-3">
                    <span className="text-amber-400 text-xs uppercase tracking-wider block font-bold mb-1 flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      Critic Integrity Critique
                    </span>
                    <p className="text-slate-400 text-xs leading-relaxed">{a.critique}</p>
                  </div>
                </div>
              ))}
              {(!metrics?.critic_audits || metrics?.critic_audits.length === 0) && (
                <div className="p-8 text-center text-slate-500 bg-slate-900/30 border border-slate-800 rounded-2xl">
                  No active hallucination audits flagged. The current knowledge base is 100% compliant.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default ClinicalQualityAuditHub
