import { useState, lazy, Suspense } from 'react';

const ObservabilityTopology = lazy(() => import('../components/ObservabilityTopology'));
const TraceList = lazy(() => import('../components/TraceList'));
const GuardrailEffectiveness = lazy(() => import('../components/GuardrailEffectiveness'));
const ToolObservatory = lazy(() => import('../components/ToolObservatory'));
const SecurityCenter = lazy(() => import('../components/SecurityCenter'));
const CostDashboard = lazy(() => import('../components/CostDashboard'));

const TABS = [
  { id: 'topology', label: 'Topology' },
  { id: 'traces', label: 'Traces' },
  { id: 'guardrails', label: 'Guardrails' },
  { id: 'tools', label: 'Tools' },
  { id: 'security', label: 'Security' },
  { id: 'cost', label: 'Cost' },
];

function Spinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="spinner" />
    </div>
  );
}

export default function ObservabilityDashboard() {
  const [activeTab, setActiveTab] = useState('topology');

  return (
    <div className="h-[calc(100vh-6rem)] flex flex-col">
      {/* Tab bar */}
      <div className="border-b border-gray-200 bg-white px-4">
        <nav className="flex space-x-4" aria-label="Observability tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-teal-500 text-teal-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        <Suspense fallback={<Spinner />}>
          {activeTab === 'topology' && <ObservabilityTopology />}
          {activeTab === 'traces' && <TraceList />}
          {activeTab === 'guardrails' && <GuardrailEffectiveness />}
          {activeTab === 'tools' && <ToolObservatory />}
          {activeTab === 'security' && <SecurityCenter />}
          {activeTab === 'cost' && <CostDashboard />}
        </Suspense>
      </div>
    </div>
  );
}
