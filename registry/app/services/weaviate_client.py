"""Weaviate client for managing guardrail reference vectors.

Used by the registry to CRUD reference texts for vector_lookup guardrails.
Sidecars query Weaviate directly for low-latency similarity checks.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

WEAVIATE_URL = os.environ.get('WEAVIATE_URL', 'http://recursant-weaviate:8080')
COLLECTION_NAME = 'GuardrailReference'


class WeaviateClient:
    """Client for managing guardrail reference vectors in Weaviate."""

    def __init__(self, url: Optional[str] = None):
        self.url = url or WEAVIATE_URL
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import weaviate
            self._client = weaviate.connect_to_custom(
                http_host=self._parse_host(self.url),
                http_port=self._parse_port(self.url),
                http_secure=self.url.startswith('https'),
                grpc_host=self._parse_host(self.url),
                grpc_port=50051,
                grpc_secure=False,
            )
            return self._client
        except Exception as e:
            logger.warning("weaviate_connection_failed: %s", e)
            return None

    def _parse_host(self, url: str) -> str:
        return url.split('://')[1].split(':')[0].split('/')[0]

    def _parse_port(self, url: str) -> int:
        try:
            return int(url.split('://')[1].split(':')[1].split('/')[0])
        except (IndexError, ValueError):
            return 443 if url.startswith('https') else 80

    def ensure_collection(self):
        """Create the GuardrailReference collection if it doesn't exist."""
        client = self._get_client()
        if client is None:
            logger.warning("weaviate_unavailable_skip_collection_creation")
            return False
        try:
            if client.collections.exists(COLLECTION_NAME):
                return True
            import weaviate.classes.config as wvc
            client.collections.create(
                name=COLLECTION_NAME,
                properties=[
                    wvc.Property(name="guardrail_id", data_type=wvc.DataType.TEXT, skip_vectorization=True),
                    wvc.Property(name="text", data_type=wvc.DataType.TEXT),
                    wvc.Property(name="category", data_type=wvc.DataType.TEXT, skip_vectorization=True),
                    wvc.Property(name="action", data_type=wvc.DataType.TEXT, skip_vectorization=True),
                    wvc.Property(name="tenant_id", data_type=wvc.DataType.TEXT, skip_vectorization=True),
                ],
                vectorizer_config=wvc.Configure.Vectorizer.text2vec_transformers(),
            )
            logger.info("weaviate_collection_created: %s", COLLECTION_NAME)
            return True
        except Exception as e:
            logger.warning("weaviate_collection_creation_failed: %s", e)
            return False

    def upsert_references(self, guardrail_id: str, references: list[dict], tenant_id: str = 'default'):
        """Insert/replace reference texts for a guardrail.

        Args:
            guardrail_id: UUID string of the guardrail.
            references: List of {text, category, action} dicts.
            tenant_id: Tenant isolation.
        """
        client = self._get_client()
        if client is None:
            logger.warning("weaviate_unavailable_skip_upsert")
            return

        try:
            # Delete existing references for this guardrail first
            self.delete_references(guardrail_id, tenant_id)

            collection = client.collections.get(COLLECTION_NAME)
            objects = []
            for ref in references:
                objects.append({
                    "guardrail_id": str(guardrail_id),
                    "text": ref.get("text", ""),
                    "category": ref.get("category", ""),
                    "action": ref.get("action", "block"),
                    "tenant_id": tenant_id,
                })

            if objects:
                collection.data.insert_many(objects)
                logger.info(
                    "weaviate_references_upserted: guardrail=%s count=%d",
                    guardrail_id, len(objects),
                )
        except Exception as e:
            logger.warning("weaviate_upsert_failed: %s", e)

    def delete_references(self, guardrail_id: str, tenant_id: str = 'default'):
        """Delete all reference vectors for a guardrail."""
        client = self._get_client()
        if client is None:
            logger.warning("weaviate_unavailable_skip_delete")
            return

        try:
            from weaviate.classes.query import Filter
            collection = client.collections.get(COLLECTION_NAME)
            collection.data.delete_many(
                where=Filter.by_property("guardrail_id").equal(str(guardrail_id))
            )
            logger.info("weaviate_references_deleted: guardrail=%s", guardrail_id)
        except Exception as e:
            logger.warning("weaviate_delete_failed: %s", e)

    def query_similar(
        self,
        text: str,
        guardrail_id: str,
        threshold: float = 0.7,
        limit: int = 5,
        tenant_id: str = 'default',
    ) -> list[dict]:
        """Search for similar reference texts.

        Returns list of {text, category, action, similarity} dicts.
        """
        client = self._get_client()
        if client is None:
            logger.warning("weaviate_unavailable_skip_query")
            return []

        try:
            import weaviate.classes.query as wvq
            from weaviate.classes.query import Filter, MetadataQuery
            collection = client.collections.get(COLLECTION_NAME)
            results = collection.query.near_text(
                query=text,
                limit=limit,
                filters=Filter.by_property("guardrail_id").equal(str(guardrail_id)),
                return_metadata=MetadataQuery(distance=True),
            )
            matches = []
            for obj in results.objects:
                similarity = 1.0 - (obj.metadata.distance or 0.0)
                if similarity >= threshold:
                    matches.append({
                        "text": obj.properties.get("text", ""),
                        "category": obj.properties.get("category", ""),
                        "action": obj.properties.get("action", "block"),
                        "similarity": round(similarity, 4),
                    })
            return matches
        except Exception as e:
            logger.warning("weaviate_query_failed: %s", e)
            return []

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
