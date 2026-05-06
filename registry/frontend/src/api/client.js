/**
 * API client for Recursant Registry.
 * Handles authentication and request/response processing.
 */

const API_BASE = '/v1';

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

function getToken() {
  return localStorage.getItem('token');
}

function setToken(token) {
  localStorage.setItem('token', token);
}

function clearToken() {
  localStorage.removeItem('token');
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const token = getToken();

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  // Handle 401 - redirect to login
  if (response.status === 401) {
    clearToken();
    window.location.href = '/login';
    throw new ApiError('Unauthorized', 401);
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      data?.error || 'Request failed',
      response.status,
      data
    );
  }

  return data;
}

// Auth API
export const auth = {
  login: async (username, password) => {
    const data = await request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    setToken(data.token);
    return data;
  },

  logout: async () => {
    try {
      await request('/auth/logout', { method: 'POST' });
    } finally {
      clearToken();
    }
  },

  me: () => request('/auth/me'),

  isAuthenticated: () => !!getToken(),
};

// Agents API
export const agents = {
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/agents${query ? `?${query}` : ''}`);
  },

  get: (id) => request(`/agents/${id}`),

  create: (data) => request('/agents', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (id, data) => request(`/agents/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (id) => request(`/agents/${id}`, {
    method: 'DELETE',
  }),

  submit: (id) => request(`/agents/${id}/submit`, {
    method: 'POST',
  }),
};

// Security Scans API
export const securityScans = {
  list: (agentId, params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/agents/${agentId}/security-scans${query ? `?${query}` : ''}`);
  },

  get: (agentId, scanId) => request(`/agents/${agentId}/security-scans/${scanId}`),

  trigger: (agentId, data = {}) => request(`/agents/${agentId}/security-scans`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
};

// Evaluations API
export const evaluations = {
  list: (agentId, params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/agents/${agentId}/evaluations${query ? `?${query}` : ''}`);
  },

  get: (agentId, evalId) => request(`/agents/${agentId}/evaluations/${evalId}`),

  trigger: (agentId, data = {}) => request(`/agents/${agentId}/evaluations`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
};

// Evaluation Suites API
export const evaluationSuites = {
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/evaluation-suites${query ? `?${query}` : ''}`);
  },

  get: (id) => request(`/evaluation-suites/${id}`),

  create: (data) => request('/evaluation-suites', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (id, data) => request(`/evaluation-suites/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  testCases: {
    list: (suiteId) => request(`/evaluation-suites/${suiteId}/test-cases`),

    get: (suiteId, tcId) => request(`/evaluation-suites/${suiteId}/test-cases/${tcId}`),

    create: (suiteId, data) => request(`/evaluation-suites/${suiteId}/test-cases`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

    update: (suiteId, tcId, data) => request(`/evaluation-suites/${suiteId}/test-cases/${tcId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

    delete: (suiteId, tcId) => request(`/evaluation-suites/${suiteId}/test-cases/${tcId}`, {
      method: 'DELETE',
    }),
  },
};

// Security Test Cases API
export const securityTestCases = {
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/security-test-cases${query ? `?${query}` : ''}`);
  },

  get: (id) => request(`/security-test-cases/${id}`),

  create: (data) => request('/security-test-cases', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (id, data) => request(`/security-test-cases/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (id) => request(`/security-test-cases/${id}`, {
    method: 'DELETE',
  }),

  resetDefaults: () => request('/security-test-cases/reset', {
    method: 'POST',
  }),
};

// Approvals API
export const approvals = {
  pending: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/approvals/pending${query ? `?${query}` : ''}`);
  },

  getStatus: (agentId) => request(`/agents/${agentId}/approval`),

  submit: (agentId, data) => request(`/agents/${agentId}/approval`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
};

// Active Agents API
export const activeAgents = {
  list: () => request('/agents/active'),

  suspend: (agentId, data) => request(`/agents/${agentId}/suspend`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
};

// Mesh Sidecars API
export const meshSidecars = {
  list: () => request('/mesh/registrations'),
};

// Mesh Tools API
export const meshTools = {
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/mesh/tools${query ? `?${query}` : ''}`);
  },
  get: (id) => request(`/mesh/tools/${id}`),
  create: (data) => request('/mesh/tools', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  update: (id, data) => request(`/mesh/tools/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  }),
  delete: (id) => request(`/mesh/tools/${id}`, {
    method: 'DELETE',
  }),
  approve: (id, data = {}) => request(`/mesh/tools/${id}/approve`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  revoke: (id, data = {}) => request(`/mesh/tools/${id}/revoke`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  withAssignments: () => request('/mesh/tools/with-assignments'),
  assignments: {
    list: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/mesh/tool-assignments${query ? `?${query}` : ''}`);
    },
    create: (data) => request('/mesh/tool-assignments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    delete: (id) => request(`/mesh/tool-assignments/${id}`, {
      method: 'DELETE',
    }),
  },
};

// Mesh Visualiser API
export const meshVisualiser = {
  registrations: () => request('/mesh/registrations'),
  audit: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/mesh/audit${query ? `?${query}` : ''}`);
  },
  edgeAudit: (source, dest, params = {}) => {
    const query = new URLSearchParams({ source_agent: source, dest_agent: dest, ...params }).toString();
    return request(`/mesh/audit?${query}`);
  },
  policies: () => request('/mesh/policies'),
  toolsWithAssignments: () => request('/mesh/tools/with-assignments'),
};

// Guardrails API
export const guardrails = {
  list: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined))
    ).toString();
    return request(`/guardrails${query ? `?${query}` : ''}`);
  },
  get: (id) => request(`/guardrails/${id}`),
  create: (data) => request('/guardrails', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  update: (id, data) => request(`/guardrails/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  delete: (id) => request(`/guardrails/${id}`, {
    method: 'DELETE',
  }),
  activate: (id) => request(`/guardrails/${id}/activate`, {
    method: 'POST',
  }),
  disable: (id) => request(`/guardrails/${id}/disable`, {
    method: 'POST',
  }),
  assignments: {
    list: (guardrailId) => request(`/guardrails/${guardrailId}/assignments`),
    create: (guardrailId, data) => request(`/guardrails/${guardrailId}/assignments`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    delete: (guardrailId, assignmentId) => request(`/guardrails/${guardrailId}/assignments/${assignmentId}`, {
      method: 'DELETE',
    }),
  },
  test: (id, data) => request(`/guardrails/${id}/test`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  testRuns: {
    list: (guardrailId) => request(`/guardrails/${guardrailId}/test-runs`),
    get: (guardrailId, runId) => request(`/guardrails/${guardrailId}/test-runs/${runId}`),
  },
};

// Guardrail Configs API
export const guardrailConfigs = {
  list: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined))
    ).toString();
    return request(`/guardrail-configs${query ? `?${query}` : ''}`);
  },
  get: (id) => request(`/guardrail-configs/${id}`),
  create: (data) => request('/guardrail-configs', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  update: (id, data) => request(`/guardrail-configs/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  delete: (id) => request(`/guardrail-configs/${id}`, {
    method: 'DELETE',
  }),
  activate: (id) => request(`/guardrail-configs/${id}/activate`, {
    method: 'POST',
  }),
  clone: (id, data) => request(`/guardrail-configs/${id}/clone`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  diff: (configA, configB) => request(`/guardrail-configs/diff?config_a=${configA}&config_b=${configB}`),
  entries: {
    list: (configId) => request(`/guardrail-configs/${configId}/entries`),
    create: (configId, data) => request(`/guardrail-configs/${configId}/entries`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    delete: (configId, entryId) => request(`/guardrail-configs/${configId}/entries/${entryId}`, {
      method: 'DELETE',
    }),
  },
};

// Webhooks API
export const webhooks = {
  list: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined))
    ).toString();
    return request(`/webhooks${query ? `?${query}` : ''}`);
  },
  get: (id) => request(`/webhooks/${id}`),
  create: (data) => request('/webhooks', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  update: (id, data) => request(`/webhooks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  delete: (id) => request(`/webhooks/${id}`, {
    method: 'DELETE',
  }),
  test: (id) => request(`/webhooks/${id}/test`, {
    method: 'POST',
  }),
  subscriptions: {
    list: (params = {}) => {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined))
      ).toString();
      return request(`/webhook-subscriptions${query ? `?${query}` : ''}`);
    },
    create: (data) => request('/webhook-subscriptions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    delete: (id) => request(`/webhook-subscriptions/${id}`, {
      method: 'DELETE',
    }),
  },
  deliveryLogs: {
    list: (params = {}) => {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined))
      ).toString();
      return request(`/webhook-delivery-logs${query ? `?${query}` : ''}`);
    },
  },
};

// Guardrail Metrics API
export const guardrailMetrics = {
  list: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined))
    ).toString();
    return request(`/guardrail-metrics${query ? `?${query}` : ''}`);
  },
  get: (id) => request(`/guardrail-metrics/${id}`),
  create: (data) => request('/guardrail-metrics', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  update: (id, data) => request(`/guardrail-metrics/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  delete: (id) => request(`/guardrail-metrics/${id}`, {
    method: 'DELETE',
  }),
  createGuardrail: (metricId, data) => request(`/guardrail-metrics/${metricId}/create-guardrail`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  generateTestCases: (metricId) => request(`/guardrail-metrics/${metricId}/generate-test-cases`, {
    method: 'POST',
  }),
  scores: {
    list: (metricId, params = {}) => {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined))
      ).toString();
      return request(`/guardrail-metrics/${metricId}/scores${query ? `?${query}` : ''}`);
    },
    record: (metricId, data) => request(`/guardrail-metrics/${metricId}/scores`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  },
};

// Dashboard API
export const dashboard = {
  stats: () => request('/dashboard/stats'),
};

// Users API
export const users = {
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/users${query ? `?${query}` : ''}`);
  },

  get: (id) => request(`/users/${id}`),

  create: (data) => request('/users', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (id, data) => request(`/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (id) => request(`/users/${id}`, {
    method: 'DELETE',
  }),

  setGroups: (id, groupIds) => request(`/users/${id}/groups`, {
    method: 'PUT',
    body: JSON.stringify({ group_ids: groupIds }),
  }),
};

// Groups API
export const groups = {
  list: () => request('/groups'),

  get: (id) => request(`/groups/${id}`),

  create: (data) => request('/groups', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (id, data) => request(`/groups/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (id) => request(`/groups/${id}`, {
    method: 'DELETE',
  }),
};

// Mesh Audit API
export const meshAudit = {
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/mesh/audit${query ? `?${query}` : ''}`);
  },

  stats: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/mesh/audit/stats${query ? `?${query}` : ''}`);
  },

  get: (id) => request(`/mesh/audit/${id}`),
};

// Audit Logs API
export const auditLogs = {
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/audit-logs${query ? `?${query}` : ''}`);
  },

  get: (id) => request(`/audit-logs/${id}`),
};

// Guardrail Observability API
export const guardrailObservability = {
  summary: () => request('/guardrails/observability/summary'),
  triggerRates: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
    ).toString();
    return request(`/guardrails/observability/trigger-rates${query ? `?${query}` : ''}`);
  },
  latency: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
    ).toString();
    return request(`/guardrails/observability/latency${query ? `?${query}` : ''}`);
  },
  topBlocked: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
    ).toString();
    return request(`/guardrails/observability/top-blocked${query ? `?${query}` : ''}`);
  },
  drift: (params = {}) => {
    const query = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
    ).toString();
    return request(`/guardrails/observability/drift${query ? `?${query}` : ''}`);
  },
};

// Adversarial Testing API
export const adversarial = {
  suites: {
    list: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/adversarial-suites${query ? `?${query}` : ''}`);
    },
    get: (id) => request(`/adversarial-suites/${id}`),
    create: (data) => request('/adversarial-suites', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    update: (id, data) => request(`/adversarial-suites/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
    delete: (id) => request(`/adversarial-suites/${id}`, {
      method: 'DELETE',
    }),
    triggerRun: (id) => request(`/adversarial-suites/${id}/run`, {
      method: 'POST',
    }),
  },
  runs: {
    list: (suiteId) => request(`/adversarial-suites/${suiteId}/runs`),
    get: (suiteId, runId) => request(`/adversarial-suites/${suiteId}/runs/${runId}`),
  },
  alerts: () => request('/adversarial-alerts'),
};

// Custom Attacks API
export const customAttacks = {
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/custom-attacks${query ? `?${query}` : ''}`);
  },
  get: (id) => request(`/custom-attacks/${id}`),
  create: (data) => request('/custom-attacks', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  update: (id, data) => request(`/custom-attacks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  delete: (id) => request(`/custom-attacks/${id}`, {
    method: 'DELETE',
  }),
  import: (data) => request('/custom-attacks/import', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  export: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/custom-attacks/export${query ? `?${query}` : ''}`);
  },
};

// Observability API
export const observability = {
  traces: {
    list: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/mesh/observability/traces${query ? `?${query}` : ''}`);
    },
    get: (taskId) => request(`/mesh/observability/traces/${taskId}`),
  },
  goldenSignals: {
    summary: () => request('/mesh/observability/golden-signals'),
    agent: (agentName) => request(`/mesh/observability/golden-signals/${encodeURIComponent(agentName)}`),
  },
  cost: {
    summary: () => request('/mesh/observability/cost'),
    agent: (agentName) => request(`/mesh/observability/cost/${encodeURIComponent(agentName)}`),
  },
  alerts: {
    list: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/mesh/observability/alerts${query ? `?${query}` : ''}`);
    },
    get: (id) => request(`/mesh/observability/alerts/${id}`),
    acknowledge: (id) => request(`/mesh/observability/alerts/${id}/acknowledge`, { method: 'POST' }),
    resolve: (id) => request(`/mesh/observability/alerts/${id}/resolve`, { method: 'POST' }),
  },
  security: {
    posture: () => request('/mesh/observability/security/posture'),
  },
  tools: {
    metrics: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/mesh/observability/tools/metrics${query ? `?${query}` : ''}`);
    },
    effectiveness: (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return request(`/mesh/observability/tools/effectiveness${query ? `?${query}` : ''}`);
    },
  },
};

// EU AI Act Compliance API
export const compliance = {
  dashboard: () => request('/compliance/dashboard'),
  requirements: () => request('/compliance/requirements'),

  classification: {
    get: (agentId) => request(`/agents/${agentId}/euai-classification`),
    create: (agentId, data) => request(`/agents/${agentId}/euai-classification`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    update: (agentId, data) => request(`/agents/${agentId}/euai-classification`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  },

  statuses: {
    list: (agentId) => request(`/agents/${agentId}/compliance`),
    update: (agentId, reqId, data) => request(`/agents/${agentId}/compliance/${reqId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  },

  autoAssess: (agentId) => request(`/agents/${agentId}/compliance/auto-assess`, {
    method: 'POST',
  }),

  gapAnalysis: (agentId) => request(`/agents/${agentId}/compliance/gap-analysis`),

  annexIV: {
    list: (agentId) => request(`/agents/${agentId}/annex-iv`),
    get: (agentId, docId) => request(`/agents/${agentId}/annex-iv/${docId}`),
    generate: (agentId) => request(`/agents/${agentId}/annex-iv/generate`, {
      method: 'POST',
    }),
    update: (agentId, docId, data) => request(`/agents/${agentId}/annex-iv/${docId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
    regenerate: (agentId, docId) => request(`/agents/${agentId}/annex-iv/${docId}/regenerate`, {
      method: 'POST',
    }),
    approve: (agentId, docId) => request(`/agents/${agentId}/annex-iv/${docId}/approve`, {
      method: 'POST',
    }),
  },

  conformity: {
    list: (agentId) => request(`/agents/${agentId}/conformity`),
    create: (agentId, data) => request(`/agents/${agentId}/conformity`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    addFinding: (agentId, assessmentId, data) => request(`/agents/${agentId}/conformity/${assessmentId}/findings`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    declare: (agentId, assessmentId) => request(`/agents/${agentId}/conformity/${assessmentId}/declare`, {
      method: 'POST',
    }),
  },

  monitoring: {
    get: (agentId) => request(`/agents/${agentId}/monitoring`),
    create: (agentId, data) => request(`/agents/${agentId}/monitoring`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    report: (agentId, data = {}) => request(`/agents/${agentId}/monitoring/report`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  },
};

// Discovery API
export const discovery = {
  scans: {
    list: (params = {}) => {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
      ).toString();
      return request(`/discovery/scans${query ? `?${query}` : ''}`);
    },
    get: (id) => request(`/discovery/scans/${id}`),
    create: (data) => request('/discovery/scans', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    cancel: (id) => request(`/discovery/scans/${id}`, {
      method: 'DELETE',
    }),
    rerun: (id) => request(`/discovery/scans/${id}/rerun`, {
      method: 'POST',
    }),
  },
  agents: {
    list: (params = {}) => {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
      ).toString();
      return request(`/discovery/agents${query ? `?${query}` : ''}`);
    },
    get: (id) => request(`/discovery/agents/${id}`),
    onboard: (id, data = {}) => request(`/discovery/agents/${id}/onboard`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    bulkOnboard: (data) => request('/discovery/agents/bulk-onboard', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    quarantine: (id) => request(`/discovery/agents/${id}/quarantine`, {
      method: 'POST',
    }),
    dismiss: (id) => request(`/discovery/agents/${id}/dismiss`, {
      method: 'POST',
    }),
  },
  tools: {
    list: (params = {}) => {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null))
      ).toString();
      return request(`/discovery/tools${query ? `?${query}` : ''}`);
    },
    onboard: (id) => request(`/discovery/tools/${id}/onboard`, {
      method: 'POST',
    }),
  },
  topology: () => request('/discovery/topology'),
  stats: () => request('/discovery/stats'),
  schedules: {
    list: () => request('/discovery/schedules'),
    create: (data) => request('/discovery/schedules', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    update: (id, data) => request(`/discovery/schedules/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
    delete: (id) => request(`/discovery/schedules/${id}`, {
      method: 'DELETE',
    }),
  },
};

export { ApiError, getToken, clearToken };
