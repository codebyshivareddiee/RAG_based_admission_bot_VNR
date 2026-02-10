"""
Quick diagnostic script to check Pinecone index status and data.

Run:  python debug_pinecone.py
"""
from app.config import get_settings
from pinecone import Pinecone

settings = get_settings()

pc = Pinecone(api_key=settings.PINECONE_API_KEY)
index = pc.Index(settings.PINECONE_INDEX_NAME)

# 1. Check index stats
stats = index.describe_index_stats()
print("=" * 60)
print("PINECONE INDEX STATS")
print("=" * 60)
print(f"Index name : {settings.PINECONE_INDEX_NAME}")
print(f"Total vectors: {stats.get('total_vector_count', getattr(stats, 'total_vector_count', 'N/A'))}")
print(f"Dimension    : {stats.get('dimension', getattr(stats, 'dimension', 'N/A'))}")
print()

# 2. Try a simple query without filter
from openai import OpenAI

client = OpenAI(api_key=settings.OPENAI_API_KEY)
resp = client.embeddings.create(
    input=["placement information 2024"],
    model=settings.OPENAI_EMBEDDING_MODEL,
)
query_vec = resp.data[0].embedding

print("=" * 60)
print("QUERY: 'placement information 2024' (NO filter)")
print("=" * 60)
results_no_filter = index.query(vector=query_vec, top_k=3, include_metadata=True)
matches = getattr(results_no_filter, "matches", None) or []
print(f"Matches found: {len(matches)}")
for m in matches:
    score = getattr(m, "score", 0)
    meta = getattr(m, "metadata", {}) or {}
    print(f"  score={score:.3f}  college={meta.get('college','?')}  file={meta.get('filename','?')}")
    print(f"    text={meta.get('text','')[:120]}...")
print()

print("=" * 60)
print(f"QUERY: 'placement information 2024' (filter: college={settings.COLLEGE_SHORT_NAME})")
print("=" * 60)
results_filtered = index.query(
    vector=query_vec,
    top_k=3,
    include_metadata=True,
    filter={"college": {"$eq": settings.COLLEGE_SHORT_NAME}},
)
matches2 = getattr(results_filtered, "matches", None) or []
print(f"Matches found: {len(matches2)}")
for m in matches2:
    score = getattr(m, "score", 0)
    meta = getattr(m, "metadata", {}) or {}
    print(f"  score={score:.3f}  college={meta.get('college','?')}  file={meta.get('filename','?')}")
    print(f"    text={meta.get('text','')[:120]}...")
