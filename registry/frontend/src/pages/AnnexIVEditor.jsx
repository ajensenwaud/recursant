import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { compliance } from '../api/client';

const SECTION_LABELS = {
  section_1_general_description: '1. General Description',
  section_2a_development: '2a. Development Methodology',
  section_2b_data_requirements: '2b. Data Requirements',
  section_2c_validation_testing: '2c. Validation and Testing',
  section_3a_accuracy: '3a. Accuracy Metrics',
  section_3b_known_risks: '3b. Known Risks',
  section_3c_human_oversight: '3c. Human Oversight',
  section_3d_input_specs: '3d. Input Specifications',
  section_4_metrics: '4. Metrics Appropriateness',
  section_5_risk_management: '5. Risk Management',
  section_6_lifecycle: '6. Lifecycle Changes',
  section_7_standards: '7. Applied Standards',
  section_8_declaration: '8. Declaration of Conformity',
  section_9_post_market: '9. Post-Market Monitoring',
};

const MANUAL_SECTIONS = {
  section_1_intended_purpose: { label: '1. Intended Purpose Detail', placeholder: 'Describe the intended purpose and use case in detail...' },
  section_2a_methodology: { label: '2a. Development Methodology', placeholder: 'Describe development methods, tools, and processes...' },
  section_2b_data: { label: '2b. Data Requirements', placeholder: 'Describe training data characteristics, governance, and quality measures...' },
  section_3a_interpretation: { label: '3a. Metric Interpretation', placeholder: 'Explain how accuracy metrics should be interpreted...' },
  section_3b_mitigation: { label: '3b. Risk Mitigation', placeholder: 'Describe mitigation strategies for identified risks...' },
  section_3c_procedures: { label: '3c. Oversight Procedures', placeholder: 'Describe human oversight procedures...' },
  section_3d_additional: { label: '3d. Additional Input Specs', placeholder: 'Provide additional input specification details...' },
  section_4_justification: { label: '4. Metrics Justification', placeholder: 'Justify why chosen metrics are appropriate...' },
  section_5_narrative: { label: '5. Risk Management Narrative', placeholder: 'Describe the overall risk management approach...' },
  section_7_standards: { label: '7. Applied Standards', placeholder: 'List applicable standards (ISO 42001, NIST AI RMF, etc.)...' },
  section_8_declaration: { label: '8. Declaration of Conformity', placeholder: 'Reference to the formal declaration...' },
  section_9_narrative: { label: '9. Monitoring Narrative', placeholder: 'Describe the post-market monitoring approach...' },
};

export default function AnnexIVEditor() {
  const { agentId, docId } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState(null);
  const [manualEdits, setManualEdits] = useState({});
  const [activeSection, setActiveSection] = useState('section_1_general_description');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDocument();
  }, [docId]);

  const loadDocument = async () => {
    try {
      setLoading(true);
      const doc = await compliance.annexIV.get(agentId, docId);
      setDocument(doc);
      setManualEdits(doc.manual_sections || {});
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleManualEdit = (key, value) => {
    setManualEdits(prev => ({
      ...prev,
      [key]: { content: value },
    }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await compliance.annexIV.update(agentId, docId, { manual_sections: manualEdits });
      await loadDocument();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerate = async () => {
    try {
      setRegenerating(true);
      await compliance.annexIV.regenerate(agentId, docId);
      await loadDocument();
    } catch (err) {
      setError(err.message);
    } finally {
      setRegenerating(false);
    }
  };

  const handleDownloadPdf = async () => {
    try {
      const response = await fetch(`/v1/agents/${agentId}/annex-iv/${docId}/pdf`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json',
        },
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = window.document.createElement('a');
        a.href = url;
        a.download = `annex_iv_v${document.version}.pdf`;
        a.click();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      setError('PDF download failed');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-600"></div>
      </div>
    );
  }

  const isEditable = document?.status === 'draft' || document?.status === 'under_review';
  const data = document?.document_data || {};

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => navigate(`/compliance/${agentId}`)} className="text-sm text-teal-600 hover:text-teal-800 mb-1">
            &larr; Back
          </button>
          <h1 className="text-xl font-bold text-gray-900">Annex IV Technical Documentation - v{document?.version}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
              document?.status === 'approved' ? 'bg-green-100 text-green-700' :
              document?.status === 'draft' ? 'bg-yellow-100 text-yellow-700' :
              'bg-gray-100 text-gray-500'
            }`}>
              {document?.status}
            </span>
            {document?.signature && (
              <span className="text-xs text-gray-400">Signed: {document.signature.substring(0, 16)}...</span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {isEditable && (
            <>
              <button
                onClick={handleRegenerate}
                disabled={regenerating}
                className="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                {regenerating ? 'Regenerating...' : 'Refresh Auto Sections'}
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-3 py-1.5 bg-teal-600 text-white rounded text-sm hover:bg-teal-700 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Manual Edits'}
              </button>
            </>
          )}
          <button
            onClick={handleDownloadPdf}
            className="px-3 py-1.5 bg-gray-800 text-white rounded text-sm hover:bg-gray-900"
          >
            Export PDF
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Split View */}
      <div className="flex gap-4" style={{ height: 'calc(100vh - 220px)' }}>
        {/* Section Nav */}
        <div className="w-56 flex-shrink-0 bg-white rounded-lg border border-gray-200 overflow-y-auto">
          <div className="p-2 space-y-0.5">
            {Object.entries(SECTION_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setActiveSection(key)}
                className={`w-full text-left px-3 py-2 text-sm rounded ${
                  activeSection === key ? 'bg-teal-50 text-teal-700 font-medium' : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 bg-white rounded-lg border border-gray-200 overflow-y-auto p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">{SECTION_LABELS[activeSection]}</h2>

          {/* Auto-populated data */}
          {data[activeSection] && Object.keys(data[activeSection]).length > 0 && (
            <div className="mb-6">
              <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Auto-Populated Data</h3>
              <div className="bg-gray-50 rounded-lg p-4">
                <pre className="text-xs text-gray-700 whitespace-pre-wrap overflow-auto">
                  {JSON.stringify(data[activeSection], null, 2)}
                </pre>
              </div>
            </div>
          )}

          {/* Manual sections for this area */}
          {Object.entries(MANUAL_SECTIONS)
            .filter(([key]) => key.startsWith(activeSection.replace('section_', 'section_').split('_').slice(0, 2).join('_')) || key.includes(activeSection.split('_')[1]))
            .map(([key, config]) => (
              <div key={key} className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">{config.label}</label>
                {isEditable ? (
                  <textarea
                    value={manualEdits[key]?.content || ''}
                    onChange={(e) => handleManualEdit(key, e.target.value)}
                    rows={6}
                    className="w-full border border-gray-300 rounded-md p-3 text-sm"
                    placeholder={config.placeholder}
                  />
                ) : (
                  <div className="bg-gray-50 rounded-md p-3 text-sm text-gray-700">
                    {manualEdits[key]?.content || <span className="text-gray-400 italic">Not provided</span>}
                  </div>
                )}
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
