import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  CubeIcon,
  ShieldCheckIcon,
  ClipboardDocumentCheckIcon,
  CheckBadgeIcon,
} from '@heroicons/react/24/outline';
import { dashboard } from '../api/client';

function StatCard({ title, value, icon: Icon, href, color }) {
  return (
    <Link
      to={href}
      className="bg-brand-surface border border-brand-border rounded-lg p-6 hover:border-brand-teal/50 hover:bg-brand-surface-hi transition-colors"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-brand-muted">{title}</p>
          <p className="mt-1 text-3xl font-semibold text-brand-text">{value}</p>
        </div>
        <div className={`p-3 rounded-lg ${color}`}>
          <Icon className="h-6 w-6 text-brand-text" />
        </div>
      </div>
    </Link>
  );
}

export default function Dashboard() {
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: dashboard.stats,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
        Failed to load dashboard: {error.message}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total Agents"
          value={stats?.agents?.total || 0}
          icon={CubeIcon}
          href="/submissions"
          color="bg-brand-dark"
        />
        <StatCard
          title="Security Scans"
          value={stats?.security_scans?.total || 0}
          icon={ShieldCheckIcon}
          href="/security"
          color="bg-brand-teal"
        />
        <StatCard
          title="Evaluations"
          value={stats?.evaluations?.total || 0}
          icon={ClipboardDocumentCheckIcon}
          href="/evaluations"
          color="bg-brand-teal-deep"
        />
        <StatCard
          title="Pending Approvals"
          value={stats?.pending_approvals || 0}
          icon={CheckBadgeIcon}
          href="/approvals"
          color="bg-brand-green"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Agent Status Breakdown */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">
            Agents by Status
          </h2>
          <div className="space-y-3">
            {Object.entries(stats?.agents?.by_status || {}).map(([status, count]) => (
              <div key={status} className="flex items-center justify-between">
                <span className="text-sm text-gray-600 capitalize">
                  {status.replace(/_/g, ' ')}
                </span>
                <span className="text-sm font-medium text-gray-900">{count}</span>
              </div>
            ))}
            {Object.keys(stats?.agents?.by_status || {}).length === 0 && (
              <p className="text-sm text-gray-500">No agents yet</p>
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">
            Quick Actions
          </h2>
          <div className="space-y-3">
            <Link
              to="/submissions"
              className="block px-4 py-2 bg-brand-surface-hi border border-brand-border rounded-md text-sm text-brand-text hover:border-brand-teal hover:bg-brand-surface transition-colors"
            >
              View all submissions
            </Link>
            <Link
              to="/approvals"
              className="block px-4 py-2 bg-brand-surface-hi border border-brand-border rounded-md text-sm text-brand-text hover:border-brand-teal hover:bg-brand-surface transition-colors"
            >
              Review pending approvals ({stats?.pending_approvals || 0})
            </Link>
            <Link
              to="/evaluation-suites"
              className="block px-4 py-2 bg-brand-surface-hi border border-brand-border rounded-md text-sm text-brand-text hover:border-brand-teal hover:bg-brand-surface transition-colors"
            >
              Manage evaluation suites
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
