"""Database connection management supporting MongoDB with SQLite document fallback."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.config import get_settings

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:  # pragma: no cover - optional runtime fallback
    AsyncIOMotorClient = None  # type: ignore


class DocumentStore:
    """Unified async document store abstraction over MongoDB or local SQLite."""

    def __init__(self) -> None:
        self.backend_type: str = "sqlite_local"
        self.connected: bool = False
        self.status_message: str = "Not initialized"
        self._mongo_client: Any = None
        self._mongo_db: Any = None
        self._sqlite_path: Optional[Path] = None

    async def initialize(self) -> None:
        settings = get_settings()
        if settings.mongodb_uri.strip() and AsyncIOMotorClient is not None:
            try:
                client = AsyncIOMotorClient(
                    settings.mongodb_uri.strip(), serverSelectionTimeoutMS=2500
                )
                await client.admin.command("ping")
                self._mongo_client = client
                self._mongo_db = client[settings.mongodb_db_name]
                self.backend_type = "mongodb"
                self.connected = True
                self.status_message = f"Connected to MongoDB ({settings.mongodb_db_name})"
                return
            except Exception as exc:
                self.status_message = f"MongoDB unreachable ({exc}); using local SQLite store"

        db_path = Path(settings.local_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_path = db_path
        with sqlite3.connect(self._sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    collection TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (collection, doc_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_collection_created ON documents (collection, created_at DESC)"
            )
            conn.commit()
        self.backend_type = "sqlite_local"
        self.connected = True
        if not settings.mongodb_uri.strip():
            self.status_message = f"Local SQLite document store active ({db_path.name}); configure MONGODB_URI for MongoDB"

    async def close(self) -> None:
        if self._mongo_client is not None:
            self._mongo_client.close()
            self._mongo_client = None
            self._mongo_db = None

    async def upsert(self, collection: str, doc_id: str, document: Dict[str, Any], created_at: str) -> None:
        if self.backend_type == "mongodb" and self._mongo_db is not None:
            payload = dict(document)
            payload["_id"] = doc_id
            await self._mongo_db[collection].replace_one({"_id": doc_id}, payload, upsert=True)
            return

        if self._sqlite_path is None:
            await self.initialize()
        assert self._sqlite_path is not None
        serialized = json.dumps(document, default=str)
        with sqlite3.connect(self._sqlite_path) as conn:
            conn.execute(
                """
                INSERT INTO documents (collection, doc_id, created_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(collection, doc_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    payload = excluded.payload
                """,
                (collection, doc_id, created_at, serialized),
            )
            conn.commit()

    async def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        if self.backend_type == "mongodb" and self._mongo_db is not None:
            doc = await self._mongo_db[collection].find_one({"_id": doc_id})
            if doc:
                doc.pop("_id", None)
            return doc

        if self._sqlite_path is None:
            await self.initialize()
        assert self._sqlite_path is not None
        with sqlite3.connect(self._sqlite_path) as conn:
            cur = conn.execute(
                "SELECT payload FROM documents WHERE collection = ? AND doc_id = ?",
                (collection, doc_id),
            )
            row = cur.fetchone()
            return json.loads(row[0]) if row else None

    async def list_all(self, collection: str, limit: int = 200) -> List[Dict[str, Any]]:
        if self.backend_type == "mongodb" and self._mongo_db is not None:
            cursor = self._mongo_db[collection].find().sort("created_at", -1).limit(limit)
            results: List[Dict[str, Any]] = []
            async for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)
            return results

        if self._sqlite_path is None:
            await self.initialize()
        assert self._sqlite_path is not None
        with sqlite3.connect(self._sqlite_path) as conn:
            cur = conn.execute(
                "SELECT payload FROM documents WHERE collection = ? ORDER BY created_at DESC LIMIT ?",
                (collection, limit),
            )
            return [json.loads(row[0]) for row in cur.fetchall()]

    async def delete(self, collection: str, doc_id: str) -> bool:
        if self.backend_type == "mongodb" and self._mongo_db is not None:
            res = await self._mongo_db[collection].delete_one({"_id": doc_id})
            return res.deleted_count > 0

        if self._sqlite_path is None:
            await self.initialize()
        assert self._sqlite_path is not None
        with sqlite3.connect(self._sqlite_path) as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE collection = ? AND doc_id = ?",
                (collection, doc_id),
            )
            conn.commit()
            return cur.rowcount > 0


db_store = DocumentStore()
