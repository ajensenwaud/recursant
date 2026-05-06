# Mesh Visualisation Tool - Architecture & Implementation Plan

## 1. Requirements Analysis

### Source Requirements (Phase 2a, mesh/REQUIREMENTS.md)

The visualisation tool provides a real-time, interactive graph view of the agentic mesh. Core requirements:

| # | Requirement | Category |
|---|-------------|----------|
| V1 | Real-time graph showing agents as named nodes and A2A message flows as connections | Core |
| V2 | Connections light up (change colour) for 5 seconds on interaction (configurable) | Animation |
| V3 | Message log on the right-hand side showing all communications with timestamps | UI |
| V4 | Blocked interactions flagged with a different colour | Policy |
| V5 | Agents on the same host/LangGraph instance clustered together with same node colour | Grouping |
| V6 | Connections only drawn after first interaction (not pre-drawn) | Rendering |
| V7 | Hover/click on agent node shows popup with name, endpoint, capability, platform, sidecar info | Interaction |
| V8 | Works on laptops and iPads | Responsive |
| V9 | Zoom and pan support (press-drag to pan the canvas) for hundreds of agents | Navigation |
| V10 | Vector graphics (SVG) for crisp zoom at all levels | Rendering |
| V11 | Auto-update when agents/sidecars are added or removed | Real-time |
| V12 | Python simulation script that runs in an infinite loop, randomly adding/removing agents and sidecars, initiating inter-host A2A messages, and simulating blocked interactions — for validating the visualiser end-to-end | Testing |

---

## 2. Existing Infrastructure

### 2.1 Data Sources

All data needed for the visualisation already exists in the registry:

| Data | Model / Endpoint | What It Provides |
|------|-------------------|-----------------|
| Registered agents | `MeshRegistration` / `GET /v1/mesh/registrations` | Agent nodes: name, sidecar URL (for host clustering), sovereignty zone, status, agent card (capabilities, platform) |
| A2A interactions | `MeshAuditLog` / `GET /v1/mesh/audit` | Edge data: source agent, dest agent, method, outcome (allowed/blocked), timestamp, task ID |
| Auth policies | `MeshPolicy` / `GET /v1/mesh/policies` | Which agent pairs are allowed/blocked (for edge colouring) |
| Agent details | `Agent` model (joined via `MeshRegistration.agent`) | Name, version, classification, capabilities, endpoint type/URL |

### 2.2 Frontend Stack

The registry frontend uses:
- **React 18** with **Vite** bundler
- **TanStack React Query** for data fetching (retry=1, no refetch on focus)
- **Tailwind CSS** for styling
- **React Router v6** for routing
- **Heroicons** for icons
- **date-fns** for timestamp formatting
- Brand colours: dark `#0A0F1C`, teal `#14B8A6`, green `#06D6A0`

### 2.3 Backend Stack

- **Flask** REST API with Blueprint architecture (`app/api/mesh.py`)
- **PostgreSQL** with SQLAlchemy ORM
- **JWT auth** for frontend-facing endpoints, **mesh API key** for sidecar endpoints
- No WebSocket or SSE support currently

---

## 3. Architecture

### 3.1 High-Level Data Flow

```
┌─────────────┐     WebSocket        ┌──────────────────┐
│  Registry    │ ◀═══════════════════▶│  React Frontend  │
│  Flask API   │  (bidirectional)     │                  │
│  + SocketIO  │                      │  MeshVisualiser  │
│              │ ◀────── REST ────── │  page component  │
│  /v1/mesh/*  │  (initial load)     │                  │
└─────────────┘                      └──────────────────┘
       ▲                                     │
       │ audit records                       │ renders
       │ (POST /v1/mesh/audit)               ▼
┌──────┴──────┐                     ┌──────────────────┐
│  Sidecars   │                     │  D3.js SVG Graph │
│  (runtime)  │                     │  + Event Log     │
└─────────────┘                     └──────────────────┘
```

### 3.2 Real-Time Delivery: WebSocket (Socket.IO)

**Why WebSocket over SSE:**
- **Proper auth:** WebSocket upgrade supports JWT via handshake auth — no need to leak tokens in query strings
- **Bidirectional:** Supports future interactive features (deregister from graph, trigger messages, control simulation)
- **No connection limits:** SSE is capped at ~6 concurrent connections per domain in HTTP/1.1
- **Mature ecosystem:** `flask-socketio` + `socket.io-client` provide auto-reconnection, room management, and namespace support out of the box

**Socket.IO namespace:** `/mesh`

The server emits three event types to connected clients:

```javascript
// Agent registered or deregistered
socket.emit('registration', {
  type: 'register',        // or 'deregister'
  agent_id: '...',
  agent_name: '...',
  sidecar_url: '...',
  agent_card: { ... },
  host: '10.0.1.5'
})

// A2A interaction occurred
socket.emit('audit', {
  source_agent_name: 'Agent A',
  dest_agent_name: 'Agent B',
  a2a_method: 'message/send',
  outcome: 'allowed',       // or 'blocked'
  decision: 'allow',
  timestamp: '2026-02-15T12:00:00Z',
  task_id: '...'
})
```

The client can emit commands back to the server (future-proofing for interactive features):

```javascript
// Future: deregister an agent from the graph
socket.emit('deregister_agent', { agent_id: '...' })

// Future: trigger a test message between agents
socket.emit('trigger_message', { source: '...', dest: '...', message: '...' })
```

**Implementation approach:**
- `flask-socketio` with `eventlet` or `gevent` async mode for efficient concurrent connections
- JWT authentication during the WebSocket handshake (`connect` event handler validates the token)
- When `mesh_register()`, `mesh_deregister()`, or `mesh_submit_audit()` REST endpoints are called, emit events to the `/mesh` namespace via `socketio.emit()`
- Heartbeat/ping-pong handled automatically by Socket.IO (configurable interval, default 5s)

### 3.3 Graph Rendering: D3.js with Force-Directed Layout

**Why D3.js over alternatives:**

| Library | SVG | Force Layout | Touch/Zoom | Bundle Size | Verdict |
|---------|-----|-------------|------------|-------------|---------|
| D3.js | Native | d3-force | d3-zoom (pan, pinch-zoom) | ~30 KB (tree-shaken) | Best fit |
| Cytoscape.js | Canvas (no SVG) | Yes | Yes | ~400 KB | Canvas = blurry on zoom |
| vis-network | Canvas | Yes | Yes | ~300 KB | Same canvas issue |
| React Flow | SVG/HTML | dagre only | Yes | ~150 KB | No force layout |

D3.js provides native SVG rendering (requirement V10), force-directed layout for organic clustering, and built-in zoom/pan behaviour (`d3-zoom`) with multi-touch support for iPads (requirement V8/V9). Only the needed modules are imported (`d3-force`, `d3-selection`, `d3-zoom`, `d3-transition`, `d3-scale`), keeping the bundle small.

### 3.4 Component Architecture

```
MeshVisualiser (page)
├── useSocket(namespace)          — custom hook: Socket.IO connection + auth + reconnection
├── useMeshGraph(events)          — custom hook: maintains graph state (nodes, edges, activity)
├── MeshGraph                     — D3 SVG canvas with force layout, zoom, pan
│   ├── <g class="clusters">     — cluster backgrounds (coloured hulls per host)
│   ├── <g class="edges">        — connection lines (drawn on first interaction)
│   │   └── <line> / <path>      — animated stroke on activity, red for blocked
│   └── <g class="nodes">        — agent circles with labels
│       └── <circle> + <text>    — click/hover triggers detail popup
├── AgentDetailPopup              — overlay with agent info (name, endpoint, capabilities, sidecar)
└── EventLog                      — right-hand sidebar with scrolling interaction log
```

---

## 4. Detailed Design

### 4.1 Backend: Socket.IO Integration

**New file:** `app/services/mesh_events.py`

```python
from flask_socketio import SocketIO

# Singleton — initialised in create_app()
socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet")
```

**Initialisation in `create_app()`** (`app/__init__.py`):

```python
from app.services.mesh_events import socketio

def create_app():
    app = Flask(__name__)
    # ... existing setup ...
    socketio.init_app(app)
    return app
```

**WebSocket handlers** in `app/api/mesh_ws.py`:

```python
from flask import request
from flask_socketio import Namespace, disconnect
from app.services.auth_service import decode_jwt  # existing JWT decoder

class MeshNamespace(Namespace):
    """WebSocket namespace for mesh visualiser."""

    def on_connect(self):
        token = request.args.get('token')
        if not token:
            disconnect()
            return False
        try:
            decode_jwt(token)
        except Exception:
            disconnect()
            return False

    def on_disconnect(self):
        pass

    # Future: handle client-initiated commands
    # def on_deregister_agent(self, data): ...
    # def on_trigger_message(self, data): ...
```

**Emitting events from REST handlers** — add to `mesh_register()`, `mesh_deregister()`, `mesh_submit_audit()`:

```python
from app.services.mesh_events import socketio

# After successful registration commit:
socketio.emit('registration', {
    'type': 'register',
    'agent_id': str(agent_id),
    'agent_name': agent.name,
    'sidecar_url': data['sidecar_url'],
    'agent_card': data['agent_card'],
}, namespace='/mesh')

# After successful audit commit (per record):
socketio.emit('audit', {
    'source_agent_name': record_data.get('source_agent_name'),
    'dest_agent_name': record_data.get('dest_agent_name'),
    'a2a_method': record_data['a2a_method'],
    'outcome': record_data['outcome'],
    'decision': record_data['decision'],
    'timestamp': record_data['timestamp'].isoformat(),
    'task_id': record_data.get('task_id'),
}, namespace='/mesh')
```

### 4.2 Frontend: Socket.IO Hook

**New file:** `frontend/src/hooks/useSocket.js`

```javascript
import { useEffect, useRef } from 'react';
import { io } from 'socket.io-client';

export default function useSocket(namespace, onEvent) {
  const socketRef = useRef(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const socket = io(namespace, {
      auth: { token },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: Infinity,
    });
    socketRef.current = socket;

    socket.on('registration', (data) => onEvent('registration', data));
    socket.on('audit', (data) => onEvent('audit', data));

    socket.on('connect_error', (err) => {
      console.error('Mesh WebSocket connection error:', err.message);
    });

    return () => socket.disconnect();
  }, [namespace]);

  return socketRef;
}
```

Authentication is handled cleanly via the `auth` option during handshake — no tokens in URLs.

### 4.3 Frontend: Graph State Management

**New file:** `frontend/src/hooks/useMeshGraph.js`

Manages the graph data model:

```javascript
// State shape:
{
  nodes: Map<agentName, {
    id, name, sidecarUrl, host, capabilities, platform, sovereigntyZone,
    status, registeredAt, agentCard
  }>,
  edges: Map<"src->dest", {
    source, target, lastActivity, outcome, count
  }>,
  activityTimers: Map<"src->dest", timeoutId>,  // 5-second glow timers
  eventLog: [{ timestamp, source, dest, method, outcome }]  // newest first
}
```

**Host clustering:** Extract hostname from `sidecar_url` (e.g. `http://10.0.1.5:9000` -> `10.0.1.5`). Assign each unique host a colour from a palette. D3 force layout uses a custom force to pull same-host nodes together.

**Edge lifecycle (V6):** Edges are only added to the `edges` Map when the first `audit` event arrives for that source->dest pair. No edges are pre-drawn.

**Activity animation (V2):** When an audit event arrives, set the edge's `lastActivity` to `Date.now()` and start a 5-second timer. During this window, the edge gets the "active" CSS class (bright teal glow). After the timer, the class is removed and the edge returns to the base colour. Blocked interactions (V4) use a red colour instead.

### 4.4 Frontend: D3 Graph Component

**New file:** `frontend/src/components/MeshGraph.jsx`

Key implementation details:

1. **SVG container** fills the available space (left side of the page). Uses a `<svg>` element with `viewBox` for responsive sizing.

2. **d3-zoom** applied to the SVG for pan and zoom (V9). Touch events are handled natively by `d3-zoom` for iPad support (V8). Zoom range: 0.1x to 4x.

3. **d3-force simulation** with:
   - `forceCenter` -- centres the graph
   - `forceManyBody` -- node repulsion (charge = -300)
   - `forceLink` -- edge spring force (only for edges that exist)
   - `forceCollide` -- prevents node overlap (radius = 40)
   - Custom `forceCluster` -- attracts same-host nodes toward their cluster centroid

4. **Node rendering:**
   - `<circle>` with radius 20, coloured by host group (V5)
   - `<text>` label below with agent name
   - `cursor: pointer`, click opens `AgentDetailPopup` (V7)
   - Hover shows tooltip with name

5. **Edge rendering:**
   - `<line>` from source to dest
   - Base colour: `#94a3b8` (slate-400)
   - Active colour: `#14B8A6` (teal) with increased stroke width and glow filter, for 5 seconds (V2)
   - Blocked colour: `#EF4444` (red-500) (V4)
   - Animated via CSS transitions on `stroke` and `stroke-width`

6. **Cluster hulls:**
   - `<path>` elements behind nodes showing the convex hull of each host group
   - Fill: host colour at 10% opacity
   - Updated on each simulation tick

### 4.5 Frontend: Event Log Sidebar

**New file:** `frontend/src/components/EventLog.jsx`

- Fixed-width panel (320px) on the right side of the visualiser (V3)
- Scrollable list of events, newest at top
- Each entry shows: timestamp, source -> dest, method, outcome badge
- Outcome badges: green for "allowed", red for "blocked"
- Caps at 500 entries in memory (oldest pruned)
- Collapsible on mobile/iPad via a toggle button

### 4.6 Frontend: Agent Detail Popup

**New file:** `frontend/src/components/AgentDetailPopup.jsx`

Displayed when clicking a node (V7). Shows:
- Agent name and version
- Endpoint URL and type (LangGraph, LangChain, etc.)
- Capabilities list
- Sidecar URL and sovereignty zone
- Registration time and last heartbeat
- Health status badge
- Close button (X) or click-outside-to-dismiss

Positioned relative to the clicked node, clamped within viewport bounds.

### 4.7 Colour Palette

| Element | Colour | Hex |
|---------|--------|-----|
| Active edge (allowed) | Teal (brand) | `#14B8A6` |
| Active edge (blocked) | Red | `#EF4444` |
| Inactive edge | Slate | `#94A3B8` |
| Node border | Dark (brand) | `#0A0F1C` |
| Node fill | Per-host from palette | See below |
| Cluster hull fill | Same as node, 10% opacity | - |
| Event log: allowed badge | Green | `#06D6A0` |
| Event log: blocked badge | Red | `#EF4444` |

**Host colour palette** (up to 12 hosts, then wraps):
```
#14B8A6  #06D6A0  #0F9690  #6366F1  #8B5CF6  #EC4899
#F59E0B  #10B981  #3B82F6  #F97316  #84CC16  #06B6D4
```

### 4.8 Simulation Script (V12)

**New file:** `scripts/simulate_mesh.py`

A standalone Python script that runs in an infinite loop, exercising all visualiser features by interacting with the real registry via its REST API. The script uses only the existing registry endpoints — no special backdoors. Agents are picked randomly to make it look like a real mesh.

**What it simulates:**

| Action | How | Frequency |
|--------|-----|-----------|
| Add agents | `POST /v1/agents` + DB status bypass to APPROVED | Every 10-20s (random) |
| Register sidecars | `POST /v1/mesh/register` with varying `sidecar_url` hostnames (3-5 simulated hosts) | Immediately after agent creation |
| Send A2A messages (allowed) | `POST /v1/mesh/audit` with `outcome: "allowed"` between random registered agent pairs | Every 2-5s (random) |
| Send A2A messages (blocked) | `POST /v1/mesh/audit` with `outcome: "blocked"` for pairs that violate policies | Every 8-15s (random) |
| Remove agents | `POST /v1/mesh/deregister` + soft-delete agent | Every 30-60s (random) |
| Create/remove policies | `POST /v1/mesh/policies` to block certain agent pairs, then delete later | Every 20-40s (random) |

**Simulated hosts** (for V5 clustering validation):
```
sim-host-alpha.internal    (3-5 agents)
sim-host-beta.internal     (2-4 agents)
sim-host-gamma.internal    (2-3 agents)
sim-host-delta.internal    (1-2 agents)
sim-host-epsilon.internal  (1-2 agents)
```

**Agent naming:** `sim-agent-{noun}-{4-digit-random}` (e.g. `sim-agent-planner-3847`, `sim-agent-analyst-0291`)

**Script behaviour:**
1. Reads credentials from `.env` (same pattern as integration tests)
2. Logs all actions to stdout with timestamps
3. Maintains a pool of currently-active agents (target: 15-30 at steady state)
4. Gradually ramps up from 0 to steady state over the first 60 seconds
5. Runs until interrupted with Ctrl+C; on exit, cleans up all `sim-agent-*` agents and their registrations
6. Accepts CLI flags: `--interval` (base tick interval), `--max-agents` (pool cap), `--hosts` (number of simulated hosts)
7. MEessage flows are random so simulate a real network / setting

**Usage:**
```bash
cd /home/aj/recursant
python scripts/simulate_mesh.py
# or with options:
python scripts/simulate_mesh.py --max-agents 50 --hosts 8 --interval 3
```

---

## 5. API Changes

### 5.1 New Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/mesh` (WebSocket namespace) | WS | JWT (handshake auth) | Bidirectional WebSocket for real-time mesh events |

### 5.2 Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `POST /v1/mesh/register` | Add `socketio.emit('registration', ..., namespace='/mesh')` after commit |
| `POST /v1/mesh/deregister` | Add `socketio.emit('registration', ..., namespace='/mesh')` after commit |
| `POST /v1/mesh/audit` | Add `socketio.emit('audit', ..., namespace='/mesh')` per record after commit |

### 5.3 New Frontend API Client Addition

```javascript
// In frontend/src/api/client.js
export const meshVisualiser = {
  registrations: () => request('/mesh/registrations'),
  audit: (params) => request(`/mesh/audit?${new URLSearchParams(params)}`),
  policies: () => request('/mesh/policies'),
};
```

---

## 6. File Plan

### 6.1 New Files

| File | Purpose |
|------|---------|
| `registry/app/services/mesh_events.py` | Socket.IO instance + MeshNamespace WebSocket handler |
| `registry/app/api/mesh_ws.py` | WebSocket namespace with JWT auth on connect |
| `registry/frontend/src/pages/MeshVisualiser.jsx` | Page component: orchestrates graph + event log |
| `registry/frontend/src/components/MeshGraph.jsx` | D3 force-directed SVG graph |
| `registry/frontend/src/components/EventLog.jsx` | Right-hand interaction log sidebar |
| `registry/frontend/src/components/AgentDetailPopup.jsx` | Click-on-node detail popup |
| `registry/frontend/src/hooks/useSocket.js` | Socket.IO connection hook with auth + auto-reconnect |
| `registry/frontend/src/hooks/useMeshGraph.js` | Graph state management (nodes, edges, activity timers) |
| `scripts/simulate_mesh.py` | Infinite-loop simulation script for validating the visualiser (V12) |

### 6.2 Modified Files

| File | Change |
|------|--------|
| `registry/app/__init__.py` | Initialise `socketio.init_app(app)` in `create_app()` |
| `registry/app/api/mesh.py` | Emit WebSocket events from register/deregister/audit handlers |
| `registry/frontend/src/App.jsx` | Add route: `/mesh-visualiser` -> `<MeshVisualiser />` |
| `registry/frontend/src/components/Sidebar.jsx` | Add nav item: "Mesh Visualiser" with `EyeIcon` |
| `registry/frontend/src/api/client.js` | Add `meshVisualiser` API methods |

### 6.3 New Dependencies

| Package | Where | Purpose | Install |
|---------|-------|---------|---------|
| `flask-socketio` | Backend | WebSocket support for Flask | `pip install flask-socketio` |
| `eventlet` | Backend | Async worker for concurrent WebSocket connections | `pip install eventlet` |
| `d3` | Frontend | Graph rendering, force layout, zoom/pan | `npm install d3` |
| `socket.io-client` | Frontend | Socket.IO client for WebSocket connection | `npm install socket.io-client` |

---

## 7. Implementation Steps

### Step 1: Backend WebSocket Setup
1. Install `flask-socketio` and `eventlet`
2. Create `app/services/mesh_events.py` with the `SocketIO` singleton
3. Create `app/api/mesh_ws.py` with the `MeshNamespace` (JWT auth on connect)
4. Initialise Socket.IO in `create_app()`
5. Add `socketio.emit()` calls to `mesh_register()`, `mesh_deregister()`, `mesh_submit_audit()`
6. Update gunicorn config to use `eventlet` worker class
7. Test with a simple Socket.IO client script that the events flow through

### Step 2: Frontend Routing & Navigation
1. Install `d3` and `socket.io-client` in `frontend/`
2. Create stub `MeshVisualiser.jsx` page
3. Add route in `App.jsx`
4. Add sidebar nav item in `Sidebar.jsx`
5. Add API client methods in `client.js`
6. Verify the page loads with a placeholder

### Step 3: WebSocket Hook + Graph State
1. Implement `useSocket.js` hook with JWT auth handshake
2. Implement `useMeshGraph.js` hook with node/edge state management
3. Wire up initial data load (REST) + live updates (WebSocket) in `MeshVisualiser.jsx`
4. Test that state updates correctly when events arrive

### Step 4: D3 Graph Rendering
1. Build `MeshGraph.jsx` with D3 force simulation
2. Render nodes as SVG circles with labels
3. Render edges as SVG lines (only for observed interactions)
4. Implement host-based clustering (custom force + hull paths)
5. Apply host-based colour palette to nodes and clusters
6. Add zoom/pan via `d3-zoom` with touch support

### Step 5: Edge Animation + Blocked Interactions
1. Implement 5-second activity glow on edges (teal for allowed, red for blocked)
2. Add CSS transitions for smooth colour/width changes
3. Add SVG glow filter for active edges
4. Test with simulated audit events

### Step 6: Agent Detail Popup
1. Build `AgentDetailPopup.jsx` component
2. Wire click handler on nodes to show popup
3. Position popup relative to node, clamped to viewport
4. Display agent metadata from the node data

### Step 7: Event Log Sidebar
1. Build `EventLog.jsx` component
2. Integrate with graph state's event log
3. Style with scrollable list, timestamps, outcome badges
4. Add collapsible toggle for mobile

### Step 8: Simulation Script (V12)
1. Build `scripts/simulate_mesh.py` with agent lifecycle simulation
2. Implement multi-host agent pool with random add/remove
3. Implement allowed and blocked audit event generation
4. Implement policy creation/deletion for blocked interactions
5. Add CLI flags for interval, max-agents, and host count
6. Add cleanup on Ctrl+C (deregister all sim agents)
7. Test that the visualiser graph updates correctly while the script runs

### Step 9: Responsive & iPad Support
1. Test touch interactions (pinch-zoom, drag-pan) on iPad
2. Adjust layout for tablet breakpoints (stack event log below graph on narrow screens)
3. Ensure popup positioning works on touch devices
4. Test with different viewport sizes

### Step 10: Polish & Edge Cases
1. Handle agent deregistration (remove node from graph, keep historical edges dimmed)
2. Handle hundreds of nodes gracefully (performance tuning of force simulation)
3. Add loading state while initial data fetches
4. Add error handling for WebSocket disconnections (Socket.IO auto-reconnects)
5. Run simulation script and validate all requirements V1-V12

---

## 8. Design Decisions & Trade-offs

### WebSocket (Socket.IO) vs SSE

WebSocket is chosen over SSE for three reasons:

1. **Auth:** WebSocket supports JWT during the handshake via Socket.IO's `auth` option. SSE's `EventSource` API doesn't support custom headers, forcing the JWT into query strings — a security anti-pattern (tokens leak via logs, referrer headers, browser history).

2. **Bidirectional:** The visualiser will evolve to support interactive features (deregister agents from the graph, trigger test messages, control the simulation script). WebSocket supports this natively. SSE would require separate REST calls for the return path.

3. **Connection limits:** Browsers limit SSE to ~6 concurrent connections per domain under HTTP/1.1. WebSocket has no such limit.

The trade-off is an additional backend dependency (`flask-socketio` + `eventlet`), but Socket.IO provides auto-reconnection, room management, and namespace isolation that we'd have to build manually with SSE.

### D3 vs Higher-Level React Graph Libraries

D3 gives full control over SVG rendering, which is needed for custom clustering, edge animations, and the specific visual requirements. Higher-level libraries (React Flow, vis-network) would require fighting against their abstractions. The cost is more code for the graph component, but the result is fully tailored to the requirements.

### In-Memory Event Bus vs Message Queue

Socket.IO with `eventlet` handles event fan-out in-process. If the registry scales to multiple gunicorn workers, Socket.IO supports a Redis message queue adapter (`flask-socketio` has built-in Redis support via `message_queue` parameter). The code change is a single line in `SocketIO()` init:

```python
socketio = SocketIO(message_queue='redis://localhost:6379')
```

Since Redis is already in the stack, this is a straightforward upgrade when needed.

### Initial Load + WebSocket vs WebSocket-Only

The page loads initial state via REST (`/mesh/registrations`, `/mesh/audit`) and then subscribes to the WebSocket for live updates. This ensures the graph is populated immediately without waiting for events, and the WebSocket stream only needs to carry incremental updates.

### SVG vs Canvas

SVG is chosen per requirement V10 (vector graphics for zoom). Canvas would give better performance at >1000 nodes but produces blurry output when zoomed. For the target scale (hundreds of agents), SVG with D3 force simulation performs well. If performance becomes an issue, the force simulation can be moved to a web worker.

---

## 9. Gunicorn Configuration

WebSocket requires long-lived connections and an async-capable worker.

**Required change:**
```
gunicorn --worker-class eventlet --workers 1 --timeout 300 app:create_app()
```

Key points:

1. **Worker class:** `eventlet` (required by `flask-socketio` for WebSocket support). This replaces the default sync workers with green threads that handle concurrent WebSocket + HTTP connections efficiently.

2. **Worker count:** Socket.IO with `eventlet` typically uses a single worker. For multi-worker setups, configure the Redis message queue adapter so events are broadcast across workers.

3. **Proxy:** If behind nginx, add WebSocket proxy support:
   ```nginx
   location /socket.io/ {
       proxy_pass http://backend;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
   }
   ```

4. **Vite dev proxy:** Add WebSocket proxy in `vite.config.js` for local development:
   ```javascript
   server: {
     proxy: {
       '/socket.io': { target: 'http://localhost:5000', ws: true }
     }
   }
   ```
