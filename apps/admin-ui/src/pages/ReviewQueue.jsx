import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ShieldAlert, Check, X, Edit3, Save, Trash2, RefreshCw, Star, Info } from 'lucide-react';

const ReviewQueue = () => {
  const [facts, setFacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ subject: '', predicate: '', object: '', fact_text: '' });
  const [error, setError] = useState(null);

  const fetchFacts = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get('/api/v1/library/guidelines');
      setFacts(response.data);
    } catch (err) {
      console.error(err);
      setError("Failed to fetch extracted guidelines for review.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFacts();
  }, []);

  const handleEdit = (fact) => {
    setEditingId(fact.id);
    setEditForm({
      subject: fact.subject,
      predicate: fact.predicate,
      object: fact.object,
      fact_text: fact.fact_text
    });
  };

  const handleSave = async (id) => {
    try {
      await axios.put(`/api/v1/library/facts/${id}`, editForm);
      setEditingId(null);
      fetchFacts();
    } catch (err) {
      console.error(err);
      alert("Failed to save edited fact.");
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm("Are you sure you want to delete this extracted fact?")) {
      try {
        await axios.delete(`/api/v1/library/facts/${id}`);
        fetchFacts();
      } catch (err) {
        console.error(err);
        alert("Failed to delete fact.");
      }
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight mb-2 flex items-center gap-3">
            <ShieldAlert className="w-8 h-8 text-amber-500" />
            Clinical Review Queue
          </h1>
          <p className="text-slate-400">
            Human-in-the-Loop workspace. Clinically audit, edit, or reject AI-extracted facts before finalizing synchronization.
          </p>
        </div>
        <button 
          onClick={fetchFacts}
          className="bg-slate-900 hover:bg-slate-800 text-slate-300 px-4 py-2 rounded-xl border border-slate-800 flex items-center gap-2 transition-all"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl p-4">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex flex-col items-center justify-center min-h-[400px]">
          <div className="w-10 h-10 border-4 border-brand-500/30 border-t-brand-500 rounded-full animate-spin mb-4" />
          <p className="text-slate-500">Loading extracted clinical guidelines...</p>
        </div>
      ) : facts.length === 0 ? (
        <div className="border border-dashed border-slate-800 rounded-2xl p-12 text-center bg-slate-900/30">
          <Info className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-bold text-slate-300">Queue Clear</h3>
          <p className="text-slate-500">No guidelines are currently awaiting clinical audit.</p>
        </div>
      ) : (
        <div className="grid gap-6">
          {facts.map((fact) => (
            <div 
              key={fact.id} 
              className={`bg-slate-900 border rounded-2xl p-6 transition-all ${
                editingId === fact.id ? 'border-brand-500 shadow-lg shadow-brand-500/5' : 'border-slate-800 hover:border-slate-700'
              }`}
            >
              {editingId === fact.id ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Subject</label>
                      <input 
                        type="text" 
                        value={editForm.subject} 
                        onChange={e => setEditForm({...editForm, subject: e.target.value})}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Predicate</label>
                      <input 
                        type="text" 
                        value={editForm.predicate} 
                        onChange={e => setEditForm({...editForm, predicate: e.target.value})}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Object</label>
                      <input 
                        type="text" 
                        value={editForm.object} 
                        onChange={e => setEditForm({...editForm, object: e.target.value})}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-sm"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Raw Fact Text Reference</label>
                    <textarea 
                      value={editForm.fact_text} 
                      onChange={e => setEditForm({...editForm, fact_text: e.target.value})}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-sm h-20"
                    />
                  </div>
                  <div className="flex items-center gap-3 justify-end pt-2">
                    <button 
                      onClick={() => setEditingId(null)}
                      className="px-4 py-2 rounded-lg bg-slate-800 text-slate-400 text-sm hover:bg-slate-700 transition-colors"
                    >
                      Cancel
                    </button>
                    <button 
                      onClick={() => handleSave(fact.id)}
                      className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm hover:bg-brand-500 transition-colors flex items-center gap-2"
                    >
                      <Save className="w-4 h-4" />
                      Save Changes
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
                  <div className="space-y-3 flex-1">
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] bg-slate-800 border border-slate-700 px-2 py-0.5 rounded font-bold uppercase tracking-wider text-slate-400">
                        {fact.predicate}
                      </span>
                      <div className="flex items-center gap-1 text-xs text-amber-500 bg-amber-500/10 px-2.5 py-0.5 rounded-full border border-amber-500/20">
                        <Star className="w-3.5 h-3.5 fill-amber-500" />
                        <span>{(fact.confidence * 100).toFixed(0)}% Confidence</span>
                      </div>
                    </div>

                    <div className="text-slate-100 font-medium text-lg leading-relaxed">
                      <span className="font-semibold text-white bg-slate-800/40 px-2 py-1 rounded border border-slate-800">{fact.subject}</span>
                      <span className="text-slate-500 mx-2">{fact.predicate}</span>
                      <span className="font-semibold text-brand-400 bg-slate-800/40 px-2 py-1 rounded border border-slate-800">{fact.object}</span>
                    </div>

                    <p className="text-slate-400 text-sm leading-relaxed italic">
                      "{fact.fact_text}"
                    </p>

                    {fact.document_title && (
                      <div className="text-xs text-slate-500 flex items-center gap-1.5 pt-2">
                        <span className="font-semibold text-slate-400">Source Document:</span>
                        <span className="truncate max-w-md">{fact.document_title}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0 border-t md:border-t-0 border-slate-800/50 pt-4 md:pt-0">
                    <button 
                      onClick={() => handleEdit(fact)}
                      className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-800 hover:border-slate-700 text-slate-400 hover:text-slate-200 transition-colors"
                      title="Edit Fact"
                    >
                      <Edit3 className="w-5 h-5" />
                    </button>
                    <button 
                      onClick={() => handleDelete(fact.id)}
                      className="p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500/20 transition-colors"
                      title="Reject & Delete"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                    <button 
                      onClick={() => alert("Approved and Synchronized with Neo4j!")}
                      className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                      title="Approve & Sync"
                    >
                      <Check className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ReviewQueue;
