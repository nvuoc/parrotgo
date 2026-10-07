"""Persistent retrieval of approved, sourced FAQ answers."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, cast

from src.config import settings
from src.core.state import QAResponse
from src.services.embedding_adapter import EmbeddingAdapter

FALLBACK_EMPTY_KB: QAResponse = {
    "category": "static_faq",
    "success": False,
    "answer_text": "Dạ hiện tại em chưa có thông tin đã xác nhận về quy định này ạ.",
    "source": "empty_kb",
    "metadata": {"reason": "no_approved_data"},
}

FALLBACK_NO_MATCH: QAResponse = {
    "category": "static_faq",
    "success": False,
    "answer_text": "Dạ hiện tại em chưa có thông tin đã xác nhận về quy định này ạ.",
    "source": "faq_not_found",
    "metadata": {"reason": "low_confidence"},
}

VEHICLE_TYPES = {"all", "xe_may", "oto_4_cho", "oto_7_cho"}


def _search_key(text: str) -> str:
    plain = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", plain))


class ChromaFAQClient:
    """Use the same embedding model for writes and reads, with conservative answers."""

    def __init__(
        self,
        data_dir: str | None = None,
        collection_name: str = "parrotgo_faq",
        embedding: EmbeddingAdapter | None = None,
    ):
        self.data_dir = data_dir or settings.CHROMA_DATA_DIR
        self.collection_name = collection_name
        self.embedding = embedding or EmbeddingAdapter()
        self._client: Any = None
        self._collection: Any = None

    def _get_client(self):
        if self._client is None:
            import chromadb

            storage_path = Path(self.data_dir)
            storage_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(storage_path))
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            manifest = self.embedding.get_manifest()
            collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=None,
                metadata={**manifest, "hnsw:space": "cosine"},
            )
            stored_metadata = dict(collection.metadata or {})
            for key in ("embedding_provider", "embedding_model", "embedding_dimensions", "embedding_metric"):
                if key in stored_metadata and stored_metadata[key] != manifest[key]:
                    raise ValueError("FAQ collection uses another embedding model; choose a new collection")
            if collection.count():
                sample = collection.get(limit=1, include=["embeddings"])
                vectors = sample.get("embeddings")
                if vectors is not None and len(vectors) and len(vectors[0]) != self.embedding.dimensions:
                    raise ValueError("FAQ collection dimensions do not match the embedding manifest")
            if any(stored_metadata.get(key) != value for key, value in manifest.items()):
                metadata_to_keep = {key: value for key, value in stored_metadata.items() if not key.startswith("hnsw:")}
                collection.modify(metadata={**metadata_to_keep, **manifest})
            self._collection = collection
        return self._collection

    def count(self) -> int:
        if not settings.RAG_ENABLED:
            return 0
        try:
            return self._get_collection().count()
        except Exception:  # noqa: BLE001 - optional storage count must remain safe
            return 0

    def validate_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Reject untyped approval flags and missing sources before indexing."""
        if not isinstance(chunks, list):
            raise TypeError("Chunks must be a list")
        seen_ids = set()
        for chunk in chunks:
            if not isinstance(chunk, dict):
                raise TypeError("Each FAQ chunk must be an object")
            chunk_id = chunk.get("id")
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ValueError("FAQ chunk requires a non-empty ID")
            if chunk_id in seen_ids:
                raise ValueError(f"Duplicate chunk ID in batch: {chunk_id}")
            seen_ids.add(chunk_id)
            document = chunk.get("document")
            if not isinstance(document, str) or not document.strip():
                raise ValueError(f"Chunk {chunk_id} missing document text")
            metadata = chunk.get("metadata")
            if not isinstance(metadata, dict):
                raise TypeError(f"Chunk {chunk_id} missing metadata dict")
            if not isinstance(metadata.get("canonical_answer"), str) or not metadata["canonical_answer"].strip():
                raise ValueError(f"Chunk {chunk_id} missing canonical_answer")
            if not isinstance(metadata.get("approved"), bool):
                raise TypeError(f"Chunk {chunk_id} approved must be a boolean")
            if metadata.get("vehicle_type", "all") not in VEHICLE_TYPES:
                raise ValueError(f"Chunk {chunk_id} has unsupported vehicle_type")
            if metadata["approved"] and (
                not isinstance(metadata.get("source"), str) or not metadata["source"].strip()
                or not isinstance(metadata.get("version"), str) or not metadata["version"].strip()
            ):
                raise ValueError(f"Approved chunk {chunk_id} requires source and version")
            for field in ("questions", "keywords", "excluded_keywords"):
                entries = chunk.get(field, [])
                if not isinstance(entries, list) or any(
                    not isinstance(entry, str) or not entry.strip() for entry in entries
                ):
                    raise ValueError(f"Chunk {chunk_id} {field} must be a list of non-empty text")

    def upsert_faq_policies(self, chunks: list[dict[str, Any]]) -> int:
        """Index each approved question variant without discarding existing FAQ records."""
        self.validate_chunks(chunks)
        if not chunks:
            return 0
        collection = self._get_collection()
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for chunk in chunks:
            metadata: dict[str, Any] = {
                key: value if isinstance(value, (str, int, float, bool)) else json.dumps(value, ensure_ascii=False)
                for key, value in chunk["metadata"].items()
            }
            metadata["vehicle_type"] = metadata.get("vehicle_type") or "all"
            metadata["faq_id"] = chunk["id"]
            metadata["keywords"] = json.dumps(chunk.get("keywords", []), ensure_ascii=False)
            metadata["excluded_keywords"] = json.dumps(chunk.get("excluded_keywords", []), ensure_ascii=False)
            metadata["question"] = chunk["document"]
            seen_questions = set()
            for index, question in enumerate([chunk["document"], *chunk.get("questions", [])]):
                key = _search_key(question)
                if key in seen_questions:
                    continue
                seen_questions.add(key)
                suffix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
                record_id = chunk["id"] if index == 0 else f"{chunk['id']}::q:{suffix}"
                ids.append(record_id)
                documents.append(question)
                metadatas.append(dict(metadata))
        vectors = self.embedding.embed_texts(documents)
        collection.upsert(ids=ids, documents=documents, embeddings=vectors, metadatas=metadatas)
        # Replacing or revoking a FAQ also revokes obsolete question variants.
        previous = collection.get(
            where={"faq_id": {"$in": [chunk["id"] for chunk in chunks]}},
            include=["metadatas"],
        )
        active_ids = set(ids)
        stale_ids: list[str] = []
        stale_metadata: list[dict[str, Any]] = []
        for record_id, metadata in zip(previous["ids"], previous["metadatas"]):
            if record_id not in active_ids:
                stale_ids.append(record_id)
                stale_metadata.append({**dict(metadata or {}), "approved": False})
        if stale_ids:
            collection.update(ids=stale_ids, metadatas=stale_metadata)
        return len(chunks)

    def delete_faq_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        collection = self._get_collection()
        variants = collection.get(where={"faq_id": {"$in": ids}}, include=[])
        collection.delete(ids=list(set(ids + variants["ids"])))

    @staticmethod
    def _matches_topic(query: str, metadata: dict[str, Any]) -> bool:
        keywords = json.loads(str(metadata.get("keywords") or "[]"))
        normalized = f" {_search_key(query)} "
        excluded = json.loads(str(metadata.get("excluded_keywords") or "[]"))
        # Single Vietnamese words must retain accents: chó and chỗ are different topics.
        verbatim = " " + " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFC", query.lower()))) + " "
        for keyword in excluded:
            accented_key = " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFC", keyword.lower())))
            search_key = _search_key(keyword)
            if f" {accented_key} " in verbatim or (
                len(search_key.split()) > 1 and f" {search_key} " in normalized
            ):
                return False
        return not keywords or any(f" {_search_key(keyword)} " in normalized for keyword in keywords)

    def search_faq_policy(
        self,
        query: str,
        vehicle_type: str | None = None,
        high_threshold: float = 0.82,
        low_threshold: float = 0.65,
    ) -> QAResponse:
        """Return a sourced answer only for an approved, relevant, confident match."""
        if not settings.RAG_ENABLED:
            return cast(QAResponse, dict(FALLBACK_EMPTY_KB))
        if not isinstance(query, str) or not query.strip():
            return cast(QAResponse, dict(FALLBACK_NO_MATCH))
        if vehicle_type is not None and vehicle_type not in VEHICLE_TYPES - {"all"}:
            return cast(QAResponse, dict(FALLBACK_NO_MATCH))
        try:
            collection = self._get_collection()
            if collection.count() == 0:
                return cast(QAResponse, dict(FALLBACK_EMPTY_KB))
            applicable = ["all", vehicle_type] if vehicle_type else ["all"]
            where = {"$and": [{"approved": True}, {"vehicle_type": {"$in": applicable}}]}
            results = collection.query(
                query_embeddings=self.embedding.embed_texts([query]),
                n_results=min(12, collection.count()),
                where=where,
                include=["distances", "metadatas"],
            )
            records = zip(
                (results.get("ids") or [[]])[0],
                (results.get("distances") or [[]])[0],
                (results.get("metadatas") or [[]])[0],
            )
            candidates = []
            seen_faqs = set()
            for record_id, distance, metadata_value in records:
                metadata = dict(metadata_value or {})
                faq_id = metadata.get("faq_id") or record_id
                if faq_id in seen_faqs or not self._matches_topic(query, metadata):
                    continue
                seen_faqs.add(faq_id)
                candidates.append((str(faq_id), 1.0 - float(distance), metadata))
            if not candidates:
                return cast(QAResponse, dict(FALLBACK_NO_MATCH))
            faq_id, score, metadata = candidates[0]
            detail = {"chunk_id": faq_id, "score": round(score, 4), "version": str(metadata.get("version", ""))}
            ambiguous = len(candidates) > 1 and candidates[1][1] >= high_threshold and score - candidates[1][1] < 0.03
            if score >= high_threshold and not ambiguous:
                return {
                    "category": "static_faq",
                    "success": True,
                    "answer_text": str(metadata["canonical_answer"]),
                    "source": str(metadata["source"]),
                    "metadata": detail,
                }
            if score >= low_threshold:
                return {
                    "category": "static_faq",
                    "success": False,
                    "answer_text": "Dạ em chưa có đủ thông tin đã xác nhận để trả lời quy định này ạ.",
                    "source": "faq_needs_clarification",
                    "metadata": {**detail, "reason": "ambiguous" if ambiguous else "moderate_confidence"},
                }
            return cast(QAResponse, dict(FALLBACK_NO_MATCH))
        except Exception as error:  # noqa: BLE001 - isolate optional model/storage failures
            return {
                "category": "static_faq",
                "success": False,
                "answer_text": FALLBACK_NO_MATCH["answer_text"],
                "source": "chroma_error",
                "metadata": {"error_type": type(error).__name__},
            }


chroma_faq_client = ChromaFAQClient()
