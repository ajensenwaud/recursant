"""Authentication interceptor — validates mTLS certs or API keys.

Supports two schemes:
- mTLS: validates client certificate CN/SAN (production)
- API key: validates X-Sidecar-API-Key header (development)
"""

from __future__ import annotations

from runtime.common.models import (
    InterceptorAction,
    InterceptorContext,
    InterceptorDecision,
)
from runtime.sidecar.config import AuthenticationConfig
from runtime.sidecar.interceptors.base import Interceptor


class AuthenticationInterceptor(Interceptor):
    """Validates the identity of calling agents."""

    def __init__(self, config: AuthenticationConfig, local_agent_name: str | None = None):
        self._config = config
        self._local_agent_name = local_agent_name
        self._registered_agents: set[str] | None = None

    def update_registered_agents(self, names: set[str]) -> None:
        """Update the set of known registered agent names.

        When populated, mTLS authentication will verify that the claimed
        client certificate CN matches a registered agent in the mesh.
        """
        self._registered_agents = names

    @property
    def name(self) -> str:
        return "authentication"

    async def process(self, context: InterceptorContext) -> InterceptorDecision:
        if not self._config.enabled:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="authentication disabled",
            )

        # Outbound requests originate from our own agent — the local sidecar
        # already knows the source identity, so there is nothing to authenticate.
        if context.direction and context.direction.value == "outbound":
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.PASS,
                reason="outbound — local agent trusted",
            )

        # Try mTLS first
        if "mtls" in self._config.schemes and context.client_cert_cn:
            return self._authenticate_mtls(context)

        # Fall back to API key
        if "api_key" in self._config.schemes and self._config.api_key:
            return self._authenticate_api_key(context)

        # Fall back to JWT
        if "jwt" in self._config.schemes:
            jwt_token = context.payload.get("_jwt_token")
            if jwt_token:
                return self._authenticate_jwt(context)

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.BLOCK,
            reason="no valid authentication credentials provided",
        )

    def _authenticate_mtls(self, context: InterceptorContext) -> InterceptorDecision:
        """Authenticate via mTLS client certificate."""
        # The cert CN is already extracted by the TLS layer and placed in context.
        # Here we just verify it's present and non-empty.
        if not context.client_cert_cn:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="mTLS client certificate CN is missing",
            )

        # Verify the claimed CN is a registered agent in the mesh
        if self._registered_agents is not None:
            cn = context.client_cert_cn
            is_local = self._local_agent_name and cn == self._local_agent_name
            if not is_local and cn not in self._registered_agents:
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.BLOCK,
                    reason=f"agent not registered in mesh: '{cn}'",
                )

        # Set the source agent name from the cert CN if not already set
        if not context.source_agent_name:
            context.source_agent_name = context.client_cert_cn

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason=f"mTLS authenticated as '{context.client_cert_cn}'",
        )

    def _authenticate_api_key(self, context: InterceptorContext) -> InterceptorDecision:
        """Authenticate via API key (dev mode).

        The API key is expected in the payload metadata under '_api_key'.
        In the real HTTP layer, this comes from the X-Sidecar-API-Key header
        and is injected into the context before the pipeline runs.
        """
        provided_key = context.payload.get("_api_key")
        if not provided_key:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="API key not provided (X-Sidecar-API-Key header missing)",
            )

        if provided_key != self._config.api_key:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="invalid API key",
            )

        # Set source identity for API key clients if not already known
        if not context.source_agent_name:
            context.source_agent_name = "api-key-client"

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason="API key authenticated",
        )

    def _authenticate_jwt(self, context: InterceptorContext) -> InterceptorDecision:
        """Authenticate via JWT bearer token.

        The JWT is expected in the payload metadata under '_jwt_token',
        injected from the Authorization: Bearer header by the HTTP layer.
        """
        try:
            import jwt as pyjwt
        except ImportError:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="JWT authentication unavailable (PyJWT not installed)",
            )

        token = context.payload.get("_jwt_token")
        if not token:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="JWT token not provided",
            )

        # Determine the decoding key
        key = self._config.jwt_secret
        if self._config.jwt_public_key_path:
            try:
                with open(self._config.jwt_public_key_path) as f:
                    key = f.read()
            except (FileNotFoundError, OSError) as e:
                return InterceptorDecision(
                    interceptor=self.name,
                    action=InterceptorAction.BLOCK,
                    reason=f"JWT public key file error: {e}",
                )

        if not key:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="JWT authentication not configured (no secret or public key)",
            )

        # Decode and validate
        decode_options: dict = {}
        kwargs: dict = {
            "algorithms": self._config.jwt_algorithms,
            "options": decode_options,
        }
        if self._config.jwt_issuer:
            kwargs["issuer"] = self._config.jwt_issuer
        if self._config.jwt_audience:
            kwargs["audience"] = self._config.jwt_audience

        try:
            claims = pyjwt.decode(token, key, **kwargs)
        except pyjwt.ExpiredSignatureError:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="JWT token expired",
            )
        except pyjwt.InvalidIssuerError:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="JWT invalid issuer",
            )
        except pyjwt.InvalidAudienceError:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason="JWT invalid audience",
            )
        except pyjwt.PyJWTError as e:
            return InterceptorDecision(
                interceptor=self.name,
                action=InterceptorAction.BLOCK,
                reason=f"JWT validation failed: {e}",
            )

        # Extract agent identity from configured claim
        agent_identity = claims.get(self._config.jwt_agent_claim)
        if not context.source_agent_name and agent_identity:
            context.source_agent_name = str(agent_identity)

        return InterceptorDecision(
            interceptor=self.name,
            action=InterceptorAction.PASS,
            reason=f"JWT authenticated as '{agent_identity}'",
        )
