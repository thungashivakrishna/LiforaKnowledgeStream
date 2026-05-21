import React, { useState, useEffect } from 'react'
import axios from 'axios'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, Cell
} from 'recharts'
import { DollarSign, Zap, AlertTriangle, CheckCircle, Clock, TrendingDown } from 'lucide-react'
import { motion } from 'framer-motion'
import { clsx } from 'clsx'

const API = 'http://localhost:8000/api/v1'

const STAGE_COLORS = {
  enrichment: '#3b82f6',
  discovery: '#10b981',
  acquisition: '#f59e0b',
  extraction: '#8b5cf6',
  chunking: '#ec4899',
  graph: '#14b8a6',
}

const StatCard = ({ title, value, icon: Icon, subtitle, color = 'brand' }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="bg-slate-900 border border-slate-800 rounded-2xl p-6 relative overflow-hidden group"
  >
    <div className="flex items-center gap-4 mb-4">
      <div className={clsx("p-3 rounded-xl", color === 'red' ? 'bg-red-500/10' : 'bg-brand-500/10')}>
        <Icon className={clsx("w-6 h-6", color === 'red' ? 'text-red-400' : 'text-brand-400')} />
      </div>
      <h3 className="text-slate-400 font-medium">{title}</h3>
    </div>
    <div className="text-3xl font-bold text-white">{value}</div>
    {subtitle && <p className="text-sm text-slate-500 mt-2">{subtitle}</p>}
  </motion.div>
)

const LLMGateway = () => {
  const [spendDaily, setSpendDaily] = useState([])
  const [spendByStage, setSpendByStage] = useState([])
  const [fallbackRate, setFallbackRate] = useState([])
  const [promptLeaderboard, setPromptLeaderboard] = useState([])
  const [cacheHitByPrompt, setCacheHitByPrompt] = useState([])
  const [recentCalls, setRecentCalls] = useState([])
  const [unitEcon, setUnitEcon] = useState(null)
  const [budgetConfig, setBudgetConfig] = useState(null)
  const [leaderboardMetric, setLeaderboardMetric] = useState('spend')
  const [callFilter, setCallFilter] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [daily, byStage, fallback, leaderboard, cacheHit, recent, econ, budget] =
          await Promise.allSettled([
            axios.get(`${API}/llm/spend/daily?days=30`),
            axios.get(`${API}/llm/spend/by-stage`),
            axios.get(`${API}/llm/fallback-rate`),
            axios.get(`${API}/llm/prompt-leaderboard?metric=${leaderboardMetric}`),
            axios.get(`${API}/llm/cache-hit-by-prompt`),
            axios.get(`${API}/llm/recent-calls?limit=50${callFilter ? `&status=${callFilter}` : ''}`),
            axios.get(`${API}/llm/unit-economics`),
            axios.get(`${API}/llm/budget-config`),
          ])

        if (daily.status === 'fulfilled') {
          // Aggregate daily spend by day
          const byDay = {}
          for (const row of daily.value.data) {
            if (!byDay[row.day]) byDay[row.day] = { day: row.day, total: 0 }
            byDay[row.day][row.stage] = (byDay[row.day][row.stage] || 0) + row.cost_usd
            byDay[row.day].total += row.cost_usd
          }
          setSpendDaily(Object.values(byDay).sort((a, b) => a.day.localeCompare(b.day)).slice(-14))
        }
        if (byStage.status === 'fulfilled') setSpendByStage(byStage.value.data)
        if (fallback.status === 'fulfilled') setFallbackRate(fallback.value.data)
        if (leaderboard.status === 'fulfilled') setPromptLeaderboard(leaderboard.value.data)
        if (cacheHit.status === 'fulfilled') setCacheHitByPrompt(cacheHit.value.data)
        if (recent.status === 'fulfilled') setRecentCalls(recent.value.data)
        if (econ.status === 'fulfilled') setUnitEcon(econ.value.data)
        if (budget.status === 'fulfilled') setBudgetConfig(budget.value.data)
      } finally {
        setLoading(false)
      }
    }
    fetchAll()
  }, [leaderboardMetric, callFilter])

  const totalSpend = spendByStage.reduce((s, r) => s + (r.cost_usd || 0), 0)
  const overallFallbackRate = fallbackRate.length
    ? (fallbackRate.reduce((s, r) => s + r.fallback_rate_pct, 0) / fallbackRate.length).toFixed(1)
    : '—'
  const overallCacheRate = cacheHitByPrompt.length
    ? (cacheHitByPrompt.reduce((s, r) => s + r.hit_rate_pct, 0) / cacheHitByPrompt.length).toFixed(1)
    : '—'

  const dailyBudgetPct = budgetConfig
    ? Math.min((spendDaily.at(-1)?.total || 0) / budgetConfig.daily_budget_usd * 100, 100).toFixed(0)
    : null

  const stages = [...new Set(spendDaily.flatMap(d => Object.keys(d).filter(k => k !== 'day' && k !== 'total')))]

  const STATUS_COLOR = { success: 'text-emerald-400', cached: 'text-blue-400', failed: 'text-red-400', refusal: 'text-yellow-400', blocked: 'text-orange-400' }

  if (loading) return <div className="text-slate-400 text-center py-20">Loading LLM Gateway data…</div>

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">LLM Gateway</h2>
        <p className="text-slate-400 text-sm">Cost tracking, fallback observability, and prompt analytics</p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Spend"
          value={`$${totalSpend.toFixed(4)}`}
          icon={DollarSign}
          subtitle="all time, successful calls"
        />
        <StatCard
          title="Fallback Rate"
          value={`${overallFallbackRate}%`}
          icon={AlertTriangle}
          subtitle="avg across all stages"
          color={parseFloat(overallFallbackRate) > 20 ? 'red' : 'brand'}
        />
        <StatCard
          title="Cache Hit Rate"
          value={`${overallCacheRate}%`}
          icon={Zap}
          subtitle="avg across all prompts"
        />
        {dailyBudgetPct !== null && (
          <StatCard
            title="Today's Budget"
            value={`${dailyBudgetPct}%`}
            icon={TrendingDown}
            subtitle={`of $${budgetConfig.daily_budget_usd} daily limit`}
            color={parseInt(dailyBudgetPct) >= 80 ? 'red' : 'brand'}
          />
        )}
      </div>

      {/* Spend chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <h3 className="font-semibold text-white mb-4">Spend (last 14 days)</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={spendDaily}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="day" tick={{ fill: '#94a3b8', fontSize: 11 }} />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v.toFixed(3)}`} />
            <Tooltip formatter={v => `$${parseFloat(v).toFixed(6)}`} contentStyle={{ background: '#0f172a', border: '1px solid #1e293b' }} />
            <Legend />
            {stages.map(s => (
              <Bar key={s} dataKey={s} stackId="a" fill={STAGE_COLORS[s] || '#64748b'} name={s} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Unit economics */}
        {unitEcon && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="font-semibold text-white mb-4">Unit Economics</h3>
            <div className="space-y-3">
              {[
                { label: 'Per document', value: unitEcon.cost_per_document_usd, count: unitEcon.documents_processed },
                { label: 'Per fact', value: unitEcon.cost_per_fact_usd, count: unitEcon.facts_extracted },
                { label: 'Per chunk', value: unitEcon.cost_per_chunk_usd, count: unitEcon.chunks_indexed },
              ].map(row => (
                <div key={row.label} className="flex items-center justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">{row.label}</span>
                  <div className="text-right">
                    <span className="text-white font-mono">${row.value.toFixed(6)}</span>
                    <span className="text-slate-500 text-xs ml-2">({row.count.toLocaleString()} total)</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Fallback heatmap (table) */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <h3 className="font-semibold text-white mb-4">Fallback Rate by Stage</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-left">
                  <th className="pb-2">Stage</th>
                  <th className="pb-2">Model Group</th>
                  <th className="pb-2 text-right">Rate</th>
                  <th className="pb-2 text-right">Calls</th>
                </tr>
              </thead>
              <tbody>
                {fallbackRate.map((r, i) => (
                  <tr key={i} className="border-t border-slate-800">
                    <td className="py-2 text-slate-300">{r.stage}</td>
                    <td className="py-2 text-slate-400 font-mono text-xs">{r.model_group}</td>
                    <td className={clsx("py-2 text-right font-mono", r.fallback_rate_pct > 20 ? 'text-red-400' : 'text-emerald-400')}>
                      {r.fallback_rate_pct}%
                    </td>
                    <td className="py-2 text-right text-slate-400">{r.total_calls}</td>
                  </tr>
                ))}
                {fallbackRate.length === 0 && (
                  <tr><td colSpan={4} className="py-4 text-slate-500 text-center">No data yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Prompt leaderboard */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-white">Prompt Leaderboard</h3>
          <div className="flex gap-2">
            {['spend', 'count', 'p95'].map(m => (
              <button
                key={m}
                onClick={() => setLeaderboardMetric(m)}
                className={clsx(
                  "px-3 py-1 rounded-lg text-xs font-medium transition-colors",
                  leaderboardMetric === m ? 'bg-brand-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'
                )}
              >
                {m === 'p95' ? 'p95 latency' : m}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-left">
                <th className="pb-2">Prompt ID</th>
                <th className="pb-2 text-right">Calls</th>
                <th className="pb-2 text-right">Total Cost</th>
                <th className="pb-2 text-right">p95 Latency</th>
              </tr>
            </thead>
            <tbody>
              {promptLeaderboard.map((r, i) => (
                <tr key={i} className="border-t border-slate-800">
                  <td className="py-2 text-slate-300 font-mono text-xs">{r.prompt_id}</td>
                  <td className="py-2 text-right text-slate-400">{r.calls}</td>
                  <td className="py-2 text-right font-mono text-white">${r.total_cost_usd.toFixed(4)}</td>
                  <td className="py-2 text-right text-slate-400">{r.p95_latency_ms}ms</td>
                </tr>
              ))}
              {promptLeaderboard.length === 0 && (
                <tr><td colSpan={4} className="py-4 text-slate-500 text-center">No data yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cache hit by prompt */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <h3 className="font-semibold text-white mb-4">Cache Hit Rate by Prompt</h3>
        <div className="space-y-2">
          {cacheHitByPrompt.map((r, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="text-xs text-slate-400 font-mono w-64 truncate">{r.prompt_id}</span>
              <div className="flex-1 bg-slate-800 rounded-full h-2">
                <div
                  className={clsx("h-2 rounded-full", r.hit_rate_pct > 50 ? 'bg-emerald-500' : r.hit_rate_pct > 20 ? 'bg-yellow-500' : 'bg-red-500')}
                  style={{ width: `${r.hit_rate_pct}%` }}
                />
              </div>
              <span className="text-xs text-white w-12 text-right">{r.hit_rate_pct}%</span>
            </div>
          ))}
          {cacheHitByPrompt.length === 0 && <p className="text-slate-500 text-sm text-center">No data yet</p>}
        </div>
      </div>

      {/* Recent calls */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-white">Recent Calls</h3>
          <div className="flex gap-2">
            {['', 'failed', 'refusal', 'budget_exceeded', 'blocked'].map(s => (
              <button
                key={s}
                onClick={() => setCallFilter(s)}
                className={clsx(
                  "px-3 py-1 rounded-lg text-xs font-medium transition-colors",
                  callFilter === s ? 'bg-brand-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'
                )}
              >
                {s || 'all'}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 text-left">
                <th className="pb-2">Time</th>
                <th className="pb-2">Stage</th>
                <th className="pb-2">Prompt</th>
                <th className="pb-2">Model</th>
                <th className="pb-2 text-right">Cost</th>
                <th className="pb-2 text-right">Latency</th>
                <th className="pb-2 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {recentCalls.map(r => (
                <tr key={r.id} className="border-t border-slate-800">
                  <td className="py-1.5 text-slate-500">{new Date(r.created_at).toLocaleTimeString()}</td>
                  <td className="py-1.5 text-slate-300">{r.stage}</td>
                  <td className="py-1.5 text-slate-400 font-mono max-w-[180px] truncate">{r.prompt_id}</td>
                  <td className="py-1.5 text-slate-400 font-mono max-w-[140px] truncate">{r.model_used}</td>
                  <td className="py-1.5 text-right text-white font-mono">${(r.cost_usd || 0).toFixed(5)}</td>
                  <td className="py-1.5 text-right text-slate-400">{r.latency_ms}ms</td>
                  <td className={clsx("py-1.5 text-right font-medium", STATUS_COLOR[r.status] || 'text-slate-400')}>{r.status}</td>
                </tr>
              ))}
              {recentCalls.length === 0 && (
                <tr><td colSpan={7} className="py-4 text-slate-500 text-center">No calls recorded yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default LLMGateway
