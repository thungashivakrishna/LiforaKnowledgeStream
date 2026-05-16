import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line
} from 'recharts';
import { Activity, Database, Clock, BarChart3 } from 'lucide-react';
import { motion } from 'framer-motion';
import { clsx } from 'clsx';

const Dashboard = () => {
  const [enrichmentRuns, setEnrichmentRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const response = await axios.get('http://localhost:8000/api/v1/enrichment/runs?limit=100');
        setEnrichmentRuns(response.data.items || []);
      } catch (error) {
        console.error("Failed to fetch enrichment runs:", error);
      } finally {
        setLoading(false);
      }
    };
    
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000);
    return () => clearInterval(interval);
  }, []);

  // Calculate metrics
  const completedRuns = enrichmentRuns.filter(r => r.status === 'COMPLETED');
  const failedRuns = enrichmentRuns.filter(r => r.status === 'FAILED');
  
  // Model token usage comparison
  const modelStats = completedRuns.reduce((acc, run) => {
    let model = run.model_used || 'unknown';
    // Normalize model names for aggregation
    let key = model;
    if (model.toLowerCase().includes('deepseek')) key = 'deepseek/deepseek-chat';
    if (model.toLowerCase().includes('gpt-4o')) key = 'gpt-4o-mini';
    
    if (!acc[key]) {
      acc[key] = { name: key, count: 0, totalTokens: 0, avgTokens: 0 };
    }
    acc[key].count += 1;
    acc[key].totalTokens += (run.total_tokens || 0);
    acc[key].avgTokens = Math.round(acc[key].totalTokens / acc[key].count);
    return acc;
  }, {});
  
  const modelData = Object.values(modelStats);
  
  const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'];

  const StatCard = ({ title, value, icon: Icon, subtitle, trend }) => (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-slate-900 border border-slate-800 rounded-2xl p-6 relative overflow-hidden group"
    >
      <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
        <Icon className="w-24 h-24" />
      </div>
      <div className="flex items-center gap-4 mb-4">
        <div className="p-3 bg-brand-500/10 rounded-xl">
          <Icon className="w-6 h-6 text-brand-400" />
        </div>
        <h3 className="text-slate-400 font-medium">{title}</h3>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-bold text-white tracking-tight">{value}</span>
        {trend && <span className="text-sm font-medium text-emerald-400">{trend}</span>}
      </div>
      {subtitle && <p className="text-sm text-slate-500 mt-2">{subtitle}</p>}
    </motion.div>
  );

  if (loading && enrichmentRuns.length === 0) {
    return <div className="flex items-center justify-center h-full text-brand-400">Loading metrics...</div>;
  }

  return (
    <div className="space-y-8 pb-12">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Token Visualization Dashboard</h1>
        <p className="text-slate-400">Real-time multi-LLM observability and cost metrics.</p>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard 
          title="Total Processed" 
          value={completedRuns.length} 
          icon={Database}
          subtitle="Documents successfully enriched" 
        />
        <StatCard 
          title="DeepSeek Tokens" 
          value={(modelStats['deepseek/deepseek-chat']?.totalTokens || 0).toLocaleString()} 
          icon={Activity}
          subtitle={`Across ${modelStats['deepseek/deepseek-chat']?.count || 0} documents`} 
        />
        <StatCard 
          title="OpenAI Tokens" 
          value={(modelStats['gpt-4o-mini']?.totalTokens || 0).toLocaleString()} 
          icon={Activity}
          subtitle={`Across ${modelStats['gpt-4o-mini']?.count || 0} documents`} 
        />
        <StatCard 
          title="Pipeline Failures" 
          value={failedRuns.length} 
          icon={Activity}
          subtitle="Errors during processing" 
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Token Usage by Model */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl shadow-black/20">
          <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-brand-400" />
            Total Tokens by Model
          </h3>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="name" stroke="#64748b" tick={{fill: '#94a3b8'}} />
                <YAxis stroke="#64748b" tick={{fill: '#94a3b8'}} />
                <RechartsTooltip 
                  cursor={{fill: '#1e293b', opacity: 0.4}}
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px' }}
                  itemStyle={{ color: '#e2e8f0' }}
                />
                <Bar dataKey="totalTokens" fill="#3b82f6" radius={[4, 4, 0, 0]}>
                  {modelData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Avg Tokens Per Document */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl shadow-black/20">
          <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
            <Activity className="w-5 h-5 text-emerald-400" />
            Average Tokens per Document
          </h3>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" stroke="#64748b" tick={{fill: '#94a3b8'}} />
                <YAxis dataKey="name" type="category" stroke="#64748b" tick={{fill: '#94a3b8'}} width={150} />
                <RechartsTooltip 
                  cursor={{fill: '#1e293b', opacity: 0.4}}
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px' }}
                />
                <Bar dataKey="avgTokens" fill="#10b981" radius={[0, 4, 4, 0]}>
                  {modelData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[(index + 1) % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Recent Runs Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl shadow-black/20">
        <div className="p-6 border-b border-slate-800">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Clock className="w-5 h-5 text-brand-400" />
            Recent Enrichment Runs
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-800/50">
                <th className="p-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Status</th>
                <th className="p-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Model</th>
                <th className="p-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Prompt</th>
                <th className="p-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Completion</th>
                <th className="p-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Tokens</th>
                <th className="p-4 text-xs font-semibold text-slate-400 uppercase tracking-wider">Started</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {enrichmentRuns.slice(0, 10).map((run) => (
                <tr key={run.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="p-4">
                    <span className={clsx(
                      "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
                      run.status === 'COMPLETED' ? "bg-emerald-500/10 text-emerald-400" : 
                      run.status === 'FAILED' ? "bg-red-500/10 text-red-400" : 
                      "bg-brand-500/10 text-brand-400"
                    )}>
                      {run.status === 'COMPLETED' ? <Activity className="w-3.5 h-3.5" /> : 
                       run.status === 'FAILED' ? <Activity className="w-3.5 h-3.5" /> : 
                       <Clock className="w-3.5 h-3.5" />}
                      {run.status}
                    </span>
                  </td>
                  <td className="p-4 text-sm font-medium text-slate-300">{run.model_used || '-'}</td>
                  <td className="p-4 text-sm text-slate-400">{run.prompt_tokens || 0}</td>
                  <td className="p-4 text-sm text-slate-400">{run.completion_tokens || 0}</td>
                  <td className="p-4 text-sm font-bold text-white">{run.total_tokens || 0}</td>
                  <td className="p-4 text-sm text-slate-400">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
