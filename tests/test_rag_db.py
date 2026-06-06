import pytest
from unittest.mock import patch
from src.rag.db import store_posts, search_posts, get_chroma_client
import shutil
import os

@pytest.fixture(autouse=True)
def mock_generate_embedding():
    with patch("src.rag.db.generate_embedding") as mock_gen:
        def dummy_embed(texts):
            return [[0.1] * 768 for _ in texts]
        mock_gen.side_effect = dummy_embed
        yield mock_gen

@pytest.fixture(autouse=True)
def clean_chroma_db():
    # Clear out chroma db before test if using a separate test path
    # Actually, to make it completely safe and independent we can patch get_chroma_client to use a temporary directory
    pass

def test_store_and_search_posts(tmp_path):
    with patch("src.rag.db.get_chroma_client") as mock_client:
        import chromadb
        # Use ephemeral client for tests
        ephemeral_client = chromadb.EphemeralClient()
        mock_client.return_value = ephemeral_client
        
        username = "testuser"
        posts = [
            {"post_id": "100", "content": "Dit is een post over garnalen", "date": "2024-01-01", "forum_name": "Garnalen", "thread_title": "Mijn aquarium"},
            {"post_id": "101", "content": "Iets over planten", "date": "2024-01-02", "forum_name": "Planten", "thread_title": "Planten groeien niet"},
        ]
        
        store_posts(username, posts)
        
        results = search_posts(username, "aquarium garnalen", limit=2)
        
        assert len(results) == 2
        post_ids = [r["post_id"] for r in results]
        assert "100" in post_ids
        assert "101" in post_ids
