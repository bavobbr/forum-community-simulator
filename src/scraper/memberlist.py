from bs4 import BeautifulSoup
from src.models import Member


def parse_memberlist(html: str) -> list[Member]:
    soup = BeautifulSoup(html, "html.parser")
    members = []

    for row in soup.find_all("tr"):
        link = row.find("a", href=lambda h: h and "member.php?u=" in h)
        if not link:
            continue
        href = link["href"]
        try:
            user_id = int(href.split("u=")[1].split("&")[0])
        except (IndexError, ValueError):
            continue

        username = link.get_text(strip=True)
        if not username:
            continue

        # Find post count: a cell whose text is purely numeric after removing commas.
        # Dates like "06-01-2007" will NOT match because they contain hyphens,
        # and stripping only commas leaves the hyphens intact.
        cells = row.find_all("td")
        post_count = None
        for cell in cells:
            text = cell.get_text(strip=True).replace(",", "")
            if text.isdigit() and int(text) > 0:
                post_count = int(text)
                break

        if post_count is None:
            continue

        members.append(Member(user_id=user_id, username=username, post_count=post_count, last_active=None))

    return sorted(members, key=lambda m: m.post_count, reverse=True)
