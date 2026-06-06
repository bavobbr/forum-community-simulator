---
name: simulate-persona
description: Orchestrates an interactive chat turn with an AI persona, fetching RAG context and building the strict system prompt via Python.
---

# Simulate Persona Chat Skill

This skill allows you to act as an orchestrator for interactive persona chats, ensuring that the generated responses precisely match the underlying Python logic of the `event.py` generator, while enriching the prompt with historical RAG context.

## Trigger
Use this skill when the user asks to "chat with [username]", "talk to [username]", or sends a message meant for a specific persona.

## Workflow Instructions

When activated, you MUST perform these exact steps for **each** chat message the user sends to the persona:

1. **Retrieve Context (RAG)**
   - Call the `search_user_posts` tool from the `forum-rag-mcp` server.
   - Use the username and the user's chat message as the query.
   - Limit the results to 3.

2. **Generate Reply (Python Engine)**
   - Call the `simulate_chat_turn` tool from the `forum-community-simulator` MCP server.
   - Pass the username, the user's chat message, and the exact string output from the `search_user_posts` tool as the `rag_context`.

3. **Respond**
   - Output the generated string from `simulate_chat_turn` as the persona's reply to the user.
   - Do NOT wrap the reply in excessive explanation or preamble (e.g. avoid saying "Here is the response:"). Just output the reply.
   - If you want to show the retrieved context to the user for debugging purposes, you may do so in a collapsible details block or quote block *before* the reply.

4. **Continue the Loop**
   - Await the user's next message and repeat the process.
