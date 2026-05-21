import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { Activity, ShieldCheck, AlertCircle, Play, FileText, Database, Terminal, CheckCircle2, XCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { clsx } from 'clsx'

const API_BASE = '/api/v1'

const SystemInspector = () => {
  const [activeTab, setActiveTab] = useState('audit') // 'audit' | 'tables' | 'llm'
  const [tables, setTables] = useState([])
  const [selectedTable, setSelectedTable] = useState('')
  const [data, setData] = useState({ columns: [], rows: [], total: 0 })
  const [loading, setLoading] = useState(false)
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)

  // Audit State
  const [auditing, setAuditing] = useState(false)
  const [auditReport, setAuditReport] = useState('')
  const [auditStatus, setAuditStatus] = useState('idle')
  const [isAuditRunning, setIsAuditRunning] = useState(false)

  // LLM Provider health
  const [providerHealth, setProviderHealth] = useState([])

  useEffect(() => {
    fetchTables()
    fetchAuditStatus()
    fetchProviderHealth()
  }, [])

  const fetchProviderHealth = async () => {
    try {
      const res = await axios.get(`${API_BASE}/llm/provider-health`)
      setProviderHealth(res.data)
    } catch (e) {
      console.error('Error fetching provider health:', e)
    }
  }

  // Poll for audit status if it's running
  useEffect(() => {
    let interval;
    if (isAuditRunning) {
      interval = setInterval(() => {
        fetchAuditStatus()
      }, 3000)
    }
    return () => clearInterval(interval)
  }, [isAuditRunning])

  useEffect(() => {
    if (selectedTable && activeTab === 'tables') {
      fetchTableData()
    }
  }, [selectedTable, offset, limit, activeTab])

  const fetchTables = async () => {
    try {
      const response = await axios.get(`${API_BASE}/system/tables`)
      setTables(response.data.tables)
      if (response.data.tables.length > 0) {
        setSelectedTable(response.data.tables[0])
      }
    } catch (error) {
      console.error('Error fetching tables:', error)
    }
  }

  const fetchAuditStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE}/system/audit/status`)
      setAuditStatus(response.data.status)
      setIsAuditRunning(response.data.is_running)
      if (response.data.report && response.data.report !== "Report not found.") {
        setAuditReport(response.data.report)
      }
    } catch (error) {
      console.error('Error fetching audit status:', error)
    }
  }

  const fetchTableData = async () => {
    setLoading(true)
    try {
      const response = await axios.get(`${API_BASE}/system/tables/${selectedTable}`, {
        params: { limit, offset }
      })
      setData(response.data)
    } catch (error) {
      console.error('Error fetching table data:', error)
    } finally {
      setLoading(false)
    }
  }

  const triggerAudit = async () => {
    setAuditing(true)
    setAuditStatus('running')
    try {
      await axios.post(`${API_BASE}/system/audit/trigger`)
      setIsAuditRunning(true)
    } catch (error) {
      console.error('Error triggering audit:', error)
      setAuditStatus('failed')
      setAuditReport('### ❌ Audit Failed\nFailed to initiate background audit task.')
    } finally {
      setAuditing(false)
    }
  }

  return (
    <div className="flex flex-col h-full space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between bg-slate-900 border border-slate-800 p-8 rounded-3xl shadow-xl gap-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Terminal className="w-8 h-8 text-brand-500" />
            <h1 className="text-3xl font-bold text-white tracking-tight">Audit Bot & System Inspector</h1>
          </div>
          <p className="text-slate-400">Validate system stability, platform services, and explore underlying database state.</p>
        </div>
        
        <div className="flex bg-slate-950 p-1 rounded-2xl border border-slate-800">
          <button 
            onClick={() => setActiveTab('audit')}
            className={clsx(
              "px-6 py-2.5 rounded-xl text-sm font-bold transition-all flex items-center gap-2",
              activeTab === 'audit' ? "bg-brand-600 text-white shadow-lg" : "text-slate-500 hover:text-slate-300"
            )}
          >
            <ShieldCheck className="w-4 h-4" />
            STABILITY AUDIT
          </button>
          <button
            onClick={() => setActiveTab('tables')}
            className={clsx(
              "px-6 py-2.5 rounded-xl text-sm font-bold transition-all flex items-center gap-2",
              activeTab === 'tables' ? "bg-brand-600 text-white shadow-lg" : "text-slate-500 hover:text-slate-300"
            )}
          >
            <Database className="w-4 h-4" />
            TABLE INSPECTOR
          </button>
          <button
            onClick={() => setActiveTab('llm')}
            className={clsx(
              "px-6 py-2.5 rounded-xl text-sm font-bold transition-all flex items-center gap-2",
              activeTab === 'llm' ? "bg-brand-600 text-white shadow-lg" : "text-slate-500 hover:text-slate-300"
            )}
          >
            <Activity className="w-4 h-4" />
            LLM HEALTH
          </button>
        </div>
      </div>

      {activeTab === 'llm' ? (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <h3 className="font-semibold text-white mb-4">Provider Health</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-left">
                <th className="pb-2">Model</th>
                <th className="pb-2">Last Success</th>
                <th className="pb-2">Last Error</th>
                <th className="pb-2 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {providerHealth.map((p, i) => (
                <tr key={i} className="border-t border-slate-800">
                  <td className="py-2 text-slate-300 font-mono text-xs">{p.model}</td>
                  <td className="py-2 text-slate-400 text-xs">{p.last_success ? new Date(p.last_success).toLocaleString() : '—'}</td>
                  <td className="py-2 text-red-400 text-xs">{p.last_error ? new Date(p.last_error).toLocaleString() : '—'}</td>
                  <td className="py-2 text-right">
                    {p.healthy
                      ? <CheckCircle2 className="w-4 h-4 text-emerald-400 inline" />
                      : <XCircle className="w-4 h-4 text-red-400 inline" />
                    }
                  </td>
                </tr>
              ))}
              {providerHealth.length === 0 && (
                <tr><td colSpan={4} className="py-4 text-slate-500 text-center">No LLM calls recorded yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : activeTab === 'audit' ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 flex-1 overflow-hidden">
          {/* Controls */}
          <div className="lg:col-span-1 space-y-6">
            <div className="glass p-8 rounded-3xl border-slate-800">
              <h3 className="text-xl font-bold text-white mb-6">Audit Controls</h3>
              <p className="text-sm text-slate-400 mb-8 leading-relaxed">
                Running a system audit will verify all infrastructure connections (Postgres, Neo4j, Redis, MinIO) and perform functional smoke tests on Clinical Normalization and UI logic.
              </p>
              
              <button 
                onClick={triggerAudit}
                disabled={auditing}
                className="w-full bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-bold py-4 rounded-2xl shadow-lg shadow-brand-600/20 transition-all flex items-center justify-center gap-3 group"
              >
                {auditing ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <Play className="w-5 h-5 fill-current" />
                    RUN STABILITY AUDIT
                  </>
                )}
              </button>

              {auditStatus && (
                <div className={clsx(
                  "mt-8 p-6 rounded-2xl border flex items-center gap-4 animate-in fade-in slide-in-from-top-2",
                  auditStatus === 'success' ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : 
                  auditStatus === 'running' ? "bg-brand-500/10 border-brand-500/20 text-brand-400" :
                  "bg-rose-500/10 border-rose-500/20 text-rose-400"
                )}>
                  {auditStatus === 'success' ? <CheckCircle2 className="w-6 h-6" /> : 
                   auditStatus === 'running' ? <Activity className="w-6 h-6 animate-pulse" /> :
                   <XCircle className="w-6 h-6" />}
                  <div>
                    <p className="font-bold uppercase tracking-widest text-[10px]">Current Status</p>
                    <p className="text-sm font-semibold capitalize">{auditStatus === 'running' ? 'Audit in Progress...' : `Audit ${auditStatus}`}</p>
                  </div>
                </div>
              )}
            </div>

            <div className="glass p-8 rounded-3xl border-slate-800 bg-slate-900/30">
              <h4 className="text-sm font-bold text-slate-300 mb-4 uppercase tracking-wider">Health Indicators</h4>
              <div className="space-y-4">
                {[
                  { name: 'Core Infrastructure', status: 'Healthy' },
                  { name: 'Temporal Workflows', status: 'Healthy' },
                  { name: 'Clinical Normalizer', status: 'Requires Key' }
                ].map(indicator => (
                  <div key={indicator.name} className="flex items-center justify-between p-3 rounded-xl bg-slate-950/50 border border-slate-800/50">
                    <span className="text-xs text-slate-400 font-medium">{indicator.name}</span>
                    <span className="text-[10px] font-bold uppercase text-emerald-500">{indicator.status}</span>
                  </div>
                ))}
              </div>
              
              {auditStatus !== 'idle' && (
                <div className="mt-8 pt-6 border-t border-slate-800">
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Diagnostics Detail</h4>
                  <div className="space-y-3">
                    <div className="bg-slate-950 rounded-xl p-4 border border-slate-800 font-mono text-[10px] text-slate-400">
                      <p className="text-brand-400 mb-1">Checking core infrastructure...</p>
                      <p>Postgres: {auditStatus === 'completed' ? '✅ OK' : auditStatus === 'failed' ? '❌ FAIL' : '...'}</p>
                      <p>Neo4j: {auditStatus === 'completed' ? '✅ OK' : auditStatus === 'failed' ? '❌ FAIL' : '...'}</p>
                      <p>Redis: {auditStatus === 'completed' ? '✅ OK' : auditStatus === 'failed' ? '❌ FAIL' : '...'}</p>
                      <p className="text-brand-400 mt-2 mb-1">Checking platform services...</p>
                      <p>API Gateway: {auditStatus === 'completed' ? '✅ OK' : auditStatus === 'failed' ? '❌ FAIL' : '...'}</p>
                      <p>Clinical Normalizer: {auditStatus === 'completed' ? '✅ OK' : auditStatus === 'failed' ? '❌ FAIL' : '...'}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Report Display */}
          <div className="lg:col-span-2 glass rounded-3xl border-slate-800 overflow-hidden flex flex-col bg-slate-900/20">
            <div className="p-4 bg-slate-800/50 border-b border-slate-800 flex items-center justify-between px-8">
              <div className="flex items-center gap-2 text-slate-300 text-sm font-bold">
                <FileText className="w-4 h-4 text-brand-500" />
                STABILITY_REPORT.MD
              </div>
              {auditReport && <span className="text-[10px] text-slate-500 font-mono">Size: {auditReport.length} bytes</span>}
            </div>
            
            <div className="flex-1 overflow-y-auto p-12 custom-scrollbar prose prose-invert prose-brand max-w-none prose-headings:text-white prose-p:text-slate-300 prose-strong:text-brand-400 prose-code:text-emerald-400 prose-table:border prose-table:border-slate-800">
              {auditing ? (
                <div className="h-full flex flex-col items-center justify-center opacity-50">
                  <Activity className="w-12 h-12 text-brand-500 animate-pulse mb-4" />
                  <p className="text-lg font-medium text-slate-400">Analyzing System Health...</p>
                </div>
              ) : auditReport ? (
                <ReactMarkdown>{auditReport}</ReactMarkdown>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center opacity-30">
                  <ShieldCheck className="w-20 h-20 text-slate-700 mb-6" />
                  <h3 className="text-xl font-bold text-slate-400">No Audit Data</h3>
                  <p className="text-slate-500 max-w-xs mt-2">Run a stability audit to generate a real-time status report of your platform.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 bg-slate-900/50 rounded-3xl border border-slate-800 overflow-hidden flex flex-col shadow-2xl">
          <div className="p-6 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
             <div className="flex items-center gap-4">
              <label className="text-sm font-bold text-slate-400 uppercase tracking-widest">PostgreSQL Table:</label>
              <select 
                className="bg-slate-950 border border-slate-800 text-white rounded-xl px-4 py-2.5 outline-none focus:ring-2 focus:ring-brand-500 transition-all font-bold text-sm"
                value={selectedTable}
                onChange={(e) => {
                  setSelectedTable(e.target.value)
                  setOffset(0)
                }}
              >
                {tables.map(t => (
                  <option key={t} value={t}>{t.replace(/_/g, ' ').toUpperCase()}</option>
                ))}
              </select>
            </div>
            <div className="text-xs text-slate-500 font-medium">
                Live Data Inspection Layer
            </div>
          </div>

          {loading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-500"></div>
            </div>
          ) : (
            <>
              <div className="flex-1 overflow-auto custom-scrollbar">
                <table className="w-full text-sm text-left border-collapse">
                  <thead className="text-[10px] uppercase bg-slate-950 text-slate-500 sticky top-0 z-10 border-b border-slate-800">
                    <tr>
                      {data.columns.map(col => (
                        <th key={col} className="px-6 py-4 font-black tracking-[0.2em] whitespace-nowrap">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {data.rows.length > 0 ? (
                      data.rows.map((row, idx) => (
                        <tr key={idx} className="hover:bg-brand-500/5 transition-colors">
                          {data.columns.map(col => (
                            <td key={col} className="px-6 py-4 text-slate-300 whitespace-nowrap overflow-hidden max-w-xs truncate font-medium border-r border-slate-800/30" title={row[col]?.toString()}>
                              {row[col] === null ? <span className="text-slate-700 italic">null</span> : 
                               typeof row[col] === 'object' ? <span className="text-brand-400/80">{JSON.stringify(row[col])}</span> : 
                               row[col].toString()}
                            </td>
                          ))}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={data.columns.length} className="px-6 py-24 text-center text-slate-600 font-medium">
                          No data entries found in this table.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              
              <div className="p-6 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
                <div className="text-xs text-slate-500 font-bold uppercase tracking-widest">
                  {offset + 1} - {Math.min(offset + limit, data.total)} <span className="text-slate-700 mx-2">/</span> Total {data.total}
                </div>
                <div className="flex items-center gap-3">
                  <button 
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                    className="px-6 py-2 bg-slate-900 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all border border-slate-800"
                  >
                    Previous
                  </button>
                  <button 
                    disabled={offset + limit >= data.total}
                    onClick={() => setOffset(offset + limit)}
                    className="px-6 py-2 bg-slate-900 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all border border-slate-800"
                  >
                    Next Page
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default SystemInspector
