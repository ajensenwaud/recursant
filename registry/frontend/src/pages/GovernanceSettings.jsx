import { useState, useEffect } from 'react';
import { governance } from '../api/client';

const RISK_TIERS = ['low', 'medium', 'high', 'critical'];

export default function GovernanceSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [autoApproveEnabled, setAutoApproveEnabled] = useState(false);
  const [selectedTiers, setSelectedTiers] = useState([]);

  useEffect(() => {
    loadConfig();
  }, []);

  async function loadConfig() {
    setLoading(true);
    try {
      const data = await governance.getConfig();
      setAutoApproveEnabled(data.auto_approve_enabled);
      setSelectedTiers(data.auto_approve_risk_tiers || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleTier(tier) {
    setSelectedTiers((prev) =>
      prev.includes(tier) ? prev.filter((t) => t !== tier) : [...prev, tier]
    );
  }

  async function handleSave() {
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await governance.updateConfig({
        auto_approve_enabled: autoApproveEnabled,
        auto_approve_risk_tiers: selectedTiers,
      });
      setSuccess('Governance settings saved.');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-500" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Governance Settings</h1>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-md text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-700 rounded-md text-sm">
          {success}
        </div>
      )}

      <div className="bg-white shadow rounded-lg p-6 space-y-6">
        {/* Auto-Approval Toggle */}
        <div>
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-medium text-gray-900">Auto-Approval</h2>
              <p className="text-sm text-gray-500 mt-1">
                When enabled, agents that pass all security and evaluation tests will be
                automatically approved without manual review.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={autoApproveEnabled}
              onClick={() => setAutoApproveEnabled(!autoApproveEnabled)}
              className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 ${
                autoApproveEnabled ? 'bg-teal-500' : 'bg-gray-200'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                  autoApproveEnabled ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Risk Tier Selection */}
        {autoApproveEnabled && (
          <div className="border-t border-gray-200 pt-4">
            <h3 className="text-sm font-medium text-gray-900 mb-1">Eligible Risk Tiers</h3>
            <p className="text-sm text-gray-500 mb-3">
              Select which risk tiers are eligible for auto-approval. If none are selected,
              all tiers are eligible.
            </p>
            <div className="space-y-2">
              {RISK_TIERS.map((tier) => (
                <label key={tier} className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedTiers.includes(tier)}
                    onChange={() => toggleTier(tier)}
                    className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                  />
                  <span className="text-sm text-gray-700 capitalize">{tier}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Save Button */}
        <div className="border-t border-gray-200 pt-4">
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-teal-600 hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
