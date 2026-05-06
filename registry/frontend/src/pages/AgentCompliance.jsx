import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { compliance, agents } from '../api/client';

const STATUS_COLORS = {
  compliant: 'bg-green-100 text-green-700',
  non_compliant: 'bg-red-100 text-red-700',
  not_started: 'bg-gray-100 text-gray-600',
  in_progress: 'bg-blue-100 text-blue-700',
  not_applicable: 'bg-gray-50 text-gray-400',
  waived: 'bg-yellow-100 text-yellow-700',
};

const RISK_COLORS = {
  unacceptable: 'bg-red-900 text-white',
  high: 'bg-red-500 text-white',
  limited: 'bg-amber-500 text-white',
  minimal: 'bg-green-500 text-white',
};

export default function AgentCompliance() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const [agent, setAgent] = useState(null);
  const [classification, setClassification] = useState(null);
  const [gapAnalysis, setGapAnalysis] = useState(null);
  const [statuses, setStatuses] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [conformityAssessments, setConformityAssessments] = useState([]);
  const [monitoringPlan, setMonitoringPlan] = useState(null);
  const [activeTab, setActiveTab] = useState('requirements');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [assessLoading, setAssessLoading] = useState(false);
  const [generateLoading, setGenerateLoading] = useState(false);

  useEffect(() => {
    loadData();
  }, [agentId]);

  const loadData = async () => {
    try {
      setLoading(true);
      const agentData = await agents.get(agentId);
      setAgent(agentData);

      try {
        const classData = await compliance.classification.get(agentId);
        setClassification(classData);

        const [statusData, gapData, docData, confData] = await Promise.all([
          compliance.statuses.list(agentId),
          compliance.gapAnalysis(agentId),
          compliance.annexIV.list(agentId),
          compliance.conformity.list(agentId),
        ]);

        setStatuses(statusData.statuses || []);
        setGapAnalysis(gapData);
        setDocuments(docData.documents || []);
        setConformityAssessments(confData.assessments || []);

        try {
          const planData = await compliance.monitoring.get(agentId);
          setMonitoringPlan(planData);
        } catch { /* no plan yet */ }
      } catch {
        // No classification yet
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAutoAssess = async () => {
    try {
      setAssessLoading(true);
      await compliance.autoAssess(agentId);
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setAssessLoading(false);
    }
  };

  const handleGenerateAnnexIV = async () => {
    try {
      setGenerateLoading(true);
      await compliance.annexIV.generate(agentId);
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerateLoading(false);
    }
  };

  const handleApproveDocument = async (docId) => {
    try {
      await compliance.annexIV.approve(agentId, docId);
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCreateConformity = async () => {
    try {
      await compliance.conformity.create(agentId, {});
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

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
        <p className="text-red-700">{error}</p>
      </div>
    );
  }

  const tabs = [
    { id: 'requirements', label: 'Requirements', count: statuses.length },
    { id: 'gaps', label: 'Gap Analysis', count: gapAnalysis?.gaps?.length || 0 },
    { id: 'annex-iv', label: 'Annex IV', count: documents.length },
    { id: 'conformity', label: 'Conformity', count: conformityAssessments.length },
    { id: 'monitoring', label: 'Monitoring' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => navigate('/compliance')} className="text-sm text-teal-600 hover:text-teal-800 mb-1">
            &larr; Back to Dashboard
          </button>
          <h1 className="text-2xl font-bold text-gray-900">{agent?.name || 'Agent'} - EU AI Act Compliance</h1>
        </div>
        {!classification && (
          <button
            onClick={() => navigate(`/compliance/${agentId}/classify`)}
            className="px-4 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700 text-sm"
          >
            Classify Agent
          </button>
        )}
      </div>

      {/* Classification Card */}
      {classification && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div>
                <p className="text-xs text-gray-500 uppercase">Risk Category</p>
                <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${RISK_COLORS[classification.eu_risk_category]}`}>
                  {classification.eu_risk_category?.toUpperCase()}
                </span>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase">Use Domain</p>
                <p className="text-sm font-medium">{classification.use_domain?.replace(/_/g, ' ')}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase">Compliance Score</p>
                <p className="text-xl font-bold" style={{ color: gapAnalysis?.compliance_score >= 80 ? '#16a34a' : gapAnalysis?.compliance_score >= 50 ? '#d97706' : '#dc2626' }}>
                  {gapAnalysis?.compliance_score?.toFixed(0) || 0}%
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase">Confirmed</p>
                <p className="text-sm">{classification.is_confirmed ? 'Yes' : 'No'}</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleAutoAssess}
                disabled={assessLoading}
                className="px-3 py-1.5 bg-teal-600 text-white rounded text-sm hover:bg-teal-700 disabled:opacity-50"
              >
                {assessLoading ? 'Assessing...' : 'Auto-Assess'}
              </button>
              <button
                onClick={() => navigate(`/compliance/${agentId}/classify`)}
                className="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50"
              >
                Reclassify
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      {classification && (
        <>
          <div className="border-b border-gray-200">
            <nav className="flex gap-4">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`pb-3 px-1 text-sm font-medium border-b-2 ${
                    activeTab === tab.id
                      ? 'border-teal-500 text-teal-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {tab.label}
                  {tab.count !== undefined && (
                    <span className="ml-1.5 px-1.5 py-0.5 rounded-full text-xs bg-gray-100">{tab.count}</span>
                  )}
                </button>
              ))}
            </nav>
          </div>

          {/* Requirements Tab */}
          {activeTab === 'requirements' && (
            <div className="bg-white rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Requirement</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Article</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Assessed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {statuses.map((s) => (
                    <tr key={s.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <p className="text-sm font-medium text-gray-900">{s.requirement?.title || s.requirement_id}</p>
                        <p className="text-xs text-gray-500">{s.requirement_id}</p>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{s.requirement?.article_reference}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[s.status] || 'bg-gray-100'}`}>
                          {s.status?.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500">{s.requirement?.evidence_type}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">
                        {s.last_assessed_at ? new Date(s.last_assessed_at).toLocaleDateString() : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Gap Analysis Tab */}
          {activeTab === 'gaps' && gapAnalysis && (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                  <p className="text-xs text-green-600">Compliant</p>
                  <p className="text-xl font-bold text-green-700">{gapAnalysis.compliant_count}</p>
                </div>
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="text-xs text-red-600">Non-Compliant</p>
                  <p className="text-xl font-bold text-red-700">{gapAnalysis.non_compliant_count}</p>
                </div>
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                  <p className="text-xs text-gray-600">Not Started</p>
                  <p className="text-xl font-bold text-gray-700">{gapAnalysis.not_started_count}</p>
                </div>
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                  <p className="text-xs text-blue-600">In Progress</p>
                  <p className="text-xl font-bold text-blue-700">{gapAnalysis.in_progress_count}</p>
                </div>
              </div>

              {gapAnalysis.gaps.length > 0 && (
                <div className="bg-white rounded-lg border border-gray-200">
                  <div className="px-4 py-3 border-b border-gray-200">
                    <h3 className="text-sm font-semibold text-gray-700">Gaps to Address</h3>
                  </div>
                  <div className="divide-y divide-gray-200">
                    {gapAnalysis.gaps.map((gap) => (
                      <div key={gap.requirement_id} className="px-4 py-3">
                        <div className="flex items-start justify-between">
                          <div>
                            <p className="text-sm font-medium text-gray-900">{gap.title}</p>
                            <p className="text-xs text-gray-500 mt-0.5">{gap.article_reference} | {gap.requirement_id}</p>
                            {gap.guidance && (
                              <p className="text-xs text-gray-600 mt-1 bg-gray-50 rounded p-2">{gap.guidance}</p>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[gap.status]}`}>
                              {gap.status?.replace(/_/g, ' ')}
                            </span>
                            <span className="text-xs text-gray-400">{gap.evidence_type}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Annex IV Tab */}
          {activeTab === 'annex-iv' && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <button
                  onClick={handleGenerateAnnexIV}
                  disabled={generateLoading}
                  className="px-4 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700 text-sm disabled:opacity-50"
                >
                  {generateLoading ? 'Generating...' : 'Generate New Version'}
                </button>
              </div>

              {documents.length > 0 ? (
                <div className="bg-white rounded-lg border border-gray-200">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Version</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Approved By</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Signed</th>
                        <th className="px-4 py-3"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {documents.map((doc) => (
                        <tr key={doc.id} className="hover:bg-gray-50">
                          <td className="px-4 py-3 text-sm font-medium">v{doc.version}</td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                              doc.status === 'approved' ? 'bg-green-100 text-green-700' :
                              doc.status === 'draft' ? 'bg-yellow-100 text-yellow-700' :
                              doc.status === 'superseded' ? 'bg-gray-100 text-gray-500' :
                              'bg-blue-100 text-blue-700'
                            }`}>
                              {doc.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-500">
                            {new Date(doc.created_at).toLocaleDateString()}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-500">{doc.approved_by || '-'}</td>
                          <td className="px-4 py-3 text-sm text-gray-500">{doc.signature ? 'Yes' : 'No'}</td>
                          <td className="px-4 py-3 text-right">
                            <div className="flex gap-2 justify-end">
                              <button
                                onClick={() => navigate(`/compliance/${agentId}/annex-iv/${doc.id}`)}
                                className="text-sm text-teal-600 hover:text-teal-800"
                              >
                                View
                              </button>
                              {doc.status === 'draft' && (
                                <button
                                  onClick={() => handleApproveDocument(doc.id)}
                                  className="text-sm text-green-600 hover:text-green-800"
                                >
                                  Approve
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
                  No Annex IV documents generated yet.
                </div>
              )}
            </div>
          )}

          {/* Conformity Tab */}
          {activeTab === 'conformity' && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <button
                  onClick={handleCreateConformity}
                  className="px-4 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700 text-sm"
                >
                  Start Assessment
                </button>
              </div>

              {conformityAssessments.length > 0 ? (
                <div className="bg-white rounded-lg border border-gray-200">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Findings</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Declaration Date</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Declared By</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {conformityAssessments.map((a) => (
                        <tr key={a.id}>
                          <td className="px-4 py-3 text-sm">{a.assessment_type}</td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                              a.status === 'passed' ? 'bg-green-100 text-green-700' :
                              a.status === 'failed' ? 'bg-red-100 text-red-700' :
                              'bg-blue-100 text-blue-700'
                            }`}>
                              {a.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm">{a.findings?.length || 0}</td>
                          <td className="px-4 py-3 text-sm text-gray-500">
                            {a.declaration_date ? new Date(a.declaration_date).toLocaleDateString() : '-'}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-500">{a.declared_by || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
                  No conformity assessments started yet.
                </div>
              )}
            </div>
          )}

          {/* Monitoring Tab */}
          {activeTab === 'monitoring' && (
            <div className="space-y-4">
              {monitoringPlan ? (
                <div className="bg-white rounded-lg border border-gray-200 p-4">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Active Monitoring Plan</h3>
                  <p className="text-sm text-gray-600">Status: <span className="font-medium">{monitoringPlan.status}</span></p>
                  {monitoringPlan.last_report_at && (
                    <p className="text-sm text-gray-500 mt-1">Last Report: {new Date(monitoringPlan.last_report_at).toLocaleDateString()}</p>
                  )}
                  <pre className="mt-2 bg-gray-50 rounded p-3 text-xs overflow-auto">
                    {JSON.stringify(monitoringPlan.monitoring_config, null, 2)}
                  </pre>
                </div>
              ) : (
                <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-500">
                  No monitoring plan configured yet.
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
