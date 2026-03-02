from prometheus_client import Counter, Histogram

cache_hits = Counter(
    "rag_cache_hits_total",
    "Cache hits",
    ["collection"],
)

cache_misses = Counter(
    "rag_cache_misses_total",
    "Cache misses",
    ["collection"],
)

llm_requests = Counter(
    "rag_llm_requests_total",
    "LLM API calls",
)

embedding_requests = Counter(
    "rag_embedding_requests_total",
    "Embedding API calls",
)

search_latency = Histogram(
    "rag_search_latency_seconds",
    "Search latency in seconds",
    ["search_mode"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
