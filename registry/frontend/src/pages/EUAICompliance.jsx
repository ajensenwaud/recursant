import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { compliance, agents } from '../api/client';

const RISK_COLORS = {
  unacceptable: 'bg-red-900 text-white',
  high: 'bg-red-500 text-white',
  limited: 'bg-amber-500 text-white',
  minimal: 'bg-green-500 text-white',
};

function ComplianceScoreBadge({ score }) {
  let color = 'text-red-600';
  if (score >= 80) color = 'text-green-600';
  else if (score >= 50) color = 'text-amber-600';

  return (
    <span className={`font-bold text-lg ${color}`}>
      {score.toFixed(0)}%
    </span>
  );
}

function RiskCategoryBadge({ category }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${RISK_COLORS[category] || 'bg-gray-200 text-gray-800'}`}>
      {category?.toUpperCase()}
    </span>
  );
}

export default function EUAICompliance() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [allAgents, setAllAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [dash, agentsResp] = await Promise.all([
        compliance.dashboard(),
        agents.list({ per_page: 200 }),
      ]);
      setDashboard(dash);
      setAllAgents(agentsResp.agents || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Agents that don't yet appear in the compliance dashboard
  const classifiedIds = new Set((dashboard?.agents || []).map((a) => a.agent_id));
  const unclassifiedAgents = allAgents.filter((a) => !classifiedIds.has(a.id));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-700">Error loading compliance dashboard: {error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">EU AI Act Compliance</h1>
          <p className="text-sm text-gray-500 mt-1">Risk classification, compliance tracking, and Annex IV documentation</p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-sm text-gray-500">Total Classified Agents</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{dashboard?.total_agents || 0}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-sm text-gray-500">Overall Compliance</p>
          <p className="text-2xl font-bold mt-1">
            {dashboard?.total_agents > 0 ? (
              <ComplianceScoreBadge score={dashboard.overall_compliance_pct} />
            ) : (
              <span className="text-gray-400">N/A</span>
            )}
          </p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-sm text-gray-500">High-Risk Agents</p>
          <p className="text-2xl font-bold text-red-600 mt-1">{dashboard?.by_risk_category?.high || 0}</p>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <p className="text-sm text-gray-500">Limited-Risk Agents</p>
          <p className="text-2xl font-bold text-amber-600 mt-1">{dashboard?.by_risk_category?.limited || 0}</p>
        </div>
      </div>

      {/* Risk Category Breakdown */}
      {dashboard?.by_risk_category && Object.keys(dashboard.by_risk_category).length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Risk Category Distribution</h2>
          <div className="flex gap-3">
            {Object.entries(dashboard.by_risk_category).map(([cat, count]) => (
              <div key={cat} className="flex items-center gap-2">
                <RiskCategoryBadge category={cat} />
                <span className="text-sm text-gray-600">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Agent Table */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-700">Classified Agents</h2>
        </div>
        {dashboard?.agents?.length > 0 ? (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Agent</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Risk Category</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Compliance</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Progress</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Gaps</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Docs</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {dashboard.agents.map((agent) => (
                <tr
                  key={agent.agent_id}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => navigate(`/compliance/${agent.agent_id}`)}
                >
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{agent.agent_name}</td>
                  <td className="px-4 py-3">
                    <RiskCategoryBadge category={agent.eu_risk_category} />
                  </td>
                  <td className="px-4 py-3">
                    <ComplianceScoreBadge score={agent.compliance_score} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-24 bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-teal-500 h-2 rounded-full"
                          style={{ width: `${Math.min(agent.compliance_score, 100)}%` }}
                        ></div>
                      </div>
                      <span className="text-xs text-gray-500">{agent.compliant_count}/{agent.total_applicable}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {agent.gap_count > 0 ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                        {agent.gap_count} gaps
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                        Complete
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {agent.has_annex_iv && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-blue-100 text-blue-700">AIV</span>
                      )}
                      {agent.has_conformity && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-purple-100 text-purple-700">DoC</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button className="text-sm text-teal-600 hover:text-teal-800">View</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-8 text-center text-gray-500">
            <p>No agents have been classified yet.</p>
            <p className="text-sm mt-1">Pick one from the list below to start a classification.</p>
          </div>
        )}
      </div>

      {/* Unclassified agents — entry point to the classification wizard */}
      {unclassifiedAgents.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="text-sm font-semibold text-gray-700">
              Unclassified Agents ({unclassifiedAgents.length})
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Run the EU AI Act risk classification wizard on any agent below.
            </p>
          </div>
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Agent</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Risk Tier</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {unclassifiedAgents.map((agent) => (
                <tr key={agent.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{agent.name}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{agent.status}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{agent.risk_tier || '—'}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => navigate(`/compliance/${agent.id}/classify`)}
                      className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
                    >
                      Classify
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
