import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "rosie-inventory")

def _get_client():
    from opensearchpy import OpenSearch
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=False,
    )

def index_resources(resources: list[dict]) -> int:
    client = _get_client()
    if not client.indices.exists(index=OPENSEARCH_INDEX):
        client.indices.create(
            index=OPENSEARCH_INDEX,
            body={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {
                    "properties": {
                        "resource_id": {"type": "keyword"},
                        "resource_type": {"type": "keyword"},
                        "name": {"type": "text"},
                        "region": {"type": "keyword"},
                        "account_id": {"type": "keyword"},
                        "details_text": {"type": "text"},
                        "tags_text": {"type": "text"},
                        "collected_at": {"type": "date"},
                    }
                },
            },
        )
    indexed = 0
    for r in resources:
        doc = {
            **r,
            "details_text": json.dumps(r.get("details", {})),
            "tags_text": json.dumps(r.get("tags", {})),
        }
        client.index(index=OPENSEARCH_INDEX, id=r["resource_id"], body=doc)
        indexed += 1
    return indexed

def search(query: str, size: int = 10) -> list[dict]:
    client = _get_client()
    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["name", "resource_type", "details_text", "tags_text"],
                "type": "best_fields",
            }
        },
        "size": size,
    }
    try:
        resp = client.search(index=OPENSEARCH_INDEX, body=body)
        return [hit["_source"] for hit in resp["hits"]["hits"]]
    except Exception as e:
        logger.warning(f"OpenSearch search failed: {e}")
        return []
