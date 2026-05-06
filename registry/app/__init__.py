from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS

from config import config

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name=None):
    """Application factory for creating Flask app instances."""
    if config_name is None:
        import os
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Multi-cluster: set CLUSTER_ID (used by mesh endpoints)
    import os
    app.config['CLUSTER_ID'] = os.environ.get('CLUSTER_ID', 'default')
    app.config['REMOTE_REGISTRY_URL'] = os.environ.get('REMOTE_REGISTRY_URL', '')

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    # Initialize Socket.IO for mesh visualiser
    from app.services.mesh_events import MeshNamespace, socketio
    if app.config.get('TESTING'):
        # Disable Redis message queue for test client compatibility
        socketio.server_options.pop('client_manager', None)
        socketio.server_options.pop('message_queue', None)
        socketio.init_app(app, message_queue=None, async_mode='threading')
    else:
        socketio.init_app(app)
    socketio.on_namespace(MeshNamespace('/mesh'))

    # Register blueprints
    from app.api import api_bp
    from app.api.auth import auth_bp
    app.register_blueprint(api_bp, url_prefix='/v1')
    app.register_blueprint(auth_bp, url_prefix='/v1')

    # Health check endpoint
    @app.route('/health')
    def health():
        return {'status': 'healthy'}

    # Start adversarial test scheduler (skip in testing mode)
    if not app.config.get('TESTING'):
        from app.services.adversarial_scheduler import AdversarialScheduler
        scheduler = AdversarialScheduler(app)
        scheduler.start()
        app.extensions['adversarial_scheduler'] = scheduler

    # Start cross-cluster event bridge if multi-cluster is configured
    if app.config.get('CLUSTER_ID', 'default') != 'default' and app.config.get('REMOTE_REGISTRY_URL'):
        from app.services.event_bridge import EventBridge
        bridge = EventBridge(
            remote_registry_url=app.config['REMOTE_REGISTRY_URL'],
            mesh_api_key=app.config.get('MESH_API_KEY'),
            socketio=socketio,
            local_cluster_id=app.config['CLUSTER_ID'],
        )
        bridge.start()
        app.extensions['event_bridge'] = bridge

    return app
