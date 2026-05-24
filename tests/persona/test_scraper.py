from pathlib import Path
from src.persona.scraper import parse_posts_page, parse_search_id, parse_has_next_page

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "search_user_119.html").read_text(
    encoding="latin-1"
)


def test_parse_posts_page_returns_correct_count():
    posts = parse_posts_page(FIXTURE)
    assert len(posts) == 25  # default pp=25 in fixture


def test_parse_posts_page_post_structure():
    posts = parse_posts_page(FIXTURE)
    first = posts[0]
    assert first["post_id"] == 1743241
    assert first["thread_id"] == 12769
    assert first["thread_title"] == "Welke spellekes zijde mee bezig"
    assert first["forum_id"] == 22
    assert first["forum_name"] == "Videogames"
    assert "mewgenics" in first["content"]
    assert first["date"] == "09-03-2026, 19:04"


def test_parse_posts_page_content_has_substance():
    posts = parse_posts_page(FIXTURE)
    for post in posts:
        assert len(post["content"]) > 2, f"Post {post['post_id']} has too little content"


def test_parse_search_id_extracts_id():
    search_id = parse_search_id(FIXTURE)
    assert search_id == "11065652"


def test_parse_has_next_page_true_when_multiple_pages():
    assert parse_has_next_page(FIXTURE) is True


def test_parse_has_next_page_false_on_single_page():
    single_page_html = "<html><body><div>Results 1 to 5 of 5</div></body></html>"
    assert parse_has_next_page(single_page_html) is False
