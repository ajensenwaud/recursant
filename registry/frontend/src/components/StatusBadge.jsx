const statusStyles = {
  // Agent statuses
  draft: 'bg-gray-100 text-gray-800',
  submitted: 'bg-blue-100 text-blue-800',
  testing: 'bg-yellow-100 text-yellow-800',
  evaluating: 'bg-yellow-100 text-yellow-800',
  security_failed: 'bg-red-100 text-red-800',
  evaluation_failed: 'bg-red-100 text-red-800',
  pending_approval: 'bg-purple-100 text-purple-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  active: 'bg-green-100 text-green-800',
  suspended: 'bg-orange-100 text-orange-800',
  decommissioned: 'bg-gray-100 text-gray-800',

  // Scan/Evaluation statuses
  pending: 'bg-gray-100 text-gray-800',
  running: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-green-100 text-green-800',
  passed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  error: 'bg-red-100 text-red-800',

  // Tool statuses
  revoked: 'bg-red-100 text-red-800',

  // Mesh statuses
  healthy: 'bg-green-100 text-green-800',
  unhealthy: 'bg-red-100 text-red-800',
  blocked: 'bg-red-100 text-red-800',
  allowed: 'bg-green-100 text-green-800',

  // Severity levels
  critical: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-blue-100 text-blue-800',
  info: 'bg-gray-100 text-gray-800',

  // Default
  default: 'bg-gray-100 text-gray-800',
};

export default function StatusBadge({ status }) {
  const normalizedStatus = status?.toLowerCase().replace(/ /g, '_') || 'default';
  const style = statusStyles[normalizedStatus] || statusStyles.default;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${style}`}
    >
      {status?.replace(/_/g, ' ')}
    </span>
  );
}
