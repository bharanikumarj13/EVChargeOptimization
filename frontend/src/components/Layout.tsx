import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  PlayCircle,
  Zap,
  BarChart3,
  Repeat,
  History,
  Activity,
  ExternalLink,
  ShieldCheck,
} from 'lucide-react';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/optimize', label: 'Run Optimization', icon: PlayCircle },
  { to: '/stations', label: 'Stations & Grid', icon: Zap },
  { to: '/results', label: 'Allocation Results', icon: BarChart3 },
  { to: '/feedback', label: 'Feedback Loop', icon: Repeat },
  { to: '/history', label: 'History & Reports', icon: History },
  { to: '/health', label: 'Integration Health', icon: Activity },
];

export const Layout: React.FC = () => {
  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col justify-between">
        <div>
          {/* Brand header */}
          <div className="p-5 border-b border-slate-800">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-lg shadow-sm">
                ⚡
              </div>
              <div>
                <h1 className="font-bold text-base tracking-tight text-slate-100 leading-tight">EVCharge-Opt</h1>
                <p className="text-[11px] text-slate-400 font-medium">Allocation & Optimization</p>
              </div>
            </div>
            <div className="mt-3 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-800/80 border border-slate-700/60 text-[11px] text-slate-300">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Mock Predictor Adapter</span>
            </div>
          </div>

          {/* Nav links */}
          <nav className="p-3 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                    }`
                  }
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>

        {/* Bottom system links */}
        <div className="p-4 border-t border-slate-800 text-xs text-slate-400 space-y-2">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-slate-400">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              Isolated Workspace
            </span>
            <span className="text-[10px] text-slate-400">v0.1.0</span>
          </div>
          <a
            href="http://127.0.0.1:8002/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between text-slate-400 hover:text-emerald-400 transition-colors pt-1"
          >
            <span>FastAPI Swagger Docs</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <header className="h-14 border-b border-slate-800 bg-slate-900/60 backdrop-blur px-8 flex items-center justify-between flex-shrink-0 sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Intelligent EV Charging Infrastructure Engine
            </span>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-400">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              Backend: 127.0.0.1:8002
            </span>
            <span className="text-slate-600">|</span>
            <span>Frontend: 127.0.0.1:5174</span>
          </div>
        </header>

        <div className="p-8 max-w-7xl w-full mx-auto space-y-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
