import { NavLink } from 'react-router-dom';
import {
  HomeIcon,
  CubeIcon,
  ShieldCheckIcon,
  ShieldExclamationIcon,
  BeakerIcon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
  DocumentTextIcon,
  CheckBadgeIcon,
  BoltIcon,
  SignalIcon,
  EyeIcon,
  UsersIcon,
  RectangleGroupIcon,
  WrenchScrewdriverIcon,
  WrenchIcon,
  ChartBarIcon,
  PresentationChartLineIcon,
  ScaleIcon,
  GlobeAltIcon,
  SquaresPlusIcon,
  BellAlertIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline';
import { useAuth, hasMinRole } from '../hooks/useAuth';

const navigation = {
  operations: [
    { name: 'Dashboard', href: '/', icon: HomeIcon, minRole: 'user' },
    { name: 'Submissions', href: '/submissions', icon: CubeIcon, minRole: 'administrator' },
    { name: 'Security Scans', href: '/security', icon: ShieldCheckIcon, minRole: 'approver' },
    { name: 'Security Tests', href: '/security-test-cases', icon: BeakerIcon, minRole: 'administrator' },
    { name: 'Evaluations', href: '/evaluations', icon: ClipboardDocumentCheckIcon, minRole: 'approver' },
    { name: 'Evaluation Suites', href: '/evaluation-suites', icon: DocumentTextIcon, minRole: 'administrator' },
    { name: 'Approvals', href: '/approvals', icon: CheckBadgeIcon, minRole: 'approver' },
    { name: 'Active Agents', href: '/active-agents', icon: BoltIcon, minRole: 'approver' },
    { name: 'Mesh Sidecars', href: '/mesh-sidecars', icon: SignalIcon, minRole: 'approver' },
    { name: 'Submitted Tools', href: '/submitted-tools', icon: WrenchScrewdriverIcon, minRole: 'approver' },
    { name: 'Approved Tools', href: '/approved-tools', icon: WrenchIcon, minRole: 'approver' },
    { name: 'Metric Store', href: '/guardrail-metrics', icon: SquaresPlusIcon, minRole: 'approver' },
    { name: 'Guardrails', href: '/guardrails', icon: ShieldExclamationIcon, minRole: 'approver' },
    { name: 'Guardrail Insights', href: '/guardrail-observability', icon: ChartBarIcon, minRole: 'approver' },
    { name: 'Configurations', href: '/guardrail-configs', icon: Cog6ToothIcon, minRole: 'approver' },
    { name: 'Webhooks', href: '/webhooks', icon: BellAlertIcon, minRole: 'approver' },
    { name: 'Adversarial Testing', href: '/adversarial-testing', icon: BeakerIcon, minRole: 'administrator' },
    { name: 'Attack Library', href: '/custom-attacks', icon: DocumentTextIcon, minRole: 'administrator' },
    { name: 'Network Discovery', href: '/network-discovery', icon: GlobeAltIcon, minRole: 'administrator' },
    { name: 'Mesh Visualiser', href: '/mesh-visualiser', icon: EyeIcon, minRole: 'administrator' },
    { name: 'Observability', href: '/observability', icon: PresentationChartLineIcon, minRole: 'approver' },
  ],
  compliance: [
    { name: 'EU AI Act', href: '/compliance', icon: ScaleIcon, minRole: 'approver' },
  ],
  administration: [
    { name: 'Mesh Audit', href: '/mesh-audit', icon: ClipboardDocumentListIcon, minRole: 'administrator' },
    { name: 'Audit Log', href: '/audit-log', icon: ClipboardDocumentListIcon, minRole: 'administrator' },
    { name: 'User Management', href: '/users', icon: UsersIcon, minRole: 'administrator' },
    { name: 'Group Management', href: '/groups', icon: RectangleGroupIcon, minRole: 'administrator' },
  ],
};

export default function Sidebar() {
  const { user } = useAuth();
  const userRole = user?.effective_role || 'user';

  const renderNavItems = (items) =>
    items
      .filter((item) => hasMinRole(userRole, item.minRole))
      .map((item) => (
        <NavLink
          key={item.name}
          to={item.href}
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
              isActive
                ? 'bg-brand-teal/15 text-brand-teal border-l-2 border-brand-teal pl-2.5'
                : 'text-brand-muted hover:bg-brand-surface hover:text-brand-text'
            }`
          }
        >
          <item.icon className="h-5 w-5" />
          {item.name}
        </NavLink>
      ));

  return (
    <aside className="w-64 flex-shrink-0 bg-brand-dark border-r border-brand-border overflow-y-auto">
      <nav className="p-4 space-y-6">
        <div>
          <h3 className="px-3 text-xs font-semibold text-brand-dim uppercase tracking-wider mb-2">
            Operations
          </h3>
          <div className="space-y-1">{renderNavItems(navigation.operations)}</div>
        </div>

        {navigation.compliance.some((item) => hasMinRole(userRole, item.minRole)) && (
          <div>
            <h3 className="px-3 text-xs font-semibold text-brand-dim uppercase tracking-wider mb-2">
              Compliance
            </h3>
            <div className="space-y-1">{renderNavItems(navigation.compliance)}</div>
          </div>
        )}

        {navigation.administration.some((item) => hasMinRole(userRole, item.minRole)) && (
          <div>
            <h3 className="px-3 text-xs font-semibold text-brand-dim uppercase tracking-wider mb-2">
              Administration
            </h3>
            <div className="space-y-1">{renderNavItems(navigation.administration)}</div>
          </div>
        )}
      </nav>
    </aside>
  );
}
