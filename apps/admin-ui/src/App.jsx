import React from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { 
  Database, 
  Search, 
  FileText, 
  Activity, 
  ShieldAlert, 
  BarChart3, 
  LayoutDashboard,
  Menu,
  X,
  UserCircle,
  Target,
  Network,
  Award
} from 'lucide-react'
import SourceRegistry from './pages/SourceRegistry'
import KnowledgeLibrary from './pages/KnowledgeLibrary'
import SystemInspector from './pages/SystemInspector'
import Dashboard from './pages/Dashboard'
import Discovery from './pages/Discovery'
import UserMapping from './pages/UserMapping'
import ReviewQueue from './pages/ReviewQueue'
import KnowledgeIntelligence from './pages/KnowledgeIntelligence'
import LLMGateway from './pages/LLMGateway'
import PersonalizedProtocols from './pages/PersonalizedProtocols'
import GraphExplorer from './pages/GraphExplorer'
import ClinicalQualityAuditHub from './pages/ClinicalQualityAuditHub'
import { clsx } from 'clsx'

const NavItem = ({ to, icon: Icon, label, active }) => (
  <Link 
    to={to} 
    className={clsx(
      "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 group",
      active 
        ? "bg-brand-600/10 text-brand-400 border border-brand-500/20" 
        : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/50"
    )}
  >
    <Icon className={clsx("w-5 h-5", active ? "text-brand-400" : "group-hover:text-slate-100")} />
    <span className="font-medium">{label}</span>
  </Link>
)

const PlaceholderPage = ({ title }) => (
  <div className="flex flex-col items-center justify-center h-full text-center">
    <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mb-4">
      <Activity className="w-8 h-8 text-brand-500/50" />
    </div>
    <h2 className="text-2xl font-bold text-white mb-2">{title}</h2>
    <p className="text-slate-400 max-w-md">
      This module is currently under construction and will be available in Phase 2 of the Knowledge Stream implementation.
    </p>
  </div>
);

const App = () => {
  const location = useLocation()
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(true)

  const navItems = [
    { to: "/", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/sources", icon: Database, label: "Source Registry" },
    { to: "/discovery", icon: Search, label: "Discovery" },
    { to: "/protocols", icon: Target, label: "Protocols" },
    { to: "/mapping", icon: UserCircle, label: "User Mapping" },
    { to: "/documents", icon: FileText, label: "Documents" },
    { to: "/clinical-quality", icon: Award, label: "Clinical Quality Hub" },
    { to: "/review", icon: ShieldAlert, label: "Review Queue" },
    { to: "/graph", icon: Network, label: "Graph Explorer" },
    { to: "/intelligence", icon: Activity, label: "Intelligence" },
    { to: "/llm-gateway", icon: BarChart3, label: "LLM Gateway" },
    { to: "/inspector", icon: BarChart3, label: "System Inspector" },
  ]

  return (
    <div className="min-h-screen bg-slate-950 flex overflow-hidden">
      {/* Sidebar */}
      <aside 
        className={clsx(
          "fixed inset-y-0 left-0 z-50 w-72 bg-slate-900 border-r border-slate-800 transform transition-transform duration-300 lg:relative lg:translate-x-0",
          !isSidebarOpen && "-translate-x-full"
        )}
      >
        <div className="h-full flex flex-col p-6">
          <div className="flex items-center gap-3 mb-10 px-2">
            <div className="w-10 h-10 bg-brand-600 rounded-xl flex items-center justify-center shadow-lg shadow-brand-600/20">
              <Activity className="text-white w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">Lifora</h1>
              <p className="text-xs text-slate-500 font-medium tracking-widest uppercase">KnowledgeStream</p>
            </div>
          </div>

          <nav className="flex-1 space-y-2">
            {navItems.map((item) => (
              <NavItem 
                key={item.to}
                {...item}
                active={location.pathname === item.to || (item.to !== "/" && location.pathname.startsWith(item.to))}
              />
            ))}
          </nav>

          <div className="mt-auto pt-6 border-t border-slate-800">
            <div className="flex items-center gap-3 px-2">
              <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-400">
                AD
              </div>
              <div>
                <p className="text-sm font-medium">Admin User</p>
                <p className="text-xs text-slate-500">Administrator</p>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        {/* Background Gradients */}
        <div className="absolute top-0 right-0 w-1/2 h-1/2 bg-brand-600/5 blur-[120px] rounded-full pointer-events-none"></div>
        <div className="absolute bottom-0 left-0 w-1/3 h-1/3 bg-blue-600/5 blur-[100px] rounded-full pointer-events-none"></div>

        <header className="h-16 border-b border-slate-800 flex items-center justify-between px-8 bg-slate-950/50 backdrop-blur-sm sticky top-0 z-40">
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="lg:hidden p-2 text-slate-400 hover:text-slate-100"
          >
            {isSidebarOpen ? <X /> : <Menu />}
          </button>
          
          <div className="flex items-center gap-4 ml-auto">
            <div className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-full flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
              <span className="text-[10px] font-bold text-emerald-500 uppercase tracking-wider">System Live</span>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar relative z-10">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/sources/*" element={<SourceRegistry />} />
            <Route path="/discovery" element={<Discovery />} />
            <Route path="/mapping" element={<UserMapping />} />
            <Route path="/protocols" element={<PersonalizedProtocols />} />
            <Route path="/documents" element={<KnowledgeLibrary />} />
            <Route path="/clinical-quality" element={<ClinicalQualityAuditHub />} />
            <Route path="/review" element={<ReviewQueue />} />
            <Route path="/graph" element={<GraphExplorer />} />
            <Route path="/intelligence" element={<KnowledgeIntelligence />} />
            <Route path="/llm-gateway" element={<LLMGateway />} />
            <Route path="/inspector" element={<SystemInspector />} />
            <Route path="*" element={<PlaceholderPage title="Page Not Found" />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

export default App
