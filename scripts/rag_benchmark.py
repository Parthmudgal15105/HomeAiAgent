"""Index local runbooks and measure title-matched retrieval recall using local embeddings."""
import asyncio,json
from pathlib import Path
from backend.app.config import Settings
from backend.app.rag import LocalRAG

async def main():
    rag=LocalRAG(Settings())
    ingestion=await rag.ingest_runbooks()
    cases=[('CodeDuel website unavailable','codeduel-unavailable.md'),('CodeDuel submissions stuck in queue','codeduel-submissions-stuck.md'),('Redis server unavailable connection refused','redis-unavailable.md'),('MongoDB Atlas database unavailable','mongodb-unavailable.md'),('Docker daemon down cannot connect socket','docker-daemon-down.md'),('Cloudflare tunnel unavailable 502','cloudflare-tunnel-unavailable.md'),('Tailscale unavailable cannot connect','tailscale-unavailable.md'),('Disk full no space left','disk-full.md'),('High memory usage OOM','high-memory-usage.md'),('Host network disconnected WiFi down','network-disconnected.md'),('Worker failure BullMQ jobs not processed','worker-failure.md')]
    results=[]
    for query,source in cases:
        docs=await rag.retrieve(query)
        results.append({'query':query,'expected':source,'retrieved':[{'source':d.get('source'), 'score':d['score']} for d in docs],'hit':any(d.get('source')==source for d in docs)})
    report={'embedding_model':rag.settings.ollama_embedding_model,'ingestion':ingestion,'queries':len(results),'recall_at_k':sum(x['hit'] for x in results)/len(results),'k':rag.settings.rag_top_k,'score_threshold':rag.settings.rag_score_threshold,'limitation':'Small authored title/symptom benchmark, not independent holdout retrieval evaluation.','results':results}
    Path('/tmp/aiops-rag-benchmark.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
asyncio.run(main())
