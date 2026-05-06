import { useState, useEffect } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { customAttacks } from '../api/client';

const ATTACK_TYPES = [
  { value: 'encoding', label: 'Encoding' },
  { value: 'jailbreak', label: 'Jailbreak' },
  { value: 'injection', label: 'Injection' },
  { value: 'pii_bypass', label: 'PII Bypass' },
  { value: 'exfiltration', label: 'Exfiltration' },
];

const SEVERITIES = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

export default function CustomAttackModal({ isOpen, onClose, attack, onSaved }) {
  const isEdit = !!attack;

  const [attackType, setAttackType] = useState('jailbreak');
  const [variantName, setVariantName] = useState('');
  const [text, setText] = useState('');
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState('medium');
  const [source, setSource] = useState('');
  const [tagsStr, setTagsStr] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (attack) {
      setAttackType(attack.attack_type || 'jailbreak');
      setVariantName(attack.variant_name || '');
      setText(attack.text || '');
      setDescription(attack.description || '');
      setSeverity(attack.severity || 'medium');
      setSource(attack.source || '');
      setTagsStr((attack.tags || []).join(', '));
    } else {
      setAttackType('jailbreak');
      setVariantName('');
      setText('');
      setDescription('');
      setSeverity('medium');
      setSource('');
      setTagsStr('');
    }
    setError('');
  }, [attack]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!variantName.trim()) {
      setError('Variant name is required.');
      return;
    }
    if (!text.trim()) {
      setError('Attack text is required.');
      return;
    }

    const payload = {
      attack_type: attackType,
      variant_name: variantName.trim(),
      text: text.trim(),
      description: description.trim() || null,
      severity,
      source: source.trim() || null,
      tags: tagsStr.split(',').map((s) => s.trim()).filter(Boolean),
    };

    setSaving(true);
    try {
      if (isEdit) {
        await customAttacks.update(attack.id, payload);
      } else {
        await customAttacks.create(payload);
      }
      onSaved();
    } catch (err) {
      setError(err.message || 'Failed to save attack.');
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
              {isEdit ? 'Edit Custom Attack' : 'Create Custom Attack'}
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

            {/* Attack Type */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Attack Type</label>
              <select
                value={attackType}
                onChange={(e) => setAttackType(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
              >
                {ATTACK_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            {/* Variant Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Variant Name</label>
              <input
                type="text"
                value={variantName}
                onChange={(e) => setVariantName(e.target.value)}
                required
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                placeholder="e.g. custom_roleplay_ceo"
              />
              <p className="mt-1 text-xs text-gray-400">Unique identifier (snake_case recommended).</p>
            </div>

            {/* Attack Text */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Attack Text</label>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                required
                rows={6}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:ring-teal-500 focus:border-teal-500"
                placeholder="The adversarial input text that will be tested against guardrails..."
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                placeholder="Human-readable explanation of what this attack tests..."
              />
            </div>

            {/* Severity + Source row */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Severity</label>
                <select
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                >
                  {SEVERITIES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Source</label>
                <input
                  type="text"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                  placeholder="e.g. OWASP, garak, custom"
                />
              </div>
            </div>

            {/* Tags */}
            <div>
              <label className="block text-sm font-medium text-gray-700">Tags</label>
              <input
                type="text"
                value={tagsStr}
                onChange={(e) => setTagsStr(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                placeholder="Comma-separated tags, e.g. owasp, llm-top-10, advanced"
              />
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
                {saving ? 'Saving...' : isEdit ? 'Update Attack' : 'Create Attack'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
