"""Web scraper for knowledge base content."""
import re
import httpx

try:
    from bs4 import BeautifulSoup
    BS4 = True
except ImportError:
    BS4 = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TechmaticBot/1.0)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}


def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def scrape_url(url):
    result = {"url": url, "title": "", "content": "", "success": False, "error": None}
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        if BS4:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "iframe", "noscript", "svg", "header"]):
                tag.decompose()
            title = soup.title.string.strip() if soup.title else url
            main = (soup.find("main") or soup.find("article") or
                    soup.find("div", class_=re.compile(r'content|main|entry|post', re.I)) or
                    soup.body)
            text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")
        else:
            title_m = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
            title = title_m.group(1).strip() if title_m else url
            text = re.sub(r'<[^>]+>', ' ', html)

        content = clean_text(text)
        if len(content) > 12000:
            content = content[:12000] + "\n[truncated]"

        result.update({"title": title[:200], "content": content, "success": True})
    except Exception as e:
        result["error"] = str(e)
    return result
