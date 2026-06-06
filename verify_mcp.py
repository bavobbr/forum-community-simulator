import os
import json
from src.mcp.server import (
    get_user_posts,
    get_thread_context,
    get_daily_activity,
    get_top_members,
    get_user_last_active
)

def main():
    print("Testing get_user_posts (fetching 1 post)...")
    posts = get_user_posts(username="wokebot", limit=1)
    print(f"Result: {posts}\n")

    print("Testing get_daily_activity...")
    daily = get_daily_activity()
    print(f"Result length: {len(daily)}\n")

    print("Testing forum://memberlist/top100...")
    top_members = get_top_members()
    print(f"Result length: {len(top_members)}\n")

    # Assuming we have at least one user from top_members
    members = json.loads(top_members)
    if members:
        user_id = members[0]["user_id"]
        print(f"Testing forum://user/{{id}}/last_active for {user_id}...")
        last_active = get_user_last_active(user_id=user_id)
        print(f"Result: {last_active}\n")

    # Assuming we have at least one post from daily activity
    daily_posts = json.loads(daily)
    if daily_posts:
        post_id = daily_posts[0]["post_id"]
        print(f"Testing get_thread_context for post {post_id}...")
        context = get_thread_context(post_id=post_id, n=2)
        print(f"Result: {context}\n")

if __name__ == "__main__":
    main()
