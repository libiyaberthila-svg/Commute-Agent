import os
import re
import math
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.config import settings
from backend.schemas import RAGDocument, RAGQueryResult

# Try to import pypdf for PDF processing
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# Try to import chromadb
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class OfflineHashingEmbeddingFunction:
    """Deterministic local 128-dimensional offline embedding function for ChromaDB."""
    def __init__(self, dim: int = 128):
        self.dim = dim

    def __call__(self, input: List[str]) -> List[List[float]]:
        embeddings = []
        for text in input:
            vec = [0.0] * self.dim
            words = re.findall(r'\b[a-zA-Z0-9_\-]{2,}\b', text.lower())
            for w in words:
                h = abs(hash(w)) % self.dim
                vec[h] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            embeddings.append([round(v / norm, 6) for v in vec])
        return embeddings


class LocalVectorStore:
    """
    Lightweight, fast, 100% offline persistent vector store with TF-IDF/Cosine ranking.
    Used seamlessly alongside or as an offline fallback for ChromaDB.
    """
    def __init__(self, storage_file: Path):
        self.storage_file = storage_file
        self.documents: List[Dict[str, Any]] = []  # List of chunks {id, text, source, metadata}
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self._load()

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r'\b[a-zA-Z0-9_\-]{2,}\b', text.lower())
        return words

    def _build_index(self):
        doc_count = len(self.documents)
        if doc_count == 0:
            return

        df: Dict[str, int] = {}
        for doc in self.documents:
            words = set(self._tokenize(doc["text"]))
            for w in words:
                df[w] = df.get(w, 0) + 1

        self.idf = {w: math.log((doc_count + 1) / (count + 1)) + 1.0 for w, count in df.items()}

    def add_chunks(self, chunks: List[Dict[str, Any]]):
        self.documents.extend(chunks)
        self._build_index()
        self._save()

    def delete_by_source(self, source: str):
        self.documents = [d for d in self.documents if d.get("metadata", {}).get("source") != source]
        self._build_index()
        self._save()

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.documents:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Calculate Query vector
        q_tf: Dict[str, int] = {}
        for t in query_tokens:
            q_tf[t] = q_tf.get(t, 0) + 1

        q_vec: Dict[str, float] = {}
        for t, freq in q_tf.items():
            if t in self.idf:
                q_vec[t] = (1 + math.log(freq)) * self.idf[t]

        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        scores = []
        for doc in self.documents:
            d_tokens = self._tokenize(doc["text"])
            d_tf: Dict[str, int] = {}
            for t in d_tokens:
                d_tf[t] = d_tf.get(t, 0) + 1

            dot_product = 0.0
            d_sq = 0.0
            for t, freq in d_tf.items():
                if t in self.idf:
                    w = (1 + math.log(freq)) * self.idf[t]
                    d_sq += w * w
                    if t in q_vec:
                        dot_product += q_vec[t] * w

            d_norm = math.sqrt(d_sq) or 1.0
            sim = dot_product / (q_norm * d_norm)

            # Boost exact substring matches
            if any(token in doc["text"].lower() for token in query_tokens):
                sim += 0.15

            if sim > 0.05:
                scores.append((sim, doc))

        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, doc in scores[:top_k]:
            results.append({
                "id": doc["id"],
                "text": doc["text"],
                "score": float(round(score, 4)),
                "source": doc.get("metadata", {}).get("source", "Unknown"),
                "metadata": doc.get("metadata", {})
            })
        return results

    def _save(self):
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, indent=2)
        except Exception as e:
            print(f"Error saving vector store: {e}")

    def _load(self):
        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
                self._build_index()
            except Exception as e:
                print(f"Error loading vector store: {e}")
                self.documents = []


class RAGService:
    """
    RAG Service handling document ingestion, chunking, indexing, and grounded retrieval.
    """
    def __init__(self):
        self.kb_dir = Path(settings.knowledge_base_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store_file = self.kb_dir / "rag_index.json"
        self.local_store = LocalVectorStore(self.vector_store_file)
        self.chroma_client = None
        self.chroma_collection = None
        
        # Initialize ChromaDB if available
        if HAS_CHROMADB:
            try:
                self.chroma_client = chromadb.PersistentClient(path=settings.chroma_db_dir)
                self.chroma_collection = self.chroma_client.get_or_create_collection(
                    name="commute_rag",
                    embedding_function=OfflineHashingEmbeddingFunction()
                )
            except Exception as e:
                print(f"ChromaDB initialization failed: {e}. Using local persistent store.")
                self.chroma_client = None

        self._seed_default_knowledge()

    def _seed_default_knowledge(self):
        """Seed sample commute policy and refund rules if empty."""
        policy_file = self.kb_dir / "commute_transit_policy.txt"
        if not policy_file.exists():
            policy_content = (
                "METRO AND RAIL TRANSIT COMMUTE GUIDELINES 2026\n"
                "1. Peak Hours & Fares: Peak hours are 07:00-09:30 and 16:30-19:00 on weekdays.\n"
                "   Express Rail fares include reserved seating in Cars 1 and 2.\n"
                "2. Automatic Booking & Seat Preferences: Auto-booking is authorized for transactions under $50.00.\n"
                "   Window seats and quiet car seats are subject to availability. Quiet cars strictly forbid phone calls.\n"
                "3. Delay Compensation & Re-planning: If a train is delayed by more than 15 minutes, riders are entitled to\n"
                "   a full fare refund or free transfer to parallel metro lines.\n"
                "4. Luggage & Bike Rules: Foldable bikes and small luggage are permitted during peak hours.\n"
                "5. Weather Disruption Policy: In heavy snow or severe rainstorms, bus speeds are reduced by 30%.\n"
                "   Underground Metro Blue Line remains 100% operational during surface weather disruptions.\n"
            )
            with open(policy_file, "w", encoding="utf-8") as f:
                f.write(policy_content)
            self.ingest_file(str(policy_file))

        pass_file = self.kb_dir / "monthly_pass_discounts.md"
        if not pass_file.exists():
            pass_content = (
                "# Commuter Pass and Discount Guide\n\n"
                "- **Monthly Transit Pass**: Provides unlimited rides on Metro Blue Line and City Buses for $95/month.\n"
                "- **Corporate Tax Benefits**: Pre-tax commuter benefits can reduce monthly travel expenses by up to 25%.\n"
                "- **Rideshare Surge Policy**: When rain precipitation exceeds 70%, rideshare pricing increases by 1.3x to 1.8x.\n"
                "- **Seat Reservation Window**: Express Rail bookings open 7 days prior and close 10 minutes before departure.\n"
            )
            with open(pass_file, "w", encoding="utf-8") as f:
                f.write(pass_content)
            self.ingest_file(str(pass_file))

    def _chunk_text(self, text: str, chunk_size: int = 350, overlap: int = 50) -> List[str]:
        # Split by paragraphs or sentences
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_len = 0

        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue
            p_len = len(p_clean)
            if current_len + p_len <= chunk_size:
                current_chunk.append(p_clean)
                current_len += p_len
            else:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                current_chunk = [p_clean]
                current_len = p_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        if not chunks:
            # Fallback simple window
            words = text.split()
            for i in range(0, len(words), chunk_size - overlap):
                chunk = " ".join(words[i:i + chunk_size])
                if chunk:
                    chunks.append(chunk)

        return chunks

    def ingest_file(self, file_path: str) -> Dict[str, Any]:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = p.suffix.lower()
        content = ""

        if ext in (".txt", ".md"):
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        elif ext == ".pdf":
            if not HAS_PYPDF:
                raise ImportError("pypdf is required to read PDF files.")
            reader = pypdf.PdfReader(str(p))
            pages_text = []
            for idx, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages_text.append(f"[Page {idx+1}]\n{text}")
            content = "\n\n".join(pages_text)
        else:
            raise ValueError(f"Unsupported document format: {ext}. Supported formats: .txt, .md, .pdf")

        if not content.strip():
            return {"filename": p.name, "status": "EMPTY", "chunk_count": 0}

        # Clear existing entries for this file to avoid duplicates
        self.local_store.delete_by_source(p.name)

        raw_chunks = self._chunk_text(content)
        chunk_objects = []
        
        for idx, chunk in enumerate(raw_chunks):
            chunk_id = f"{p.stem}_{idx}_{uuid.uuid4().hex[:6]}"
            chunk_objects.append({
                "id": chunk_id,
                "text": chunk,
                "metadata": {
                    "source": p.name,
                    "chunk_index": idx,
                    "file_path": str(p),
                    "timestamp": datetime.now().isoformat()
                }
            })

        self.local_store.add_chunks(chunk_objects)

        # Also add to ChromaDB if available
        if self.chroma_collection:
            try:
                ids = [c["id"] for c in chunk_objects]
                docs = [c["text"] for c in chunk_objects]
                metas = [{"source": c["metadata"]["source"], "chunk_index": c["metadata"]["chunk_index"]} for c in chunk_objects]
                self.chroma_collection.upsert(ids=ids, documents=docs, metadatas=metas)
            except Exception as e:
                print(f"Error upserting to ChromaDB: {e}")

        return {
            "filename": p.name,
            "status": "INGESTED",
            "chunk_count": len(chunk_objects),
            "source_type": ext.lstrip(".")
        }

    def query(self, question: str, top_k: int = 3) -> RAGQueryResult:
        """
        Query the RAG index and return grounded source passages. Never invent facts.
        """
        results = self.local_store.search(question, top_k=top_k)

        if not results:
            return RAGQueryResult(
                query=question,
                answer="No relevant commute policy or guidelines found in indexed documents.",
                sources=[],
                confidence_score=0.0,
                rag_used=False
            )

        sources = []
        excerpts = []
        for r in results:
            sources.append({
                "source": r["source"],
                "score": r["score"],
                "excerpt": r["text"][:280] + ("..." if len(r["text"]) > 280 else "")
            })
            excerpts.append(f"[{r['source']}]: {r['text']}")

        answer = "Relevant Commute Policy Insights:\n" + "\n---\n".join(excerpts)
        confidence = float(min(1.0, results[0]["score"] + 0.3))

        return RAGQueryResult(
            query=question,
            answer=answer,
            sources=sources,
            confidence_score=round(confidence, 2),
            rag_used=True
        )

    def list_documents(self) -> List[RAGDocument]:
        doc_sources: Dict[str, Dict[str, Any]] = {}
        for d in self.local_store.documents:
            src = d.get("metadata", {}).get("source", "Unknown")
            if src not in doc_sources:
                doc_sources[src] = {
                    "filename": src,
                    "source_type": Path(src).suffix.lstrip(".") or "txt",
                    "chunk_count": 0,
                    "created_at": d.get("metadata", {}).get("timestamp", datetime.now().isoformat())
                }
            doc_sources[src]["chunk_count"] += 1

        return [
            RAGDocument(
                id=src,
                filename=info["filename"],
                source_type=info["source_type"],
                chunk_count=info["chunk_count"],
                created_at=info["created_at"]
            )
            for src, info in doc_sources.items()
        ]


rag_service = RAGService()
