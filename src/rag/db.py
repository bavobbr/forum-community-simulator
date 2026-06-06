import os
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from src.llm import generate_embedding

class GeminiEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        batch_size = 100
        all_embeddings = []
        for i in range(0, len(input), batch_size):
            batch = input[i:i+batch_size]
            all_embeddings.extend(generate_embedding(batch))
        return all_embeddings

_db_client = None

def get_chroma_client():
    global _db_client
    if _db_client is None:
        db_path = os.path.join("config", "chroma_db")
        os.makedirs(db_path, exist_ok=True)
        _db_client = chromadb.PersistentClient(path=db_path)
    return _db_client

def get_collection(username: str):
    client = get_chroma_client()
    import re
    safe_name = re.sub(r'[^\w\-]', '_', username.lower())
    return client.get_or_create_collection(
        name=f"posts_{safe_name}",
        embedding_function=GeminiEmbeddingFunction()
    )

def store_posts(username: str, posts: list[dict]):
    """Embed and store posts for a user."""
    if not posts:
        return
        
    collection = get_collection(username)
    
    ids = []
    documents = []
    metadatas = []
    
    for p in posts:
        post_id = str(p.get("post_id", ""))
        content = p.get("content", "").strip()
        if not post_id or not content:
            continue
            
        ids.append(post_id)
        documents.append(content)
        metadatas.append({
            "date": str(p.get("date", "")),
            "forum_name": str(p.get("forum_name", "")),
            "thread_title": str(p.get("thread_title", "")),
        })
        
    if ids:
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )

def search_posts(username: str, query: str, limit: int = 5) -> list[dict]:
    """Retrieve relevant historical posts for a user based on query."""
    collection = get_collection(username)
    
    if collection.count() == 0:
        return []
        
    # Chroma handles when n_results is greater than the collection size
    actual_limit = min(limit, collection.count())
    
    results = collection.query(
        query_texts=[query],
        n_results=actual_limit
    )
    
    posts = []
    if results and results.get("documents") and results["documents"][0]:
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        post_ids = results["ids"][0] if results.get("ids") else [""] * len(docs)
        
        for doc, meta, pid in zip(docs, metas, post_ids):
            posts.append({
                "post_id": pid,
                "content": doc,
                "date": meta.get("date", ""),
                "forum_name": meta.get("forum_name", ""),
                "thread_title": meta.get("thread_title", "")
            })
            
    return posts

def drop_posts(username: str):
    """Delete the collection for a given user."""
    client = get_chroma_client()
    import re
    safe_name = re.sub(r'[^\w\-]', '_', username.lower())
    try:
        client.delete_collection(name=f"posts_{safe_name}")
    except Exception:
        pass

def get_user_post_counts() -> dict[str, int]:
    """Return a dictionary mapping username to post count."""
    client = get_chroma_client()
    counts = {}
    for collection in client.list_collections():
        name = collection.name if hasattr(collection, 'name') else collection
        if name.startswith("posts_"):
            username = name[len("posts_"):]
            try:
                col_obj = collection if hasattr(collection, 'count') else client.get_collection(name)
                counts[username] = col_obj.count()
            except Exception:
                pass
    return counts

