import { useState } from 'react';
import { XMarkIcon, PlusIcon, TrashIcon } from '@heroicons/react/24/outline';

const MECHANISMS = [
  { value: 'regex', label: 'Regex', description: 'Pattern matching (<1ms, free)' },
  { value: 'vector_lookup', label: 'Vector Lookup', description: 'Semantic similarity via Weaviate (5-20ms)' },
  { value: 'llm_judge', label: 'LLM Judge', description: 'AI-powered evaluation (1-5s, API cost)' },
  { value: 'ml_classifier', label: 'ML Classifier', description: 'External classifier endpoint (~50ms)' },
];

function defaultConfig(mechanism) {
  switch (mechanism) {
    case 'regex':
      return { patterns: [{ name: '', pattern: '', action: 'block' }] };
    case 'vector_lookup':
      return {
        collection_name: 'GuardrailReference',
        similarity_threshold: 0.7,
        reference_texts: [{ text: '', category: '', action: 'block' }],
      };
    case 'llm_judge':
      return { provider: 'anthropic', model: 'claude-sonnet-4-5-20250929', system_prompt: '', temperature: 0.0, max_tokens: 256, timeout_ms: 5000 };
    case 'ml_classifier':
      return { endpoint_url: '', threshold: 0.5, labels: [] };
    default:
      return {};
  }
}

export default function GuardrailModal({ onClose, onSubmit, submitting }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState('pre_processing');
  const [mechanism, setMechanism] = useState('regex');
  const [enforcementMode, setEnforcementMode] = useState('block');
  const [scope, setScope] = useState('all_agents');
  const [priority, setPriority] = useState(100);
  const [config, setConfig] = useState(defaultConfig('regex'));
  const [error, setError] = useState('');

  function handleMechanismChange(newMech) {
    setMechanism(newMech);
    setConfig(defaultConfig(newMech));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    if (!name.trim()) { setError('Name is required'); return; }

    try {
      await onSubmit({ name, description, type, mechanism, enforcement_mode: enforcementMode, scope, priority, config });
    } catch (err) {
      setError(err.message || 'Failed to create guardrail');
    }
  }

  // Config editors
  function renderRegexConfig() {
    const patterns = config.patterns || [];
    return (
      <div className="space-y-3">
        <label className="block text-sm font-medium text-gray-700">Patterns</label>
        {patterns.map((p, i) => (
          <div key={i} className="flex gap-2 items-start">
            <input
              placeholder="Name"
              value={p.name}
              onChange={(e) => {
                const updated = [...patterns];
                updated[i] = { ...p, name: e.target.value };
                setConfig({ ...config, patterns: updated });
              }}
              className="w-32 px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
            <input
              placeholder="Regex pattern"
              value={p.pattern}
              onChange={(e) => {
                const updated = [...patterns];
                updated[i] = { ...p, pattern: e.target.value };
                setConfig({ ...config, patterns: updated });
              }}
              className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm font-mono"
            />
            <select
              value={p.action}
              onChange={(e) => {
                const updated = [...patterns];
                updated[i] = { ...p, action: e.target.value };
                setConfig({ ...config, patterns: updated });
              }}
              className="w-24 px-2 py-1.5 border border-gray-300 rounded text-sm"
            >
              <option value="block">Block</option>
              <option value="warn">Warn</option>
              <option value="redact">Redact</option>
            </select>
            <button
              type="button"
              onClick={() => setConfig({ ...config, patterns: patterns.filter((_, j) => j !== i) })}
              className="p-1.5 text-gray-400 hover:text-red-600"
            >
              <TrashIcon className="h-4 w-4" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => setConfig({ ...config, patterns: [...patterns, { name: '', pattern: '', action: 'block' }] })}
          className="inline-flex items-center gap-1 text-sm text-teal-600 hover:text-teal-700"
        >
          <PlusIcon className="h-4 w-4" /> Add Pattern
        </button>
      </div>
    );
  }

  function renderVectorConfig() {
    const refs = config.reference_texts || [];
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">Collection Name</label>
            <input
              value={config.collection_name || ''}
              onChange={(e) => setConfig({ ...config, collection_name: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Similarity Threshold</label>
            <input
              type="number"
              step="0.05"
              min="0"
              max="1"
              value={config.similarity_threshold || 0.7}
              onChange={(e) => setConfig({ ...config, similarity_threshold: parseFloat(e.target.value) })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
          </div>
        </div>
        <label className="block text-sm font-medium text-gray-700">Reference Texts</label>
        {refs.map((r, i) => (
          <div key={i} className="flex gap-2 items-start">
            <textarea
              placeholder="Reference text"
              value={r.text}
              onChange={(e) => {
                const updated = [...refs];
                updated[i] = { ...r, text: e.target.value };
                setConfig({ ...config, reference_texts: updated });
              }}
              rows={2}
              className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
            <input
              placeholder="Category"
              value={r.category}
              onChange={(e) => {
                const updated = [...refs];
                updated[i] = { ...r, category: e.target.value };
                setConfig({ ...config, reference_texts: updated });
              }}
              className="w-28 px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
            <select
              value={r.action}
              onChange={(e) => {
                const updated = [...refs];
                updated[i] = { ...r, action: e.target.value };
                setConfig({ ...config, reference_texts: updated });
              }}
              className="w-24 px-2 py-1.5 border border-gray-300 rounded text-sm"
            >
              <option value="block">Block</option>
              <option value="warn">Warn</option>
              <option value="redact">Redact</option>
            </select>
            <button
              type="button"
              onClick={() => setConfig({ ...config, reference_texts: refs.filter((_, j) => j !== i) })}
              className="p-1.5 text-gray-400 hover:text-red-600"
            >
              <TrashIcon className="h-4 w-4" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => setConfig({ ...config, reference_texts: [...refs, { text: '', category: '', action: 'block' }] })}
          className="inline-flex items-center gap-1 text-sm text-teal-600 hover:text-teal-700"
        >
          <PlusIcon className="h-4 w-4" /> Add Reference Text
        </button>
      </div>
    );
  }

  function renderLLMConfig() {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">Provider</label>
            <select
              value={config.provider || 'anthropic'}
              onChange={(e) => setConfig({ ...config, provider: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
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
              value={config.model || ''}
              onChange={(e) => setConfig({ ...config, model: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Temperature</label>
            <input
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={config.temperature ?? 0}
              onChange={(e) => setConfig({ ...config, temperature: parseFloat(e.target.value) })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Max Tokens</label>
            <input
              type="number"
              value={config.max_tokens || 256}
              onChange={(e) => setConfig({ ...config, max_tokens: parseInt(e.target.value) })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">System Prompt</label>
          <textarea
            value={config.system_prompt || ''}
            onChange={(e) => setConfig({ ...config, system_prompt: e.target.value })}
            rows={4}
            placeholder="Instructions for the LLM judge..."
            className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
          />
        </div>
      </div>
    );
  }

  function renderMLConfig() {
    return (
      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-gray-700">Endpoint URL</label>
          <input
            value={config.endpoint_url || ''}
            onChange={(e) => setConfig({ ...config, endpoint_url: e.target.value })}
            placeholder="https://classifier.example.com/predict"
            className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">Threshold</label>
          <input
            type="number"
            step="0.05"
            min="0"
            max="1"
            value={config.threshold || 0.5}
            onChange={(e) => setConfig({ ...config, threshold: parseFloat(e.target.value) })}
            className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded text-sm"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="fixed inset-0 bg-black bg-opacity-25" onClick={onClose} />
        <div className="relative bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
          <div className="flex items-center justify-between px-6 py-4 border-b">
            <h2 className="text-lg font-medium text-gray-900">Create Guardrail</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {error && (
              <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-800">{error}</div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Type</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="pre_processing">Pre-processing</option>
                  <option value="post_processing">Post-processing</option>
                  <option value="structural">Structural</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Enforcement Mode</label>
                <select
                  value={enforcementMode}
                  onChange={(e) => setEnforcementMode(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="block">Block</option>
                  <option value="warn">Warn</option>
                  <option value="redact">Redact</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Scope</label>
                <select
                  value={scope}
                  onChange={(e) => setScope(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="all_agents">All Agents</option>
                  <option value="specific_agents">Specific Agents</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Priority</label>
                <input
                  type="number"
                  min={1}
                  max={10000}
                  value={priority}
                  onChange={(e) => setPriority(parseInt(e.target.value) || 100)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Mechanism</label>
              <div className="grid grid-cols-2 gap-2">
                {MECHANISMS.map((m) => (
                  <button
                    key={m.value}
                    type="button"
                    onClick={() => handleMechanismChange(m.value)}
                    className={`text-left p-3 rounded-md border ${
                      mechanism === m.value
                        ? 'border-teal-500 bg-teal-50 ring-1 ring-teal-500'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="text-sm font-medium">{m.label}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{m.description}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="border-t pt-4">
              <h3 className="text-sm font-medium text-gray-700 mb-3">
                {MECHANISMS.find((m) => m.value === mechanism)?.label} Configuration
              </h3>
              {mechanism === 'regex' && renderRegexConfig()}
              {mechanism === 'vector_lookup' && renderVectorConfig()}
              {mechanism === 'llm_judge' && renderLLMConfig()}
              {mechanism === 'ml_classifier' && renderMLConfig()}
            </div>

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
                disabled={submitting}
                className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50"
              >
                {submitting ? 'Creating...' : 'Create Guardrail'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
