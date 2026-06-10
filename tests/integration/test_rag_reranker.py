import pytest
import os
from dotenv import load_dotenv
from src.rag.db import rerank_posts

load_dotenv(override=True)
import src.llm
from google import genai
if os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_API_KEY") != "test-api-key-for-unit-tests":
    src.llm._client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

@pytest.mark.integration
def test_live_rerank_posts():
    """Test that the live Gemini Flash API correctly ranks candidate posts based on relevance."""
    if not os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") == "test-api-key-for-unit-tests":
        pytest.skip("No real GOOGLE_API_KEY found, skipping integration test.")
        
    query = "Mijn aquariumwater is troebel, wat kan ik doen aan de waterwaarden?"
    
    # Candidate 1 is irrelevant. Candidate 2 is highly relevant. Candidate 3 is somewhat relevant.
    candidates = [
        {"post_id": "1", "content": "Ik gebruik altijd een ander merk voer voor mijn crystal reds, veel goedkoper."},
        {"post_id": "2", "content": "Troebel water komt vaak door een bacteriebloei. Ik zou een 50% waterwissel doen en je nitriet meten."},
        {"post_id": "3", "content": "Mijn pomp was laatst stuk, toen was het water ook niet meer helder. Heb je het filter schoongemaakt?"}
    ]
    
    reranked = rerank_posts(query, candidates)
    
    # Verify the returned list contains the same number of posts
    assert len(reranked) == 3
    
    post_ids = [p.get("post_id") for p in reranked if p.get("post_id")]
    
    # Verify that the highly relevant post (id 2) was ranked higher than the irrelevant one (id 1)
    assert "2" in post_ids
    assert "1" in post_ids
    assert post_ids.index("2") < post_ids.index("1"), f"Expected highly relevant post 2 to be ranked before irrelevant post 1. Actual order: {post_ids}"
