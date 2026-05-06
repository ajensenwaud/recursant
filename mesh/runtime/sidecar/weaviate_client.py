"""Lightweight async Weaviate client for sidecar guardrail evaluation.

Uses httpx to call Weaviate REST API directly (avoids heavy weaviate-client
dependency in the sidecar). Queries nearText against the GuardrailReference
collection filtered by guardrail_id.
"""

from __future__ import annotations

from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()


class SidecarWeaviateClient:
    """Async Weaviate client for similarity queries."""

    def __init__(self, url: str = "http://weaviate:8080", timeout_ms: int = 2000):
        self._url = url.rstrip('/')
        self._timeout = timeout_ms / 1000.0

    async def query_near_text(
        self,
        collection: str,
        text: str,
        guardrail_id: str,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> list[dict]:
        """Search for similar reference texts via Weaviate GraphQL API.

        Args:
            collection: Weaviate collection name (e.g. "GuardrailReference").
            text: The text to search for similarity.
            guardrail_id: Filter to only this guardrail's references.
            limit: Max results.
            threshold: Minimum similarity (1 - distance) to include.

        Returns:
            List of {text, category, action, similarity} dicts, or empty on error.
        """
        query = """
        {
            Get {
                %s(
                    nearText: {concepts: [%s]}
                    limit: %d
                    where: {
                        path: ["guardrail_id"]
                        operator: Equal
                        valueText: %s
                    }
                ) {
                    text
                    category
                    action
                    guardrail_id
                    _additional {
                        distance
                    }
                }
            }
        }
        """ % (
            collection,
            _gql_string(text),
            limit,
            _gql_string(guardrail_id),
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._url}/v1/graphql",
                    json={"query": query},
                )
                resp.raise_for_status()
                data = resp.json()

            results = (
                data.get("data", {})
                .get("Get", {})
                .get(collection, [])
            )

            matches = []
            for obj in results:
                distance = (
                    obj.get("_additional", {}).get("distance", 1.0)
                )
                similarity = 1.0 - float(distance)
                if similarity >= threshold:
                    matches.append({
                        "text": obj.get("text", ""),
                        "category": obj.get("category", ""),
                        "action": obj.get("action", "block"),
                        "similarity": round(similarity, 4),
                    })

            return matches

        except httpx.ConnectError:
            logger.warning("weaviate_unreachable", url=self._url)
            return []
        except httpx.TimeoutException:
            logger.warning("weaviate_timeout", url=self._url)
            return []
        except Exception as e:
            logger.warning("weaviate_query_error", error=str(e))
            return []


def _gql_string(value: str) -> str:
    """Escape a string for GraphQL query embedding."""
    escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    return f'"{escaped}"'
