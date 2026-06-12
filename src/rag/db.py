import os
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
import json
from pydantic import BaseModel
from src.llm import generate_embedding, call_llm_raw, MODEL_FLASH

class RankedPosts(BaseModel):
    post_ids: list[str]
from src.persona.scraper import parse_post_date_timestamp

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

def store_posts(username: str, posts: list[dict], progress_callback=None):
    """Embed and store posts for a user."""
    if not posts:
        return
        
    collection = get_collection(username)
    
    ids = []
    documents = []
    metadatas = []
    seen_ids = set()
    
    for p in posts:
        post_id = str(p.get("post_id", ""))
        content = p.get("content", "").strip()
        if not post_id or not content or post_id in seen_ids:
            continue
            
        seen_ids.add(post_id)
        ids.append(post_id)
        documents.append(content)
        date_str = str(p.get("date", ""))
        ts = parse_post_date_timestamp(date_str)
        
        meta = {
            "date": date_str,
            "forum_name": str(p.get("forum_name", "")),
            "thread_title": str(p.get("thread_title", "")),
        }
        if ts is not None:
            meta["timestamp"] = ts
            
        metadatas.append(meta)
        
    if ids:
        batch_size = 100
        total = len(ids)
        for i in range(0, total, batch_size):
            end_idx = min(i + batch_size, total)
            collection.upsert(
                ids=ids[i:end_idx],
                documents=documents[i:end_idx],
                metadatas=metadatas[i:end_idx]
            )
            if progress_callback:
                progress_callback(end_idx, total)

def rerank_posts(query: str, candidate_posts: list[dict]) -> list[dict]:
    if not candidate_posts:
        return []
        
    system_prompt = (
        "You are an expert relevance ranking assistant for a Dutch shrimp-keeping forum.\n"
        "Your task is to rank the provided list of historical posts based on how useful they would be as context to help an AI persona write a reply to the user's incoming query.\n\n"
        "When ranking, consider:\n"
        "1. Topical relevance: Do they discuss the same subjects (e.g., filters, water parameters, specific shrimp species)?\n"
        "2. Factual usefulness: Does the historical post contain opinions or facts that apply to the incoming query?\n\n"
        "Return the post_ids ordered from most relevant (1st) to least relevant (last)."
    )
    
    candidates_json = []
    for p in candidate_posts:
        candidates_json.append({
            "post_id": p.get("post_id", ""),
            "content": p.get("content", "")
        })
        
    user_prompt = (
        f"INCOMING QUERY TO REPLY TO:\n{query}\n\n"
        f"CANDIDATE HISTORICAL POSTS:\n{json.dumps(candidates_json, ensure_ascii=False, indent=2)}"
    )
    
    try:
        resp = call_llm_raw(
            system=system_prompt,
            user=user_prompt,
            max_tokens=8192,
            model=MODEL_FLASH,
            response_schema=RankedPosts
        )
        raw_text = resp.text.strip() if resp.text else ""
        if not raw_text:
            return candidate_posts
            
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()
        
        try:
            ranked_data = json.loads(raw_text)
            ranked_ids = ranked_data.get("post_ids", [])
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON during reranking: {e}. Raw text: {repr(raw_text)}")
            # Fallback: try to extract via regex in case of truncated response
            import re
            match = re.search(r'"post_ids"\s*:\s*\[(.*?)\]?', raw_text, re.DOTALL)
            if match:
                # Extract numbers/strings
                ranked_ids = [x.strip(' \n\r\t"\'') for x in match.group(1).split(',') if x.strip(' \n\r\t"\'')]
            else:
                return candidate_posts
        
        # Ensure ids are strings
        ranked_ids = [str(pid) for pid in ranked_ids]
        
        # Reorder candidate_posts based on ranked_ids
        post_map = {str(p.get("post_id")): p for p in candidate_posts if p.get("post_id")}
        reordered = []
        for pid in ranked_ids:
            if pid in post_map:
                reordered.append(post_map[pid])
                
        # Append any posts that the model might have missed
        missed_ids = set(post_map.keys()) - set(ranked_ids)
        for pid in missed_ids:
            reordered.append(post_map[pid])
            
        return reordered
    except Exception as e:
        print(f"Error during reranking: {e}")
        return candidate_posts

def search_posts(username: str, query: str, limit: int = 5) -> list[dict]:
    """Retrieve relevant historical posts for a user based on query."""
    collection = get_collection(username)
    
    if collection.count() == 0:
        return []
        
    # Fetch a larger candidate pool for reranking
    candidate_limit = max(20, limit)
    actual_limit = min(candidate_limit, collection.count())
    
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
            
    if posts:
        posts = rerank_posts(query, posts)
            
    return posts[:limit]

def drop_posts(username: str):
    """Delete the collection for a given user."""
    client = get_chroma_client()
    import re
    safe_name = re.sub(r'[^\w\-]', '_', username.lower())
    try:
        client.delete_collection(name=f"posts_{safe_name}")
    except Exception:
        pass

def get_oldest_post_ts(username: str) -> int | None:
    """Return the timestamp of the oldest post in the user's collection."""
    collection = get_collection(username)
    if collection.count() == 0:
        return None
        
    results = collection.get(include=["metadatas"])
    metadatas = results.get("metadatas", [])
    
    timestamps = []
    for meta in metadatas:
        if meta and "timestamp" in meta:
            timestamps.append(meta["timestamp"])
            
    if timestamps:
        return min(timestamps)
    return None

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

