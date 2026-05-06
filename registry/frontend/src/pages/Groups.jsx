import { useState, useEffect } from 'react';
import { groups } from '../api/client';

const GROUP_TYPES = ['administrator', 'approver', 'user'];

const emptyForm = {
  name: '',
  description: '',
  group_type: 'user',
};

export default function Groups() {
  const [groupList, setGroupList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');
  const [expandedGroup, setExpandedGroup] = useState(null);
  const [groupDetail, setGroupDetail] = useState(null);

  useEffect(() => {
    loadGroups();
  }, []);

  async function loadGroups() {
    setLoading(true);
    try {
      const data = await groups.list();
      setGroupList(data.groups);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function toggleExpand(groupId) {
    if (expandedGroup === groupId) {
      setExpandedGroup(null);
      setGroupDetail(null);
      return;
    }
    try {
      const detail = await groups.get(groupId);
      setGroupDetail(detail);
      setExpandedGroup(groupId);
    } catch (err) {
      setError(err.message);
    }
  }

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setError('');
    setShowModal(true);
  }

  function openEdit(group) {
    setEditing(group);
    setForm({
      name: group.name,
      description: group.description || '',
      group_type: group.group_type,
    });
    setError('');
    setShowModal(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    try {
      if (editing) {
        await groups.update(editing.id, form);
      } else {
        await groups.create(form);
      }
      setShowModal(false);
      loadGroups();
    } catch (err) {
      setError(err.data?.messages ? JSON.stringify(err.data.messages) : err.message);
    }
  }

  async function handleDelete(group) {
    if (!confirm(`Delete group "${group.name}"?`)) return;
    try {
      await groups.delete(group.id);
      loadGroups();
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Group Management</h1>
        <button
          onClick={openCreate}
          className="px-4 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700 text-sm font-medium"
        >
          Create Group
        </button>
      </div>

      {error && !showModal && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-md text-sm">
          {error}
        </div>
      )}

      <div className="bg-white shadow rounded-lg overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {groupList.map((group) => (
              <>
                <tr key={group.id}>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">
                    <button
                      onClick={() => toggleExpand(group.id)}
                      className="text-teal-600 hover:text-teal-800 hover:underline"
                    >
                      {group.name}
                    </button>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full capitalize ${
                      group.group_type === 'administrator'
                        ? 'bg-purple-100 text-purple-800'
                        : group.group_type === 'approver'
                        ? 'bg-blue-100 text-blue-800'
                        : 'bg-gray-100 text-gray-800'
                    }`}>
                      {group.group_type}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{group.description || '-'}</td>
                  <td className="px-6 py-4 text-right text-sm space-x-2">
                    <button onClick={() => openEdit(group)} className="text-teal-600 hover:text-teal-800">
                      Edit
                    </button>
                    <button onClick={() => handleDelete(group)} className="text-red-600 hover:text-red-800">
                      Delete
                    </button>
                  </td>
                </tr>
                {expandedGroup === group.id && groupDetail && (
                  <tr key={`${group.id}-members`}>
                    <td colSpan="4" className="px-6 py-4 bg-gray-50">
                      <div className="text-sm font-medium text-gray-700 mb-2">Members:</div>
                      {groupDetail.members && groupDetail.members.length > 0 ? (
                        <ul className="space-y-1 text-sm text-gray-600">
                          {groupDetail.members.map((m) => (
                            <li key={m.id}>{m.first_name} {m.last_name} ({m.username})</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-gray-400">No members</p>
                      )}
                    </td>
                  </tr>
                )}
              </>
            ))}
            {groupList.length === 0 && (
              <tr>
                <td colSpan="4" className="px-6 py-8 text-center text-gray-500">No groups found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
            <form onSubmit={handleSubmit}>
              <div className="px-6 py-4 border-b">
                <h2 className="text-lg font-semibold text-gray-900">
                  {editing ? 'Edit Group' : 'Create Group'}
                </h2>
              </div>

              <div className="px-6 py-4 space-y-4">
                {error && (
                  <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-md text-sm">
                    {error}
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                  <input
                    type="text"
                    required
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                  <select
                    value={form.group_type}
                    onChange={(e) => setForm({ ...form, group_type: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                  >
                    {GROUP_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <textarea
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-teal-500 focus:border-teal-500"
                  />
                </div>
              </div>

              <div className="px-6 py-4 border-t flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-sm font-medium text-white bg-teal-600 rounded-md hover:bg-teal-700"
                >
                  {editing ? 'Save Changes' : 'Create Group'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
