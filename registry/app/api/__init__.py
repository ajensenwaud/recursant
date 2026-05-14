from flask import Blueprint

api_bp = Blueprint('api', __name__)

from app.api import agents  # noqa: E402, F401
from app.api import security  # noqa: E402, F401
from app.api import evaluation  # noqa: E402, F401
from app.api import dashboard  # noqa: E402, F401
from app.api import approval  # noqa: E402, F401
from app.api import users  # noqa: E402, F401
from app.api import audit  # noqa: E402, F401
from app.api import mesh  # noqa: E402, F401
from app.api import consent  # noqa: E402, F401
from app.api import certificates  # noqa: E402, F401
from app.api import guardrails  # noqa: E402, F401
from app.api import guardrail_metrics  # noqa: E402, F401
from app.api import webhooks  # noqa: E402, F401
from app.api import guardrail_configs  # noqa: E402, F401
from app.api import governance  # noqa: E402, F401
from app.api import adversarial  # noqa: E402, F401
from app.api import observability  # noqa: E402, F401
from app.api import euai_compliance  # noqa: E402, F401
from app.api import discovery  # noqa: E402, F401
from app.api import openclaw  # noqa: E402, F401
