import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { adversarial, guardrails } from '../api/client';

const ATTACK_TYPES = [
  { value: 'encoding', label: 'Encoding' },
  { value: 'jailbreak', label: 'Jailbreak' },
  { value: 'injection', label: 'Injection' },
  { value: 'pii_bypass', label: 'PII Bypass' },
  { value: 'exfiltration', label: 'Exfiltration' },
];

export default function AdversarialSuiteModal({ isOpen, onClose, suite, onSaved }) {
  const isEdit = !!suite;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [attackTypes, setAttackTypes] = useState([]);
  const [targetGuardrailIds, setTargetGuardrailIds] = useState([]);
  const [targetAgents, setTargetAgents] = useState('');
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleIntervalMinutes, setScheduleIntervalMinutes] = useState(60);
  const [evasionThreshold, setEvasionThreshold] = useState(10);
  const [alertOnBreach, setAlertOnBreach] = useState(true);
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [llmProvider, setLlmProvider] = useState('anthropic');
  const [llmModel, setLlmModel] = useState('claude-sonnet-4-5-20250929');
  const [llmTemperature, setLlmTemperature] = useState(0.7);
  const [llmStrategies, setLlmStrategies] = useState(['category_targeted']);
  const [llmVariantsPerStrategy, setLlmVariantsPerStrategy] = useState(5);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Load guardrails for the multi-select
  const { data: guardrailsData } = useQuery({
    queryKey: ['guardrails-list-for-adversarial'],
    queryFn: () => guardrails.list(),
  });

  const availableGuardrails = guardrailsData?.guardrails || [];

  // Populate form when editing
  useEffect(() => {
    if (suite) {
      setName(suite.name || '');
      setDescription(suite.description || '');
      setAttackTypes(suite.attack_types || []);
      setTargetGuardrailIds(suite.target_guardrail_ids || []);
      setTargetAgents((suite.target_agents || []).join(', '));
      setScheduleEnabled(suite.schedule_enabled || false);
      setScheduleIntervalMinutes(suite.schedule_interval_minutes || 60);
      setEvasionThreshold(
        suite.evasion_threshold != null ? Math.round(suite.evasion_threshold * 100) : 10
      );
      setAlertOnBreach(suite.alert_on_breach ?? true);
      const gc = suite.generation_config;
      if (gc) {
        setLlmEnabled(true);
        setLlmProvider(gc.provider || 'anthropic');
        setLlmModel(gc.model || 'claude-sonnet-4-5-20250929');
        setLlmTemperature(gc.temperature ?? 0.7);
        setLlmStrategies(gc.strategies || ['category_targeted']);
        setLlmVariantsPerStrategy(gc.num_variants_per_strategy ?? 5);
      } else {
        setLlmEnabled(false);
      }
    } else {
      setName('');
      setDescription('');
      setAttackTypes([]);
      setTargetGuardrailIds([]);
      setTargetAgents('');
      setScheduleEnabled(false);
      setScheduleIntervalMinutes(60);
      setEvasionThreshold(10);
      setAlertOnBreach(true);
      setLlmEnabled(false);
      setLlmProvider('anthropic');
      setLlmModel('claude-sonnet-4-5-20250929');
      setLlmTemperature(0.7);
      setLlmStrategies(['category_targeted']);
      setLlmVariantsPerStrategy(5);
    }
    setError('');
  }, [suite]);

  function toggleAttackType(type) {
    setAttackTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  }

  function toggleGuardrail(id) {
    setTargetGuardrailIds((prev) =>
      prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id]
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Name is required.');
      return;
    }
    if (attackTypes.length === 0) {
      setError('Select at least one attack type.');
      return;
    }

    const generationConfig = llmEnabled ? {
      provider: llmProvider,
      model: llmModel,
      temperature: parseFloat(llmTemperature),
      strategies: llmStrategies,
      num_variants_per_strategy: parseInt(llmVariantsPerStrategy, 10),
    } : null;

    const payload = {
      name: name.trim(),
      description: description.trim(),
      attack_types: attackTypes,
      target_guardrail_ids: targetGuardrailIds,
      target_agents: targetAgents
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      schedule_enabled: scheduleEnabled,
      schedule_interval_minutes: scheduleEnabled ? parseInt(scheduleIntervalMinutes, 10) : null,
      evasion_threshold: evasionThreshold / 100,
      alert_on_breach: alertOnBreach,
      generation_config: generationConfig,
    };

    setSaving(true);
    try {
      if (isEdit) {
        await adversarial.suites.update(suite.id, payload);
      } else {
        await adversarial.suites.create(payload);
      }
      onSaved();
    } catch (err) {
      setError(err.message || 'Failed to save suite.');
    } finally {
      setSaving(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="fixed inset-0 bg-black bg-opacity-25" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b">
            <h2 className="text-lg font-medium text-gray-900">
              {isEdit ? 'Edit Adversarial Suite' : 'Create Adversarial Suite'}
            </h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="p-6 space-y-5">
            {error && (
              <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-800">
                {error}
              </div>
            )}

            {/* Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                placeholder="e.g. Jailbreak Regression Suite"
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                placeholder="Describe the purpose of this adversarial test suite..."
              />
            </div>

            {/* Attack Types */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Attack Types</label>
              <div className="flex flex-wrap gap-3">
                {ATTACK_TYPES.map((at) => (
                  <label key={at.value} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={attackTypes.includes(at.value)}
                      onChange={() => toggleAttackType(at.value)}
                      className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                    />
                    {at.label}
                  </label>
                ))}
              </div>
            </div>

            {/* Target Guardrails */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Target Guardrails</label>
              {availableGuardrails.length === 0 ? (
                <p className="text-sm text-gray-400">No guardrails available.</p>
              ) : (
                <div className="max-h-40 overflow-y-auto border border-gray-200 rounded-md p-2 space-y-1">
                  {availableGuardrails.map((g) => (
                    <label key={g.id} className="flex items-center gap-2 text-sm py-1 px-1 rounded hover:bg-gray-50">
                      <input
                        type="checkbox"
                        checked={targetGuardrailIds.includes(g.id)}
                        onChange={() => toggleGuardrail(g.id)}
                        className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                      />
                      <span className="text-gray-900">{g.name}</span>
                      <span className="text-xs text-gray-400 ml-auto">{g.status}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            {/* Target Agents */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Target Agents</label>
              <input
                type="text"
                value={targetAgents}
                onChange={(e) => setTargetAgents(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                placeholder="Comma-separated agent IDs or names"
              />
              <p className="mt-1 text-xs text-gray-400">Leave empty to test all active agents.</p>
            </div>

            {/* Schedule */}
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                  <input
                    type="checkbox"
                    checked={scheduleEnabled}
                    onChange={(e) => setScheduleEnabled(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                  />
                  Enable Scheduled Runs
                </label>
              </div>
              {scheduleEnabled && (
                <div>
                  <label className="block text-sm font-medium text-gray-700">Interval (minutes)</label>
                  <input
                    type="number"
                    min={1}
                    value={scheduleIntervalMinutes}
                    onChange={(e) => setScheduleIntervalMinutes(e.target.value)}
                    className="mt-1 block w-40 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
              )}
            </div>

            {/* Evasion Rate Threshold */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Evasion Rate Threshold: <span className="text-teal-600 font-bold">{evasionThreshold}%</span>
              </label>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400">0%</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={evasionThreshold}
                  onChange={(e) => setEvasionThreshold(parseInt(e.target.value, 10))}
                  className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-teal-600"
                />
                <span className="text-xs text-gray-400">100%</span>
              </div>
              <p className="mt-1 text-xs text-gray-400">
                An alert will be triggered if evasion rate exceeds this threshold.
              </p>
            </div>

            {/* Alert on Breach */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                <input
                  type="checkbox"
                  checked={alertOnBreach}
                  onChange={(e) => setAlertOnBreach(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                />
                Alert on Threshold Breach
              </label>
            </div>

            {/* LLM Attack Generation */}
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                  <input
                    type="checkbox"
                    checked={llmEnabled}
                    onChange={(e) => setLlmEnabled(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                  />
                  Enable LLM-Generated Attacks
                </label>
              </div>
              {llmEnabled && (
                <div className="ml-6 space-y-3 p-4 bg-gray-50 rounded-md border border-gray-200">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Provider</label>
                      <select
                        value={llmProvider}
                        onChange={(e) => setLlmProvider(e.target.value)}
                        className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                      >
                        <option value="anthropic">Anthropic</option>
                        <option value="openai">OpenAI</option>
                        <option value="google">Google</option>
                        <option value="openrouter">OpenRouter</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Model</label>
                      <input
                        type="text"
                        value={llmModel}
                        onChange={(e) => setLlmModel(e.target.value)}
                        className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                        placeholder="e.g. claude-sonnet-4-5-20250929"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700">
                        Temperature: <span className="text-teal-600 font-bold">{llmTemperature}</span>
                      </label>
                      <input
                        type="range"
                        min={0}
                        max={2}
                        step={0.1}
                        value={llmTemperature}
                        onChange={(e) => setLlmTemperature(parseFloat(e.target.value))}
                        className="mt-1 w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-teal-600"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700">Variants per Strategy</label>
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={llmVariantsPerStrategy}
                        onChange={(e) => setLlmVariantsPerStrategy(e.target.value)}
                        className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Strategies</label>
                    <div className="flex flex-wrap gap-3">
                      {[
                        { value: 'mutation', label: 'Mutation', desc: 'Rephrase existing attacks' },
                        { value: 'category_targeted', label: 'Category Targeted', desc: 'Target specific categories' },
                        { value: 'creative', label: 'Creative', desc: 'Novel techniques' },
                      ].map((s) => (
                        <label key={s.value} className="flex items-center gap-2 text-sm" title={s.desc}>
                          <input
                            type="checkbox"
                            checked={llmStrategies.includes(s.value)}
                            onChange={() => {
                              setLlmStrategies((prev) =>
                                prev.includes(s.value)
                                  ? prev.filter((v) => v !== s.value)
                                  : [...prev, s.value]
                              );
                            }}
                            className="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500"
                          />
                          {s.label}
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-4 border-t">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50"
              >
                {saving ? 'Saving...' : isEdit ? 'Update Suite' : 'Create Suite'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
