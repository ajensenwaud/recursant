import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import { customAttacks } from '../api/client';
import CustomAttackModal from '../components/CustomAttackModal';
import ConfirmDialog from '../components/ConfirmDialog';

const ATTACK_TYPE_COLORS = {
  encoding: 'bg-purple-100 text-purple-800',
  jailbreak: 'bg-red-100 text-red-800',
  injection: 'bg-orange-100 text-orange-800',
  pii_bypass: 'bg-yellow-100 text-yellow-800',
  exfiltration: 'bg-pink-100 text-pink-800',
};

const SEVERITY_COLORS = {
  low: 'bg-gray-100 text-gray-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

const ATTACK_TYPES = ['encoding', 'jailbreak', 'injection', 'pii_bypass', 'exfiltration'];

export default function CustomAttackLibrary() {
  const [showModal, setShowModal] = useState(false);
  const [editingAttack, setEditingAttack] = useState(null);
  const [deleteAttack, setDeleteAttack] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [filterType, setFilterType] = useState('');
  const [showImportModal, setShowImportModal] = useState(false);
  const [importJson, setImportJson] = useState('');
  const [importError, setImportError] = useState('');
  const [importResult, setImportResult] = useState(null);
  const queryClient = useQueryClient();

  const params = {};
  if (filterType) params.attack_type = filterType;

  const { data, isLoading, error } = useQuery({
    queryKey: ['custom-attacks', filterType],
    queryFn: () => customAttacks.list(params),
  });

  const deleteMutation = useMutation({
    mutationFn: (id) => customAttacks.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['custom-attacks'] });
      setDeleteAttack(null);
    },
  });

  const importMutation = useMutation({
    mutationFn: (data) => customAttacks.import(data),
    onSuccess: (result) => {
      setImportResult(result);
      queryClient.invalidateQueries({ queryKey: ['custom-attacks'] });
    },
    onError: (err) => {
      setImportError(err.message || 'Import failed');
    },
  });

  const attacks = data?.attacks || [];
  const total = data?.total || 0;

  function handleExport() {
    customAttacks.export(filterType ? { attack_type: filterType } : {}).then((data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `custom-attacks${filterType ? `-${filterType}` : ''}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  function handleImportSubmit() {
    setImportError('');
    setImportResult(null);
    try {
      const parsed = JSON.parse(importJson);
      const payload = Array.isArray(parsed) ? { attacks: parsed } : parsed;
      if (!payload.attacks) {
        setImportError('JSON must be an array of attacks or {attacks: [...]}');
        return;
      }
      importMutation.mutate(payload);
    } catch {
      setImportError('Invalid JSON');
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Custom Attack Library</h1>
          <p className="mt-1 text-sm text-gray-500">
            {total} custom attack{total !== 1 ? 's' : ''} defined
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowImportModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <ArrowUpTrayIcon className="h-4 w-4" />
            Import
          </button>
          <button
            onClick={handleExport}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <ArrowDownTrayIcon className="h-4 w-4" />
            Export
          </button>
          <button
            onClick={() => { setEditingAttack(null); setShowModal(true); }}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
          >
            <PlusIcon className="h-4 w-4" />
            Add Attack
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700">Filter:</label>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="block w-48 px-3 py-2 text-sm border border-gray-300 rounded-md focus:ring-teal-500 focus:border-teal-500"
        >
          <option value="">All types</option>
          {ATTACK_TYPES.map((t) => (
            <option key={t} value={t}>{t.replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 border-4 border-teal-200 border-t-teal-600 rounded-full animate-spin" />
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-800">
          Failed to load attacks: {error.message}
        </div>
      ) : attacks.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg font-medium">No custom attacks defined</p>
          <p className="mt-1 text-sm">Add attacks manually or import from JSON.</p>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="w-8" />
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Variant Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Attack Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Severity
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Source
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {attacks.map((attack) => (
                <AttackRow
                  key={attack.id}
                  attack={attack}
                  isExpanded={expandedId === attack.id}
                  onToggle={() => setExpandedId(expandedId === attack.id ? null : attack.id)}
                  onEdit={() => { setEditingAttack(attack); setShowModal(true); }}
                  onDelete={() => setDeleteAttack(attack)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modals */}
      <CustomAttackModal
        isOpen={showModal}
        onClose={() => { setShowModal(false); setEditingAttack(null); }}
        attack={editingAttack}
        onSaved={() => {
          setShowModal(false);
          setEditingAttack(null);
          queryClient.invalidateQueries({ queryKey: ['custom-attacks'] });
        }}
      />

      <ConfirmDialog
        isOpen={!!deleteAttack}
        title="Delete Custom Attack"
        message={`Are you sure you want to delete "${deleteAttack?.variant_name}"?`}
        onConfirm={() => deleteMutation.mutate(deleteAttack.id)}
        onCancel={() => setDeleteAttack(null)}
      />

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen p-4">
            <div className="fixed inset-0 bg-black bg-opacity-25" onClick={() => setShowImportModal(false)} />
            <div className="relative bg-white rounded-lg shadow-xl max-w-2xl w-full">
              <div className="px-6 py-4 border-b">
                <h2 className="text-lg font-medium text-gray-900">Import Custom Attacks</h2>
              </div>
              <div className="p-6 space-y-4">
                <p className="text-sm text-gray-500">
                  Paste a JSON array of attack objects. Each object needs: attack_type, variant_name, text.
                  Optional: description, severity, source, tags.
                </p>
                <textarea
                  value={importJson}
                  onChange={(e) => setImportJson(e.target.value)}
                  rows={12}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:ring-teal-500 focus:border-teal-500"
                  placeholder='[{"attack_type": "jailbreak", "variant_name": "my_attack", "text": "..."}]'
                />
                {importError && (
                  <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-800">
                    {importError}
                  </div>
                )}
                {importResult && (
                  <div className="bg-green-50 border border-green-200 rounded p-3 text-sm text-green-800">
                    Imported: {importResult.imported}, Skipped: {importResult.skipped}
                    {importResult.errors?.length > 0 && (
                      <span>, Errors: {importResult.errors.length}</span>
                    )}
                  </div>
                )}
                <div className="flex justify-end gap-3 pt-2">
                  <button
                    onClick={() => { setShowImportModal(false); setImportJson(''); setImportError(''); setImportResult(null); }}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                  >
                    Close
                  </button>
                  <button
                    onClick={handleImportSubmit}
                    disabled={importMutation.isPending || !importJson.trim()}
                    className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700 disabled:opacity-50"
                  >
                    {importMutation.isPending ? 'Importing...' : 'Import'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AttackRow({ attack, isExpanded, onToggle, onEdit, onDelete }) {
  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="pl-3">
          <button onClick={onToggle} className="text-gray-400 hover:text-gray-600">
            {isExpanded ? (
              <ChevronDownIcon className="h-4 w-4" />
            ) : (
              <ChevronRightIcon className="h-4 w-4" />
            )}
          </button>
        </td>
        <td className="px-4 py-3 text-sm font-medium text-gray-900">
          {attack.variant_name}
        </td>
        <td className="px-4 py-3 text-sm">
          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${ATTACK_TYPE_COLORS[attack.attack_type] || 'bg-gray-100 text-gray-800'}`}>
            {attack.attack_type?.replace('_', ' ')}
          </span>
        </td>
        <td className="px-4 py-3 text-sm">
          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_COLORS[attack.severity] || 'bg-gray-100 text-gray-800'}`}>
            {attack.severity}
          </span>
        </td>
        <td className="px-4 py-3 text-sm text-gray-500">
          {attack.source || '-'}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500">
          {attack.created_at ? format(new Date(attack.created_at), 'MMM d, yyyy') : '-'}
        </td>
        <td className="px-4 py-3 text-right">
          <div className="flex items-center justify-end gap-2">
            <button onClick={onEdit} className="text-gray-400 hover:text-teal-600" title="Edit">
              <PencilIcon className="h-4 w-4" />
            </button>
            <button onClick={onDelete} className="text-gray-400 hover:text-red-600" title="Delete">
              <TrashIcon className="h-4 w-4" />
            </button>
          </div>
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={7} className="px-6 py-4 bg-gray-50">
            <div className="space-y-2">
              <div>
                <span className="text-xs font-medium text-gray-500 uppercase">Attack Text:</span>
                <pre className="mt-1 text-sm text-gray-800 bg-white rounded border border-gray-200 p-3 whitespace-pre-wrap max-h-48 overflow-y-auto">
                  {attack.text || '-'}
                </pre>
              </div>
              {attack.description && (
                <div>
                  <span className="text-xs font-medium text-gray-500 uppercase">Description:</span>
                  <p className="mt-1 text-sm text-gray-700">{attack.description}</p>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
