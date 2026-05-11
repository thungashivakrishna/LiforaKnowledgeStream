import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { 
  FileText, 
  Search, 
  Tag, 
  Calendar, 
  Link as LinkIcon, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  BrainCircuit,
  Hash,
  Share2,
  X,
  ExternalLink,
  Database
} from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'
import { motion, AnimatePresence } from 'framer-motion'
import KnowledgeGraph from '../components/KnowledgeGraph'

const API_BASE = '/api/v1'

const KnowledgeLibrary = () => {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedDocId, setSelectedDocId] = useState(null)
  const [docDetails, setDocDetails] = useState(null)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [activeTab, setActiveTab] = useState('content')

  useEffect(() => {
    fetchDocuments(search)
  }, [])

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchDocuments(search)
    }, 500)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (selectedDocId) {
      fetchDocumentDetails(selectedDocId)
    }
  }, [selectedDocId])

  const fetchDocuments = async (query = '') => {
    try {
      setLoading(true)
      const params = query ? { q: query } : {}
      const response = await axios.get(`${API_BASE}/library/documents`, { params })
      setDocuments(response.data.items)
    } catch (error) {
      console.error('Error fetching documents:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchDocumentDetails = async (id) => {
    try {
      setLoadingDetails(true)
      const response = await axios.get(`${API_BASE}/library/documents/${id}`)
      setDocDetails(response.data)
    } catch (error) {
      console.error('Error fetching document details:', error)
    } finally {
      setLoadingDetails(false)
    }
  }

  const filteredDocs = documents

  return (
    <div className="flex h-full gap-6">
      {/* Left Pane: Catalog */}
      <div className={clsx("flex flex-col transition-all duration-300", selectedDocId ? "w-1/3" : "w-full")}>
        <div className="mb-6 flex justify-between items-end">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
              <BrainCircuit className="w-8 h-8 text-brand-500" />
              Knowledge Library
            </h2>
            <p className="text-slate-400 mt-1">Explore structured knowledge extracted from your trusted sources.</p>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 w-5 h-5" />
          <input 
            type="text" 
            placeholder="Search documents..." 
            className="input-field pl-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Catalog Grid/List */}
        <div className={clsx("overflow-y-auto pr-2 custom-scrollbar", selectedDocId ? "space-y-4" : "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6")}>
          {loading ? (
            Array(6).fill(0).map((_, i) => (
              <div key={i} className="glass p-6 rounded-2xl animate-pulse h-48">
                <div className="h-6 bg-slate-800 rounded w-3/4 mb-4"></div>
                <div className="h-4 bg-slate-800 rounded w-1/2 mb-2"></div>
                <div className="h-4 bg-slate-800 rounded w-full mt-6"></div>
              </div>
            ))
          ) : filteredDocs.length === 0 ? (
            <div className="col-span-full p-12 text-center glass rounded-2xl">
              <FileText className="text-slate-600 w-12 h-12 mx-auto mb-4" />
              <p className="text-slate-400 font-medium text-lg">No processed documents found.</p>
              <p className="text-slate-500 mt-2">Documents will appear here once they complete the ingestion pipeline.</p>
            </div>
          ) : (
            filteredDocs.map((doc) => (
              <div 
                key={doc.id}
                onClick={() => setSelectedDocId(doc.id)}
                className={clsx(
                  "p-5 rounded-2xl border transition-all cursor-pointer relative group",
                  selectedDocId === doc.id 
                    ? "bg-brand-900/20 border-brand-500 shadow-lg shadow-brand-500/10" 
                    : "glass hover:bg-slate-800/50 hover:border-slate-700"
                )}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-bold text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded-full">
                      <CheckCircle2 className="w-3 h-3" />
                      Extracted
                    </span>
                  </div>
                  <span className="text-xs text-slate-500 font-medium">
                    {format(new Date(doc.created_at), 'MMM d, yyyy')}
                  </span>
                </div>
                
                <h3 className="font-bold text-slate-200 text-lg mb-2 line-clamp-2 leading-tight group-hover:text-brand-400 transition-colors capitalize">
                  {doc.title || doc.canonical_url.split('/').filter(Boolean).pop().replace('.htm', '').replace('.html', '').replace(/[_-]/g, ' ')}
                </h3>

                {doc.relevance_score && (
                  <div className="flex items-center gap-2 mb-3">
                    <div className="h-1.5 flex-1 bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-brand-500" 
                        style={{ width: `${Math.min(100, doc.relevance_score * 20)}%` }}
                      ></div>
                    </div>
                    <span className="text-[10px] font-bold text-brand-400">
                      {doc.relevance_score.toFixed(1)} MATCH
                    </span>
                  </div>
                )}
                
                <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-2 truncate">
                  <LinkIcon className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="truncate">{doc.source_name || doc.canonical_url}</span>
                </div>

                <div className="flex flex-wrap gap-2 mb-4">
                   <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-500 border border-slate-700">
                    {doc.source_type?.replace('_', ' ')}
                  </span>
                  {doc.source_type === 'PRESCRIPTION_SOURCE' && (
                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">
                      Rx Insight
                    </span>
                  )}
                  {doc.source_type === 'CLINICAL_REPORT_SOURCE' && (
                    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/30">
                      Clinical Report
                    </span>
                  )}
                </div>

                {!selectedDocId && doc.summary_preview && (
                  <p className="text-sm text-slate-400 line-clamp-3 mb-4">
                    {doc.summary_preview}
                  </p>
                )}

                <div className="flex flex-wrap gap-1.5 mt-auto">
                  {doc.tags?.slice(0, 3).map((tag, i) => (
                    <span key={i} className="text-[10px] px-2 py-1 rounded bg-slate-800 text-slate-300 font-medium truncate max-w-[120px]">
                      {tag.tag_value}
                    </span>
                  ))}
                  {doc.tags?.length > 3 && (
                    <span className="text-[10px] px-2 py-1 rounded bg-slate-800 text-slate-500 font-medium">
                      +{doc.tags.length - 3} more
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right Pane: Document Details (Knowledge Graph) */}
      <AnimatePresence>
        {selectedDocId && (
          <motion.div 
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="w-2/3 flex flex-col glass rounded-3xl border border-slate-800 overflow-hidden shadow-2xl relative"
          >
            {loadingDetails || !docDetails ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
              </div>
            ) : (
              <>
                {/* Header */}
                <div className="p-8 border-b border-slate-800 bg-slate-900/50 relative">
                  <button 
                    onClick={() => setSelectedDocId(null)}
                    className="absolute top-6 right-6 p-2 rounded-full hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                  
                  <div className="flex flex-wrap gap-2 mb-4">
                    {docDetails.tags?.map((tag) => (
                      <span key={tag.id} className={clsx(
                        "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium border",
                        tag.tag_type === 'FRAMEWORK' 
                          ? "bg-amber-500/10 text-amber-400 border-amber-500/30 ring-1 ring-amber-500/20" 
                          : "bg-brand-500/10 text-brand-400 border-brand-500/20"
                      )}>
                        <Hash className="w-3 h-3" />
                        {tag.tag_type === 'FRAMEWORK' ? `FRAMEWORK: ${tag.tag_value}` : tag.tag_value}
                      </span>
                    ))}
                  </div>

                  <h2 className="text-2xl font-bold text-white mb-4 pr-12 leading-snug capitalize">
                    {docDetails.title || docDetails.canonical_url.split('/').filter(Boolean).pop().replace('.htm', '').replace('.html', '').replace(/[_-]/g, ' ')}
                  </h2>

                  <div className="flex flex-wrap items-center gap-6 text-sm text-slate-400">
                    <span className="flex items-center gap-1.5 text-brand-400 font-semibold bg-brand-500/10 px-2 py-1 rounded">
                      <Database className="w-4 h-4" />
                      {docDetails.source_name}
                    </span>
                    <span className="flex items-center gap-1.5 bg-slate-800 px-2 py-1 rounded">
                      <Tag className="w-4 h-4" />
                      {docDetails.source_type?.replace('_', ' ')}
                    </span>
                    <a href={docDetails.canonical_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:text-brand-400 transition-colors">
                      <ExternalLink className="w-4 h-4" />
                      Original Link
                    </a>
                    <div className="flex items-center gap-1.5">
                      <Calendar className="w-4 h-4" />
                      {format(new Date(docDetails.created_at), 'MMM d, yyyy')}
                    </div>
                  </div>
                </div>

                {/* Tabs */}
                <div className="flex px-8 border-b border-slate-800">
                  <button 
                    onClick={() => setActiveTab('content')}
                    className={clsx(
                      "px-6 py-3 text-sm font-bold transition-all border-b-2",
                      activeTab === 'content' ? "border-brand-500 text-white" : "border-transparent text-slate-500 hover:text-slate-300"
                    )}
                  >
                    Content & Insights
                  </button>
                  <button 
                    onClick={() => setActiveTab('graph')}
                    className={clsx(
                      "px-6 py-3 text-sm font-bold transition-all border-b-2",
                      activeTab === 'graph' ? "border-brand-500 text-white" : "border-transparent text-slate-500 hover:text-slate-300"
                    )}
                  >
                    Semantic Graph
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto p-8 custom-scrollbar space-y-10">
                  {activeTab === 'graph' ? (
                    <section className="h-[600px]">
                       <h3 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
                        <Share2 className="w-5 h-5 text-emerald-400" />
                        Interactive Entity Map
                      </h3>
                      <KnowledgeGraph 
                        facts={docDetails.facts} 
                        tags={docDetails.tags} 
                        width={window.innerWidth * 0.4} 
                        height={500} 
                      />
                    </section>
                  ) : (
                    <>
                  
                  {/* AI Summary */}
                  {docDetails.summary && (
                    <section>
                      <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                        <FileText className="w-5 h-5 text-brand-400" />
                        AI Summary
                      </h3>
                      <div className="prose prose-invert max-w-none text-slate-300 bg-slate-900/50 p-6 rounded-2xl border border-slate-800/50 leading-relaxed">
                        {docDetails.summary.summary_text}
                      </div>
                    </section>
                  )}

                  {/* Extracted Facts (Actionable Insights) */}
                  <section>
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <Share2 className="w-5 h-5 text-emerald-400" />
                        Knowledge Graph & Actionable Insights
                      </h3>
                      <span className="text-sm font-medium text-slate-500 bg-slate-800 px-3 py-1 rounded-full">
                        {docDetails.facts?.length || 0} Entities Extracted
                      </span>
                    </div>

                    <div className="grid grid-cols-1 gap-4">
                      {docDetails.facts?.map((fact) => {
                        const isActionable = ["includes", "requires", "suggests", "prescribes", "contains", "steps"].some(p => fact.predicate?.toLowerCase().includes(p))
                        
                        return (
                          <div key={fact.id} className={clsx(
                            "transition-all border rounded-xl p-4 flex flex-col gap-3",
                            isActionable ? "bg-emerald-900/10 border-emerald-500/30 ring-1 ring-emerald-500/20" : "bg-slate-900/40 border-slate-800/50"
                          )}>
                            
                            <div className="flex items-center justify-between">
                              {isActionable && (
                                <span className="text-[10px] font-black uppercase tracking-tighter bg-emerald-500 text-emerald-950 px-1.5 py-0.5 rounded mb-1 w-fit">
                                  Actionable Guideline
                                </span>
                              )}
                              <span className="text-[10px] text-slate-500 font-mono">CONFIDENCE: {(fact.confidence * 100).toFixed(0)}%</span>
                            </div>

                            {/* S-P-O Visualizer */}
                            {(fact.subject && fact.predicate && fact.object) ? (
                              <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                                <span className="px-3 py-1.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-lg">
                                  {fact.subject}
                                </span>
                                <span className="text-slate-500 text-xs uppercase tracking-widest px-1 font-bold">
                                  {fact.predicate}
                                </span>
                                <span className="px-3 py-1.5 bg-brand-500/10 text-brand-400 border border-brand-500/20 rounded-lg">
                                  {fact.object}
                                </span>
                              </div>
                            ) : null}

                            <div className="text-slate-300 text-sm pl-1 border-l-2 border-brand-500/30 italic">
                              "{fact.fact_text}"
                            </div>
                            
                          </div>
                        )
                      })}
                    </div>
                  </section>
                    </>
                  )}

                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default KnowledgeLibrary
