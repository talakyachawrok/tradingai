"""Ephemeral in-memory session store (no permanent database storage)."""

import copy
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


class DocumentStore:
    """In-memory ephemeral store for temporary runtime state during personal sessions."""

    def __init__(self) -> None:
        self.backend_type: str = "in_memory_ephemeral"
        self.connected: bool = True
        self.status_message: str = (
            "Ephemeral in-memory processing active (no permanent database configured)."
        )
        # collection -> {doc_id: (created_at_iso, payload_dict)}
        self._collections: Dict[str, Dict[str, Tuple[str, Dict[str, Any]]]] = defaultdict(dict)

    async def initialize(self) -> None:
        self.backend_type = "in_memory_ephemeral"
        self.connected = True
        self.status_message = (
            "Ephemeral in-memory processing active (no permanent database configured)."
        )

    async def close(self) -> None:
        return None

    def reset(self) -> None:
        """Clear all temporary in-memory collections (used between isolated tests)."""
        self._collections.clear()

    async def upsert(
        self, collection: str, doc_id: str, document: Dict[str, Any], created_at: str
    ) -> None:
        self._collections[collection][doc_id] = (created_at, copy.deepcopy(document))

    async def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        item = self._collections.get(collection, {}).get(doc_id)
        return copy.deepcopy(item[1]) if item else None

    async def list_all(self, collection: str, limit: int = 200) -> List[Dict[str, Any]]:
        bucket = self._collections.get(collection, {})
        ordered = sorted(bucket.values(), key=lambda pair: pair[0], reverse=True)
        return [copy.deepcopy(doc) for _, doc in ordered[:limit]]

    async def delete(self, collection: str, doc_id: str) -> bool:
        bucket = self._collections.get(collection, {})
        return bucket.pop(doc_id, None) is not None


db_store = DocumentStore()
