import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, RequireAuth, RequireRole } from './hooks/useAuth';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Submissions from './pages/Submissions';
import SubmissionDetail from './pages/SubmissionDetail';
import SecurityScans from './pages/SecurityScans';
import Evaluations from './pages/Evaluations';
import EvaluationSuites from './pages/EvaluationSuites';
import EvaluationSuiteDetail from './pages/EvaluationSuiteDetail';
import Approvals from './pages/Approvals';
import ActiveAgents from './pages/ActiveAgents';
import SecurityTestCases from './pages/SecurityTestCases';
import MeshSidecars from './pages/MeshSidecars';
import SubmittedTools from './pages/SubmittedTools';
import ApprovedTools from './pages/ApprovedTools';
import MeshToolDetail from './pages/MeshToolDetail';
import MeshVisualiser from './pages/MeshVisualiser';
import MeshAuditExplorer from './pages/MeshAuditExplorer';
import AuditLog from './pages/AuditLog';
import Users from './pages/Users';
import Groups from './pages/Groups';
import Guardrails from './pages/Guardrails';
import GuardrailDetail from './pages/GuardrailDetail';
import GuardrailObservability from './pages/GuardrailObservability';
import AdversarialTesting from './pages/AdversarialTesting';
import AdversarialRunDetail from './pages/AdversarialRunDetail';
import CustomAttackLibrary from './pages/CustomAttackLibrary';
import ObservabilityDashboard from './pages/ObservabilityDashboard';
import EUAICompliance from './pages/EUAICompliance';
import AgentCompliance from './pages/AgentCompliance';
import EUAIClassificationWizard from './pages/EUAIClassificationWizard';
import AnnexIVEditor from './pages/AnnexIVEditor';
import NetworkDiscovery from './pages/NetworkDiscovery';
import GuardrailMetrics from './pages/GuardrailMetrics';
import Webhooks from './pages/Webhooks';
import GuardrailConfigs from './pages/GuardrailConfigs';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <Layout />
                </RequireAuth>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="submissions" element={<Submissions />} />
              <Route path="submissions/:id" element={<SubmissionDetail />} />
              <Route path="security" element={<SecurityScans />} />
              <Route path="evaluations" element={<Evaluations />} />
              <Route path="evaluation-suites" element={<EvaluationSuites />} />
              <Route path="evaluation-suites/:id" element={<EvaluationSuiteDetail />} />
              <Route
                path="security-test-cases"
                element={
                  <RequireRole minRole="administrator">
                    <SecurityTestCases />
                  </RequireRole>
                }
              />
              <Route path="approvals" element={<Approvals />} />
              <Route path="active-agents" element={<ActiveAgents />} />
              <Route
                path="mesh-sidecars"
                element={
                  <RequireRole minRole="approver">
                    <MeshSidecars />
                  </RequireRole>
                }
              />
              <Route
                path="submitted-tools"
                element={
                  <RequireRole minRole="approver">
                    <SubmittedTools />
                  </RequireRole>
                }
              />
              <Route
                path="approved-tools"
                element={
                  <RequireRole minRole="approver">
                    <ApprovedTools />
                  </RequireRole>
                }
              />
              <Route
                path="mesh-tools/:id"
                element={
                  <RequireRole minRole="approver">
                    <MeshToolDetail />
                  </RequireRole>
                }
              />
              <Route
                path="mesh-visualiser"
                element={
                  <RequireRole minRole="administrator">
                    <MeshVisualiser />
                  </RequireRole>
                }
              />
              <Route
                path="guardrail-configs"
                element={
                  <RequireRole minRole="approver">
                    <GuardrailConfigs />
                  </RequireRole>
                }
              />
              <Route
                path="webhooks"
                element={
                  <RequireRole minRole="approver">
                    <Webhooks />
                  </RequireRole>
                }
              />
              <Route
                path="guardrail-metrics"
                element={
                  <RequireRole minRole="approver">
                    <GuardrailMetrics />
                  </RequireRole>
                }
              />
              <Route
                path="guardrails"
                element={
                  <RequireRole minRole="approver">
                    <Guardrails />
                  </RequireRole>
                }
              />
              <Route
                path="guardrails/:id"
                element={
                  <RequireRole minRole="approver">
                    <GuardrailDetail />
                  </RequireRole>
                }
              />
              <Route
                path="guardrail-observability"
                element={
                  <RequireRole minRole="approver">
                    <GuardrailObservability />
                  </RequireRole>
                }
              />
              <Route
                path="adversarial-testing"
                element={
                  <RequireRole minRole="administrator">
                    <AdversarialTesting />
                  </RequireRole>
                }
              />
              <Route
                path="adversarial-testing/:suiteId/runs/:runId"
                element={
                  <RequireRole minRole="administrator">
                    <AdversarialRunDetail />
                  </RequireRole>
                }
              />
              <Route
                path="custom-attacks"
                element={
                  <RequireRole minRole="administrator">
                    <CustomAttackLibrary />
                  </RequireRole>
                }
              />
              <Route
                path="compliance"
                element={
                  <RequireRole minRole="approver">
                    <EUAICompliance />
                  </RequireRole>
                }
              />
              <Route
                path="compliance/:agentId"
                element={
                  <RequireRole minRole="approver">
                    <AgentCompliance />
                  </RequireRole>
                }
              />
              <Route
                path="compliance/:agentId/classify"
                element={
                  <RequireRole minRole="approver">
                    <EUAIClassificationWizard />
                  </RequireRole>
                }
              />
              <Route
                path="compliance/:agentId/annex-iv/:docId"
                element={
                  <RequireRole minRole="approver">
                    <AnnexIVEditor />
                  </RequireRole>
                }
              />
              <Route
                path="observability"
                element={
                  <RequireRole minRole="approver">
                    <ObservabilityDashboard />
                  </RequireRole>
                }
              />
              <Route
                path="network-discovery"
                element={
                  <RequireRole minRole="administrator">
                    <NetworkDiscovery />
                  </RequireRole>
                }
              />
              <Route
                path="mesh-audit"
                element={
                  <RequireRole minRole="administrator">
                    <MeshAuditExplorer />
                  </RequireRole>
                }
              />
              <Route
                path="audit-log"
                element={
                  <RequireRole minRole="administrator">
                    <AuditLog />
                  </RequireRole>
                }
              />
              <Route
                path="users"
                element={
                  <RequireRole minRole="administrator">
                    <Users />
                  </RequireRole>
                }
              />
              <Route
                path="groups"
                element={
                  <RequireRole minRole="administrator">
                    <Groups />
                  </RequireRole>
                }
              />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
