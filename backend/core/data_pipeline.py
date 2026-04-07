import asyncio
import json
import time
import hashlib
from typing import AsyncGenerator
import chromadb
from openai import OpenAI

oai    = OpenAI()
from .config import CHROMA_DIR
chroma = chromadb.PersistentClient(path=CHROMA_DIR)

trace_collection   = chroma.get_or_create_collection("production_traces")
failure_collection = chroma.get_or_create_collection("eval_failures")
insight_collection = chroma.get_or_create_collection("eval_insights")


class TracePipeline:

    CHUNK_SIZE     = 300   
    OVERLAP_WORDS  = 30    
    EMBED_BATCH    = 50    

    async def process_span(self, span: dict):
        if not span.get("input") or not span.get("output"):
            return

        
        span_text = self._format_span_for_embedding(span)

        chunks = self._chunk(span_text)

        embeddings = await self._embed_batch(chunks)

        self._store_chunks(chunks, embeddings, span)

    def _format_span_for_embedding(self, span: dict) -> str:
        parts = []

        parts.append(f"Operation: {span.get('name', 'unknown')}")

        inp = span.get("input", "")
        if len(inp) > 500:
            inp = inp[:500] + "..."
        parts.append(f"User input: {inp}")

        out = span.get("output", "")
        if len(out) > 300:
            out = out[:300] + "..."
        parts.append(f"AI output: {out}")

        if span.get("judge_score") is not None:
            score = span["judge_score"]
            quality = "excellent" if score >= 9 else \
                      "good"      if score >= 7 else \
                      "poor"      if score >= 4 else "failing"
            parts.append(f"Quality: {quality} (score: {score:.1f})")

        if span.get("error"):
            parts.append(f"Error occurred: {span['error'][:100]}")

        return "\n".join(parts)

    def _chunk(self, text: str) -> list[str]:
        words  = text.split()
        if len(words) <= self.CHUNK_SIZE:
            return [text]

        chunks = []
        for i in range(0, len(words), self.CHUNK_SIZE - self.OVERLAP_WORDS):
            chunk = " ".join(words[i:i + self.CHUNK_SIZE])
            if chunk:
                chunks.append(chunk)
        return chunks

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        loop     = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: oai.embeddings.create(
                model="text-embedding-3-small",
                input=[t[:8000] for t in texts]
            )
        )
        return [item.embedding for item in response.data]

    def _store_chunks(self, chunks: list[str], embeddings: list[list[float]],
                      span: dict):
        ids, docs, metas = [], [], []

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = hashlib.md5(
                f"{span.get('span_id','')}{i}".encode()
            ).hexdigest()

            ids.append(chunk_id)
            docs.append(chunk)
            metas.append({
                "span_id":    span.get("span_id", ""),
                "trace_id":   span.get("trace_id", ""),
                "project_id": span.get("project_id", ""),
                "name":       span.get("name", ""),
                "score":      float(span.get("judge_score") or -1),
                "is_failure": (span.get("judge_score") or 10) < 6,
                "has_error":  bool(span.get("error")),
                "timestamp":  float(span.get("timestamp") or time.time()),
                "chunk_idx":  i,
                "input_preview": span.get("input","")[:100]
            })

        trace_collection.upsert(
            ids        = ids,
            embeddings = embeddings,
            documents  = docs,
            metadatas  = metas
        )

    async def semantic_search(
        self,
        query:      str,
        project_id: str,
        k:          int = 10,
        only_failures: bool = False
    ) -> list[dict]:
        embeddings = await self._embed_batch([query])
        query_emb  = embeddings[0]

        where = {"project_id": project_id}
        if only_failures:
            where["is_failure"] = True

        results = trace_collection.query(
            query_embeddings = [query_emb],
            n_results        = min(k, max(1, trace_collection.count())),
            where            = where if project_id else {},
            include          = ["documents", "metadatas", "distances"]
        )

        chunks = []
        if results["documents"] and results["documents"][0]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            ):
                chunks.append({
                    "text":        doc,
                    "similarity":  round(1 - dist, 3),
                    "score":       meta.get("score", -1),
                    "is_failure":  meta.get("is_failure", False),
                    "name":        meta.get("name", ""),
                    "timestamp":   meta.get("timestamp", 0),
                    "input":       meta.get("input_preview", "")
                })

        return sorted(chunks, key=lambda x: -x["similarity"])


class DocumentPipeline:

    async def ingest(self, file_path: str, project_id: str,
                     doc_type: str = "runbook") -> dict:

        text   = self._load(file_path)
        source = file_path.split("/")[-1]
        print(f"  Loaded {source}: {len(text)} chars")

        chunks = self._paragraph_chunk(text, max_words=400, overlap=50)
        print(f"  Chunked into {len(chunks)} pieces")

        all_embeddings = []
        batch_size     = 50
        for i in range(0, len(chunks), batch_size):
            batch      = chunks[i:i+batch_size]
            response   = oai.embeddings.create(
                model="text-embedding-3-small",
                input=[c[:8000] for c in batch]
            )
            all_embeddings.extend([e.embedding for e in response.data])
        print(f"  Embedded {len(all_embeddings)} chunks")

        doc_collection = chroma.get_or_create_collection(f"docs_{project_id}")
        ids, docs, metas = [], [], []
        for i, (chunk, emb) in enumerate(zip(chunks, all_embeddings)):
            ids.append(f"{source}_{i}")
            docs.append(chunk)
            metas.append({
                "source":     source,
                "doc_type":   doc_type,
                "chunk_idx":  i,
                "total":      len(chunks),
                "project_id": project_id,
                "timestamp":  time.time()
            })

        doc_collection.upsert(ids=ids, embeddings=all_embeddings,
                               documents=docs, metadatas=metas)
        print(f"  Stored in ChromaDB collection 'docs_{project_id}'")

        return {"chunks": len(chunks), "source": source, "doc_type": doc_type}

    def _load(self, path: str) -> str:
        ext = path.split(".")[-1].lower()
        if ext == "pdf":
            import pypdf
            reader = pypdf.PdfReader(path)
            return "\n\n".join(p.extract_text() for p in reader.pages if p.extract_text())
        elif ext == "docx":
            import docx
            doc = docx.Document(path)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        else:
            return open(path, encoding="utf-8").read()

    def _paragraph_chunk(self, text: str, max_words: int,
                         overlap: int) -> list[str]:
        import re
        paragraphs = re.split(r'\n\s*\n', text)
        chunks, current, current_len = [], [], 0

        for para in paragraphs:
            para_words = len(para.split())
            if current_len + para_words > max_words and current:
                chunks.append("\n\n".join(current))
                current     = [current[-1]] if current else []
                current_len = len(current[0].split()) if current else 0
            current.append(para)
            current_len += para_words

        if current:
            chunks.append("\n\n".join(current))
        return [c for c in chunks if c.strip()]


trace_pipeline = TracePipeline()
doc_pipeline   = DocumentPipeline()