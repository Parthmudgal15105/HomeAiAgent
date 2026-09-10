from abc import ABC, abstractmethod
import hashlib
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx

from .config import Settings
from .safety import redact


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=self.settings.agent_llm_timeout_seconds, trust_env=False) as client:
            response = await client.post(self.settings.ollama_base_url.rstrip('/') + '/api/embed', json={
                'model': self.settings.ollama_embedding_model, 'input': redact(text, 10000), 'truncate': True, 'keep_alive': '1m',
            })
            response.raise_for_status()
            return response.json()['embeddings'][0]


class LocalRAG:
    def __init__(self, settings: Settings, embedding: EmbeddingProvider | None = None):
        self.settings = settings
        self.embedding = embedding or OllamaEmbeddingProvider(settings)
        # Changing models starts a compatible collection rather than mixing embedding spaces.
        suffix = hashlib.sha256(settings.ollama_embedding_model.encode()).hexdigest()[:8]
        self.collection = f'{settings.qdrant_collection}_{suffix}'
        self._ready = False

    def client(self):
        headers = {'api-key': self.settings.qdrant_api_key} if self.settings.qdrant_api_key else {}
        return httpx.AsyncClient(base_url=self.settings.qdrant_url.rstrip('/'), headers=headers, timeout=20, trust_env=False)

    async def ensure_collection(self, dimensions: int):
        if self._ready:
            return
        async with self.client() as client:
            response = await client.get(f'/collections/{self.collection}')
            if response.status_code == 404:
                response = await client.put(f'/collections/{self.collection}', json={'vectors': {'size': dimensions, 'distance': 'Cosine'}})
                if response.status_code != 409:
                    response.raise_for_status()
            else:
                response.raise_for_status()
                size = response.json()['result']['config']['params']['vectors']['size']
                if size != dimensions:
                    raise ValueError('Embedding dimensions do not match existing Qdrant collection')
        self._ready = True

    async def upsert(self, document_id: str, text: str, kind: str, metadata: dict | None = None):
        text = redact(text, 10000)
        vector = await self.embedding.embed(text)
        await self.ensure_collection(len(vector))
        payload = {'document_id': document_id, 'text': text, 'kind': kind, **redact(metadata or {})}
        point = {'id': str(uuid5(NAMESPACE_URL, document_id)), 'vector': vector, 'payload': payload}
        async with self.client() as client:
            response = await client.put(f'/collections/{self.collection}/points', params={'wait': 'true'}, json={'points': [point]})
            response.raise_for_status()

    async def retrieve(self, query: str) -> list[dict]:
        vector = await self.embedding.embed(query)
        await self.ensure_collection(len(vector))
        async with self.client() as client:
            response = await client.post(f'/collections/{self.collection}/points/query', json={
                'query': vector, 'limit': self.settings.rag_top_k, 'with_payload': True,
                'score_threshold': self.settings.rag_score_threshold,
            })
            response.raise_for_status()
            return [{'score': point['score'], **point['payload']} for point in response.json()['result']['points']]

    async def ingest_runbooks(self) -> dict:
        count = 0
        for path in sorted(Path(self.settings.runbooks_path).glob('*.md')):
            text = path.read_text()[:50000]
            sections = re.split(r'(?m)(?=^## )', text)
            chunks: list[str] = []
            current = ''
            for section in sections:
                if len(current) + len(section) > 4500 and current:
                    chunks.append(current)
                    current = ''
                current += section
            if current:
                chunks.append(current)
            for index, chunk in enumerate(chunks):
                await self.upsert(f'runbook:{path.name}:{index}', chunk, 'runbook', {'source': path.name, 'title': text.splitlines()[0].lstrip('# ')})
                count += 1
        return {'chunks_indexed': count, 'collection': self.collection, 'embedding_model': self.settings.ollama_embedding_model}
