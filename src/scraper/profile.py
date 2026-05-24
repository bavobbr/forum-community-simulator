import re
from bs4 import BeautifulSoup
from datetime import date, datetime

_DATE_PATTERN = re.compile(r"\b(\d{2}-\d{2}-\d{4}),\s*\d{2}:\d{2}")

def parse_last_active(html: str) -> date | None:
    soup = BeautifulSoup(html, "html.parser")
    for td in soup.find_all("td", class_="thead"):
        text = td.get_text(separator=" ", strip=True)
        match = _DATE_PATTERN.search(text)
        if match:
            try:
                return datetime.strptime(match.group(1), "%d-%m-%Y").date()
            except ValueError:
                continue
    return None
