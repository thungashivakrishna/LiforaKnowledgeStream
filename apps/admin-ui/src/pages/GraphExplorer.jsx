import React, { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'
import ForceGraph2D from 'react-force-graph-2d'
import { Network, Search, Filter, Maximize2, Info, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

const API_BASE = '/api/v1'

const GraphExplorer = () => {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [typeFilter, setTypeFilter] = useState('ALL')
  const [frameworkFilter, setFrameworkFilter] = useState('ALL')
  const fgRef = useRef()

  useEffect(() => {
    fetchGraphData()
  }, [])

  const fetchGraphData = async () => {
    try {
      setLoading(true)
      const params = {
        q: searchTerm,
        type: typeFilter !== 'ALL' ? typeFilter : undefined,
        framework: frameworkFilter !== 'ALL' ? frameworkFilter : undefined
      }
      const response = await axios.get(`${API_BASE}/graph/explorer/data`, { params })
      setGraphData(response.data || { nodes: [], links: [] })
    } catch (error) {
      console.error('Error fetching graph data:', error)
    } finally {
      setLoading(false)
    }
  }

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchGraphData()
    }, 600)
    return () => clearTimeout(timer)
  }, [searchTerm, typeFilter, frameworkFilter])

  const handleNodeClick = useCallback(node => {
    if (fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 800)
      fgRef.current.zoom(2.5, 800)
    }
    setSelectedNode(node)
  }, [])

  const entityTypes = ['ALL', 'Entity', 'Condition', 'Symptom', 'Intervention', 'Food', 'Nutrient']
  const frameworks = ['ALL', 'Functional Medicine', 'Ayurveda', 'Longevity', 'General Health']

  if (loading && graphData.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand-500"></div>
        <p className="text-slate-500 animate-pulse text-sm">Traversing Knowledge Graph...</p>
      </div>
    )
  }

  const typeColors = {
    'Condition': '#ef4444',     // Red-500
    'Symptom': '#f97316',       // Orange-500
    'Intervention': '#10b981', // Emerald-500
    'Nutrient': '#f59e0b',      // Amber-500
    'Supplement': '#8b5cf6',   // Violet-500
    'Food': '#ec4899',         // Pink-500
    'Entity': '#3b82f6'         // Blue-500 (Default)
  }

  const legendItems = Object.entries(typeColors)

  return (
    <div className="h-[calc(100vh-120px)] relative overflow-hidden bg-slate-950 rounded-3xl border border-slate-800 shadow-2xl">
      {/* Header / Controls */}
      <div className="absolute top-6 left-6 z-10 flex flex-col gap-3 w-80">
        <div className="glass p-3 rounded-2xl flex items-center gap-3 pr-4 shadow-xl border border-white/5">
          <div className="p-2 bg-brand-500 rounded-xl shadow-lg shadow-brand-500/20">
            <Network className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white uppercase tracking-tight">Clinical Knowledge</h2>
            <p className="text-[10px] text-slate-400 font-medium">{graphData.nodes.length} nodes • {graphData.links.length} relationships</p>
          </div>
        </div>

        <div className="flex flex-col gap-2 p-1">
          <div className="glass px-4 py-2.5 rounded-xl flex items-center gap-2 border border-white/5 shadow-lg">
            <Search className="w-4 h-4 text-slate-400" />
            <input 
              type="text" 
              placeholder="Search clinical entities..." 
              className="bg-transparent border-none text-xs text-white placeholder:text-slate-500 focus:outline-none w-full"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          
          <div className="flex gap-2">
            <select 
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="flex-1 glass bg-slate-900/60 text-[10px] text-slate-300 border border-white/5 rounded-lg px-2 py-2 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            >
              {entityTypes.map(t => <option key={t} value={t} className="bg-slate-950">{t === 'ALL' ? 'All Types' : t}</option>)}
            </select>
            
            <select 
              value={frameworkFilter}
              onChange={(e) => setFrameworkFilter(e.target.value)}
              className="flex-1 glass bg-slate-900/60 text-[10px] text-slate-300 border border-white/5 rounded-lg px-2 py-2 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
            >
              {frameworks.map(f => <option key={f} value={f} className="bg-slate-950">{f === 'ALL' ? 'All Frameworks' : f}</option>)}
            </select>

            <button 
              onClick={fetchGraphData}
              className="glass p-2 rounded-lg border border-white/5 hover:bg-brand-500/20 text-slate-400 hover:text-brand-400 transition-all"
              title="Manual Refresh"
            >
              <Filter className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Node Info Panel */}
      <AnimatePresence>
        {selectedNode && (
          <motion.div 
            initial={{ x: 400, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 400, opacity: 0 }}
            className="absolute top-6 right-6 bottom-6 w-80 glass z-20 rounded-3xl border border-white/10 shadow-2xl overflow-hidden flex flex-col"
          >
            <div className="p-6 border-b border-white/5 flex justify-between items-start">
              <div>
                <span className="text-[10px] font-bold text-brand-400 uppercase tracking-widest px-2 py-0.5 rounded bg-brand-500/10 mb-2 inline-block">
                  {selectedNode.type}
                </span>
                <h3 className="text-xl font-bold text-white leading-tight">{selectedNode.label}</h3>
              </div>
              <button 
                onClick={() => setSelectedNode(null)}
                className="p-1 hover:bg-white/5 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>
            
            <div className="p-6 flex-1 overflow-y-auto custom-scrollbar">
              <div className="space-y-6">
                <div>
                  <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Clinical Attributes</h4>
                  <div className="grid gap-3">
                    {Object.entries(selectedNode.properties || {}).map(([key, val]) => (
                      <div key={key} className="bg-white/5 p-3 rounded-xl border border-white/5">
                        <p className="text-[10px] text-slate-500 uppercase mb-1">{key}</p>
                        <p className="text-sm text-slate-200 font-medium">{String(val)}</p>
                      </div>
                    ))}
                    {(!selectedNode.properties || Object.keys(selectedNode.properties).length === 0) && (
                      <p className="text-xs text-slate-600 italic">No additional metadata available.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Legend */}
      <div className="absolute bottom-6 left-6 z-10 glass p-4 rounded-2xl border border-white/5 shadow-xl max-w-[220px]">
        <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Clinical Legend</h4>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          {legendItems.map(([type, color]) => (
            <div key={type} className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full shadow-sm" style={{ backgroundColor: color }}></div>
              <span className="text-[9px] text-slate-400 font-bold uppercase tracking-wider">{type}</span>
            </div>
          ))}
        </div>
      </div>

      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeLabel="label"
        nodeAutoColorBy="type"
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={1}
        linkCurvature={0.25}
        d3AlphaDecay={0.01}
        d3VelocityDecay={0.4}
        cooldownTicks={150}
        warmupTicks={50}
        onEngineStop={() => {
          if (fgRef.current && graphData.nodes.length > 0) {
            fgRef.current.zoomToFit(400, 100)
          }
        }}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = node.label
          const fontSize = 14/globalScale
          ctx.font = `${fontSize}px Inter, sans-serif`
          const textWidth = ctx.measureText(label).width
          const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.4) 

          // Shadow
          ctx.shadowColor = 'rgba(0,0,0,0.5)'
          ctx.shadowBlur = 4/globalScale
          
          ctx.fillStyle = 'rgba(15, 23, 42, 0.95)'
          ctx.beginPath()
          ctx.roundRect(node.x - bckgDimensions[0] / 2, node.y - bckgDimensions[1] / 2, bckgDimensions[0], bckgDimensions[1], 4/globalScale)
          ctx.fill()
          
          ctx.shadowBlur = 0 

          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillStyle = typeColors[node.type] || '#3b82f6'
          ctx.fillText(label, node.x, node.y)

          node.__bckgDimensions = bckgDimensions
        }}
        nodePointerAreaPaint={(node, color, ctx) => {
          ctx.fillStyle = color
          const bckgDimensions = node.__bckgDimensions
          bckgDimensions && ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y - bckgDimensions[1] / 2, ...bckgDimensions)
        }}
        onNodeClick={handleNodeClick}
        backgroundColor="transparent"
        linkColor={() => 'rgba(255, 255, 255, 0.08)'}
      />
    </div>
  )
}

export default GraphExplorer
