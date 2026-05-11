import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API_BASE = 'http://localhost:8000/api/v1'

const SystemInspector = () => {
  const [tables, setTables] = useState([])
  const [selectedTable, setSelectedTable] = useState('')
  const [data, setData] = useState({ columns: [], rows: [], total: 0 })
  const [loading, setLoading] = useState(false)
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    fetchTables()
  }, [])

  useEffect(() => {
    if (selectedTable) {
      fetchTableData()
    }
  }, [selectedTable, offset, limit])

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

  return (
    <div className="flex flex-col h-full space-y-6">
      <div className="flex items-center justify-between bg-slate-900/50 p-6 rounded-2xl border border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">System Inspector</h1>
          <p className="text-slate-400 text-sm">Directly explore internal PostgreSQL tables and state.</p>
        </div>
        
        <div className="flex items-center gap-4">
          <label className="text-sm font-medium text-slate-300">Select Table:</label>
          <select 
            className="bg-slate-800 border border-slate-700 text-white rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-blue-500 transition-all"
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
      </div>

      <div className="flex-1 bg-slate-900/50 rounded-2xl border border-slate-800 overflow-hidden flex flex-col">
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-auto custom-scrollbar">
              <table className="w-full text-sm text-left">
                <thead className="text-xs uppercase bg-slate-800/80 text-slate-400 sticky top-0 z-10">
                  <tr>
                    {data.columns.map(col => (
                      <th key={col} className="px-6 py-4 font-semibold tracking-wider whitespace-nowrap">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {data.rows.length > 0 ? (
                    data.rows.map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                        {data.columns.map(col => (
                          <td key={col} className="px-6 py-4 text-slate-300 whitespace-nowrap overflow-hidden max-w-xs truncate" title={row[col]?.toString()}>
                            {row[col] === null ? <span className="text-slate-600 italic">null</span> : 
                             typeof row[col] === 'object' ? JSON.stringify(row[col]) : 
                             row[col].toString()}
                          </td>
                        ))}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={data.columns.length} className="px-6 py-12 text-center text-slate-500">
                        No data found in this table.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            
            <div className="p-4 bg-slate-800/50 border-t border-slate-800 flex items-center justify-between">
              <div className="text-xs text-slate-500">
                Showing {offset + 1} to {Math.min(offset + limit, data.total)} of {data.total} rows
              </div>
              <div className="flex items-center gap-2">
                <button 
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed rounded text-xs text-white transition-all"
                >
                  Previous
                </button>
                <button 
                  disabled={offset + limit >= data.total}
                  onClick={() => setOffset(offset + limit)}
                  className="px-3 py-1 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed rounded text-xs text-white transition-all"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default SystemInspector
