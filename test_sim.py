import os
from dotenv import load_dotenv
load_dotenv()

from src.mcp.server import simulate_chat_turn

rag_json = """[
  {
    "post_id": "123",
    "content": "Dit is een RAG test bericht.",
    "date": "09-12-2023",
    "forum_name": "Test",
    "thread_title": "Test thread"
  }
]"""

reply = simulate_chat_turn("acku", "welke spelletjes", rag_context=rag_json)
print("REPLY:", reply)
