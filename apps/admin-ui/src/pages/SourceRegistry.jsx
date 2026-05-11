import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { 
  Plus, 
  Search, 
  Filter, 
  ExternalLink, 
  MoreVertical, 
  ChevronRight, 
  CheckCircle2, 
  Clock, 
  PauseCircle, 
  XCircle,
  AlertCircle,
  History,
  Settings2,
  Database
} from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'

const API_BASE = '/api/v1'

const STATUS_STYLES = {
  CANDIDATE: "bg-amber-500/10 text-amber-500 border-amber-500/20",
  UNDER_REVIEW: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  APPROVED_ACTIVE: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
  APPROVED_LIMITED: "bg-cyan-500/10 text-cyan-500 border-cyan-500/20",
  PAUSED: "bg-slate-500/10 text-slate-500 border-slate-500/20",
  BLOCKED: "bg-rose-500/10 text-rose-500 border-rose-500/20",
  RETIRED: "bg-slate-700/10 text-slate-400 border-slate-700/20",
}

const STATUS_ICONS = {
  CANDIDATE: Clock,
  UNDER_REVIEW: Search,
  APPROVED_ACTIVE: CheckCircle2,
  APPROVED_LIMITED: CheckCircle2,
  PAUSED: PauseCircle,
  BLOCKED: XCircle,
  RETIRED: AlertCircle,
}

const STAT_STYLES = {
  brand: "bg-brand-500/10 text-brand-500",
  emerald: "bg-emerald-500/10 text-emerald-500",
  amber: "bg-amber-500/10 text-amber-500",
  rose: "bg-rose-500/10 text-rose-500",
}

const formatEnumLabel = (value) => value.toLowerCase().replaceAll('_', ' ')

const StatusBadge = ({ status }) => {
  const Icon = STATUS_ICONS[status] || AlertCircle

  return (
    <span className={clsx("flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider border", STATUS_STYLES[status])}>
      <Icon className="w-3 h-3" />
      {formatEnumLabel(status)}
    </span>
  )
}

const SourceRegistry = () => {
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedSourceId, setSelectedSourceId] = useState(null)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)

  useEffect(() => {
    fetchSources()
  }, [])

  const fetchSources = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE}/sources`)
      setSources(response.data.items)
    } catch (error) {
      console.error('Error fetching sources:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSourceAction = async (id, action) => {
    try {
      await axios.post(`${API_BASE}/sources/${id}/${action}`, {
        actor: 'admin',
        reason: 'Manual action via admin UI'
      })
      fetchSources()
      if (selectedSourceId === id) {
        // Refresh detail view
      }
    } catch (error) {
      console.error(`Error performing ${action}:`, error)
    }
  }

  const filteredSources = sources.filter(s => 
    s.name.toLowerCase().includes(search.toLowerCase()) || 
    s.root_url.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Source Registry</h2>
          <p className="text-slate-400 mt-1">Manage health knowledge sources and their trust policies.</p>
        </div>
        <button 
          onClick={() => setIsCreateModalOpen(true)}
          className="btn-primary flex items-center justify-center gap-2"
        >
          <Plus className="w-5 h-5" />
          Add Source
        </button>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Sources', value: sources.length, icon: Database, color: 'brand' },
          { label: 'Active', value: sources.filter(s => s.approval_status === 'APPROVED_ACTIVE').length, icon: CheckCircle2, color: 'emerald' },
          { label: 'Pending Review', value: sources.filter(s => s.approval_status === 'CANDIDATE').length, icon: Clock, color: 'amber' },
          { label: 'Blocked', value: sources.filter(s => s.approval_status === 'BLOCKED').length, icon: XCircle, color: 'rose' },
        ].map((stat, i) => (
          <div key={i} className="glass p-4 rounded-2xl flex items-center gap-4">
            <div className={clsx("w-12 h-12 rounded-xl flex items-center justify-center", STAT_STYLES[stat.color])}>
              <stat.icon className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">{stat.label}</p>
              <p className="text-2xl font-bold">{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Filters & Table */}
      <div className="glass rounded-2xl overflow-hidden flex flex-col">
        <div className="p-4 border-b border-slate-800/50 flex flex-col md:flex-row gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 w-5 h-5" />
            <input 
              type="text" 
              placeholder="Search by name or URL..." 
              className="input-field pl-10"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button className="btn-secondary flex items-center justify-center gap-2">
            <Filter className="w-5 h-5" />
            Filters
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-900/30 text-slate-400 uppercase text-[10px] font-bold tracking-widest border-b border-slate-800/50">
                <th className="px-6 py-4">Source</th>
                <th className="px-6 py-4">Type</th>
                <th className="px-6 py-4">Frameworks</th>
                <th className="px-6 py-4">Tier</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {loading ? (
                Array(5).fill(0).map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-6 py-4"><div className="h-4 bg-slate-800 rounded w-32"></div></td>
                    <td className="px-6 py-4"><div className="h-4 bg-slate-800 rounded w-20"></div></td>
                    <td className="px-6 py-4"><div className="h-4 bg-slate-800 rounded w-24"></div></td>
                    <td className="px-6 py-4"><div className="h-4 bg-slate-800 rounded w-8"></div></td>
                    <td className="px-6 py-4"><div className="h-4 bg-slate-800 rounded w-16"></div></td>
                    <td className="px-6 py-4 text-right"><div className="h-4 bg-slate-800 rounded w-8 ml-auto"></div></td>
                  </tr>
                ))
              ) : filteredSources.map((source) => (
                <tr 
                  key={source.id} 
                  className="group hover:bg-slate-800/30 transition-colors cursor-pointer"
                  onClick={() => setSelectedSourceId(source.id)}
                >
                  <td className="px-6 py-4">
                    <div className="flex flex-col">
                      <span className="font-semibold text-slate-100 group-hover:text-brand-400 transition-colors">{source.name}</span>
                      <span className="text-xs text-slate-500 truncate max-w-xs">{source.root_url}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-xs font-medium text-slate-400 bg-slate-800/50 px-2 py-0.5 rounded uppercase tracking-wider">
                      {formatEnumLabel(source.source_type)}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {source.framework_maps.map(fm => (
                        <span 
                          key={fm.framework} 
                          className={clsx(
                            "text-[10px] px-1.5 py-0.5 rounded font-bold uppercase",
                            fm.is_primary ? "bg-brand-500/20 text-brand-400" : "bg-slate-800 text-slate-500"
                          )}
                        >
                          {fm.framework.split('_')[0]}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1">
                      <div className={clsx(
                        "w-2 h-2 rounded-full",
                        source.trust_tier <= 2 ? "bg-emerald-500" : source.trust_tier <= 3 ? "bg-amber-500" : "bg-rose-500"
                      )}></div>
                      <span className="font-bold">{source.trust_tier}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={source.approval_status} />
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSourceAction(source.id, source.approval_status === 'PAUSED' ? 'approve' : 'pause');
                        }}
                        className="p-2 text-slate-500 hover:text-slate-100 hover:bg-slate-700/50 rounded-lg transition-all"
                        title={source.approval_status === 'PAUSED' ? 'Resume' : 'Pause'}
                      >
                        {source.approval_status === 'PAUSED' ? <CheckCircle2 className="w-5 h-5" /> : <PauseCircle className="w-5 h-5" />}
                      </button>
                      <button 
                        className="p-2 text-slate-500 hover:text-slate-100 hover:bg-slate-700/50 rounded-lg transition-all"
                        title="Source Settings"
                      >
                        <Settings2 className="w-5 h-5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        
        {!loading && filteredSources.length === 0 && (
          <div className="p-12 text-center">
            <div className="w-16 h-16 bg-slate-900 rounded-full flex items-center justify-center mx-auto mb-4 border border-slate-800">
              <Database className="text-slate-600 w-8 h-8" />
            </div>
            <p className="text-slate-400 font-medium">No sources found matching your search.</p>
          </div>
        )}
      </div>

      {/* Add Source Modal */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-6">
            <h3 className="text-xl font-bold text-white">Add New Health Source</h3>
            
            <form onSubmit={async (e) => {
              e.preventDefault();
              const formData = new FormData(e.target);
              const payload = {
                name: formData.get('name'),
                root_url: formData.get('root_url'),
                source_type: formData.get('source_type'),
                primary_framework: 'EVIDENCE_BASED_WESTERN_MEDICINE',
                trust_tier: parseInt(formData.get('trust_tier') || '3'),
                approval_status: 'APPROVED_ACTIVE'
              };
              
              try {
                await axios.post(`${API_BASE}/sources`, payload);
                setIsCreateModalOpen(false);
                fetchSources();
              } catch (error) {
                console.error(error);
                alert("Failed to create source. Please check the inputs.");
              }
            }} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Source Name</label>
                <input type="text" name="name" required className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white" placeholder="e.g. Lancet Endocrinology" />
              </div>
              
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Root URL</label>
                <input type="url" name="root_url" required className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white" placeholder="https://thelancet.com" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Type</label>
                  <select name="source_type" className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white">
                    <option value="ACADEMIC_SOURCE">Academic Journal</option>
                    <option value="PUBLIC_HEALTH_SOURCE">Public Health</option>
                    <option value="NUTRITION_GUIDANCE_SOURCE">Nutrition Guidance</option>
                    <option value="RECIPE_OR_LIFESTYLE_SOURCE">Lifestyle/Recipe</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Trust Tier</label>
                  <select name="trust_tier" className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white">
                    <option value="1">Tier 1 (Highest)</option>
                    <option value="2">Tier 2</option>
                    <option value="3">Tier 3 (Medium)</option>
                    <option value="4">Tier 4 (Low)</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
                <button 
                  type="button" 
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-bold"
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-xl font-bold"
                >
                  Create Source
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default SourceRegistry
