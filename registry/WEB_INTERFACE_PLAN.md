# Web Interface Implementation Plan

## Overview

This plan covers the implementation of the React-based admin web interface for Recursant Registry, as specified in REQUIREMENTS.md Section 6.

## Requirements Summary

| ID | Requirement |
|----|-------------|
| REQ-WEB-001 | Viewing submissions |
| REQ-WEB-002 | Deleting submissions |
| REQ-WEB-003 | Viewing security assessment outcomes |
| REQ-WEB-004 | Manually triggering security assessment re-runs |
| REQ-WEB-005 | Viewing evaluation outcomes |
| REQ-WEB-006 | Editing and configuring evaluation rules |
| REQ-WEB-007 | Manually triggering evaluation re-runs |
| REQ-WEB-008 | Viewing submissions pending approval |
| REQ-WEB-009 | Approving and declining submissions |
| REQ-WEB-010 | React-based, simple and appealing UI |
| REQ-WEB-011 | Simple auth (username/password from .env) |

---

## 1. Project Structure

```
registry/
├── app/
│   ├── api/
│   │   ├── auth.py              # NEW: Authentication endpoints
│   │   └── ...
│   └── ...
├── frontend/                     # NEW: React application
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx
│   │   ├── api/
│   │   │   └── client.js        # API client with auth
│   │   ├── components/
│   │   │   ├── Layout.jsx
│   │   │   ├── Navbar.jsx
│   │   │   ├── Sidebar.jsx
│   │   │   ├── StatusBadge.jsx
│   │   │   ├── DataTable.jsx
│   │   │   └── ConfirmDialog.jsx
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Submissions.jsx
│   │   │   ├── SubmissionDetail.jsx
│   │   │   ├── SecurityScans.jsx
│   │   │   ├── Evaluations.jsx
│   │   │   ├── EvaluationSuites.jsx
│   │   │   └── Approvals.jsx
│   │   ├── hooks/
│   │   │   ├── useAuth.js
│   │   │   └── useApi.js
│   │   └── styles/
│   │       └── index.css
│   └── Dockerfile
├── docker-compose.yml            # Updated to include frontend
└── .env                          # Add ADMIN_USERNAME, ADMIN_PASSWORD
```

---

## 2. Backend Changes

### 2.1 Authentication API (`app/api/auth.py`)

New endpoints for simple session-based authentication:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/auth/login` | POST | Authenticate with username/password |
| `/v1/auth/logout` | POST | End session |
| `/v1/auth/me` | GET | Get current user info |

Implementation:
- Use Flask-Login or simple JWT tokens
- Credentials stored in environment variables:
  - `ADMIN_USERNAME` (default: `admin`)
  - `ADMIN_PASSWORD` (required, no default)
- Session stored in Redis for scalability

### 2.2 Environment Variables

Add to `.env.example`:
```bash
# Admin Authentication
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
JWT_SECRET_KEY=your-secret-key-here
```

### 2.3 API Updates

Minor updates to existing APIs to support the web interface:

| Endpoint | Change |
|----------|--------|
| `DELETE /v1/agents/{id}` | Ensure works for admin deletion (REQ-WEB-002) |
| `POST /v1/agents/{id}/security-scans` | Already exists (REQ-WEB-004) |
| `POST /v1/agents/{id}/evaluations` | Already exists (REQ-WEB-007) |
| `GET /v1/evaluation-suites` | Already exists |
| `PUT /v1/evaluation-suites/{id}` | Add if missing (REQ-WEB-006) |
| `POST /v1/agents/{id}/approval` | Already exists (REQ-WEB-009) |

---

## 3. Frontend Implementation

### 3.1 Technology Stack

- **React 18** - UI framework
- **Vite** - Build tool (fast, modern)
- **React Router v6** - Client-side routing
- **TanStack Query** - Server state management
- **Tailwind CSS** - Styling (simple, utility-first)
- **Heroicons** - Icons
- **date-fns** - Date formatting

### 3.2 Pages

#### Login Page (`/login`)
- Simple username/password form
- Redirects to dashboard on success
- Shows error message on failure

#### Dashboard (`/`)
- Overview statistics:
  - Total agents by status
  - Recent submissions
  - Pending approvals count
  - Failed security scans count
- Quick action links

#### Submissions (`/submissions`)
- Table of all agent submissions
- Columns: Name, Version, Status, Owner, Submitted, Actions
- Filters: Status, Risk Tier, Date Range
- Actions: View Details, Delete
- Pagination

#### Submission Detail (`/submissions/:id`)
- Agent metadata display
- Capabilities list
- Endpoint configuration
- Security scan history with results
- Evaluation history with results
- Approval status and history
- Action buttons:
  - Trigger Security Scan
  - Trigger Evaluation
  - Delete Agent

#### Security Scans (`/security`)
- Table of recent security scans across all agents
- Columns: Agent, Status, Started, Completed, Pass/Fail
- Click to view detailed results
- Filter by status, scan type

#### Evaluations (`/evaluations`)
- Table of recent evaluations
- Columns: Agent, Suite, Status, Score, Date
- Click to view detailed results with judge reasoning

#### Evaluation Suites (`/evaluation-suites`)
- List of evaluation suites
- Create/Edit suite modal
- Manage test cases within suites
- Configure judge settings

#### Approvals (`/approvals`)
- List of agents in PENDING_APPROVAL status
- Shows security scan and evaluation summary
- Approve/Reject buttons with justification modal
- History of approval decisions

### 3.3 Components

| Component | Purpose |
|-----------|---------|
| `Layout` | Page wrapper with navbar and sidebar |
| `Navbar` | Top navigation with user menu, logout |
| `Sidebar` | Navigation links to all pages |
| `StatusBadge` | Colored badge for status display |
| `DataTable` | Reusable sortable, filterable table |
| `ConfirmDialog` | Modal for destructive actions |
| `JsonViewer` | Pretty-print JSON data |
| `ScoreBar` | Visual score display (0-100%) |

### 3.4 Authentication Flow

1. User visits any page
2. `useAuth` hook checks for valid token
3. If no token or expired, redirect to `/login`
4. Login form posts to `/v1/auth/login`
5. On success, store JWT in localStorage
6. Include token in all API requests via `Authorization: Bearer <token>`
7. Logout clears token and redirects to login

---

## 4. Docker Integration

### 4.1 Frontend Dockerfile (`frontend/Dockerfile`)

```dockerfile
# Build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### 4.2 Nginx Configuration (`frontend/nginx.conf`)

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to backend
    location /v1/ {
        proxy_pass http://api:5000/v1/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 4.3 Docker Compose Update

Add to `docker-compose.yml`:

```yaml
  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - api
    environment:
      - API_URL=http://api:5000
```

---

## 5. Implementation Phases

### Phase 1: Backend Auth & Setup
1. Add authentication endpoints (`/v1/auth/*`)
2. Add JWT token handling
3. Update `.env.example` with auth variables
4. Add `PUT /v1/evaluation-suites/{id}` if missing

### Phase 2: Frontend Scaffolding
1. Initialize Vite + React project
2. Set up Tailwind CSS
3. Create basic layout components
4. Implement authentication flow
5. Set up React Router

### Phase 3: Core Pages
1. Login page
2. Dashboard with statistics
3. Submissions list and detail pages
4. Delete functionality

### Phase 4: Security & Evaluation Pages
1. Security scans page
2. Evaluations page
3. Trigger re-run functionality
4. Evaluation suites management

### Phase 5: Approvals
1. Approvals page
2. Approve/Reject with justification
3. Approval history

### Phase 6: Polish & Testing
1. Error handling and loading states
2. Responsive design
3. Integration testing
4. Documentation update

---

## 6. UI Design Guidelines

Per REQ-WEB-010, the interface should be "simple and appealing":

- **Clean layout**: Generous whitespace, clear hierarchy
- **Minimal color palette**:
  - Primary: Blue (#3B82F6)
  - Success: Green (#10B981)
  - Warning: Yellow (#F59E0B)
  - Error: Red (#EF4444)
  - Neutral: Gray shades
- **Status indicators**: Color-coded badges
- **Clear typography**: System font stack
- **Consistent spacing**: 4px base unit
- **Accessible**: WCAG 2.1 AA compliance

---

## 7. API Endpoints Summary

### Existing (to be used)
- `GET /v1/agents` - List all agents
- `GET /v1/agents/{id}` - Agent details
- `DELETE /v1/agents/{id}` - Delete agent
- `GET /v1/agents/{id}/security-scans` - List scans
- `POST /v1/agents/{id}/security-scans` - Trigger scan
- `GET /v1/agents/{id}/evaluations` - List evaluations
- `POST /v1/agents/{id}/evaluations` - Trigger evaluation
- `GET /v1/evaluation-suites` - List suites
- `POST /v1/evaluation-suites` - Create suite
- `GET /v1/agents/{id}/approval` - Approval status
- `POST /v1/agents/{id}/approval` - Submit decision
- `GET /v1/approvals/pending` - Pending approvals

### New (to be added)
- `POST /v1/auth/login` - Authenticate
- `POST /v1/auth/logout` - End session
- `GET /v1/auth/me` - Current user
- `PUT /v1/evaluation-suites/{id}` - Update suite
- `GET /v1/dashboard/stats` - Dashboard statistics

---

## 8. Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 1: Backend Auth | 1 day |
| Phase 2: Frontend Scaffolding | 1 day |
| Phase 3: Core Pages | 2 days |
| Phase 4: Security & Evaluation | 2 days |
| Phase 5: Approvals | 1 day |
| Phase 6: Polish & Testing | 1 day |
| **Total** | **~8 days** |

---

## 9. Open Questions

1. Should there be multiple admin users, or just one configured in .env?
   - *Current plan: Single admin user from .env per REQ-WEB-011*

2. Should the frontend be served from the same container as the API, or separately?
   - *Current plan: Separate container (nginx) for better separation of concerns*

3. Are there any specific branding requirements (logo, colors)?
   - *Current plan: Generic clean design, can be customized later*

---

*Plan Version: 1.0*
*Created: 2026-01-27*
