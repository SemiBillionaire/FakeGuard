import httpx
from bs4 import BeautifulSoup

"""
@brief Công cụ cào bài báo từ các trang web Việt Nam
@details Trả về: title, summary, publish_date, content (plain text), url, domain
"""

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5",
    "Referer": "https://www.google.com/",
}

async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, headers=HEADERS, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"    [LOAD_ERR] {url}: {e}")
            return None

def _text(el) -> str:
    """Trích xuất plain text từ 1 element BeautifulSoup."""
    return el.get_text(strip=True) if el else ""

def _content_text(el) -> str:
    """
    Trích xuất plain text từ khối nội dung chính (loại bỏ quảng cáo, chú thích ảnh).
    Mỗi đoạn văn được nối bằng dấu xuống dòng để dễ đọc.
    """
    if not el:
        return ""
    # Xóa các tag quảng cáo, script, style trước khi lấy text
    for tag in el.find_all(["script", "style", "figure", "figcaption", "iframe", "aside"]):
        tag.decompose()
    paragraphs = [p.get_text(strip=True) for p in el.find_all(["p", "h2", "h3"]) if p.get_text(strip=True)]
    return "\n".join(paragraphs) if paragraphs else el.get_text(separator=" ", strip=True)

# ------------------------------------------------------------------
# Parsers cho từng trang báo
# ------------------------------------------------------------------

def parse_vnexpress(soup: BeautifulSoup) -> dict:
    return {
        "title":        _text(soup.select_one("h1.title-detail")),
        "summary":      _text(soup.select_one("p.description")),
        "publish_date": _text(soup.select_one("span.date")),
        "content":      _content_text(soup.select_one("article.fck_detail")),
    }

def parse_tuoitre(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("#main-detail h1") or soup.find("h1")
    summary = soup.select_one(".detail-sapo") or soup.select_one("h2")
    date_el = soup.select_one(".detail-time") or soup.select_one("time")
    content = soup.select_one("#main-detail")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_dantri(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.title-page") or soup.select_one("h1.e-magazine__title") or soup.find("h1")
    summary = soup.select_one(".singular-sapo") or soup.select_one(".e-magazine__sapo") or soup.select_one("h2.e-magazine__subtitle") or soup.select_one("h2")
    date_el = soup.select_one("time.author-time") or soup.select_one("time")
    content = (soup.select_one(".singular-content")
               or soup.select_one(".e-magazine__body")
               or soup.select_one(".dt-news__body")
               or soup.select_one("article.e-magazine")
               or soup.select_one("div.detail")
               or soup.select_one("article"))
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_kenh14(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.kbwc-title") or soup.select_one("h1.title") or soup.find("h1")
    summary = soup.select_one(".kbwc-sapo") or soup.select_one(".sapo")
    date_el = soup.select_one("span.kbwc-time") or soup.select_one("time")
    content = soup.select_one(".kbw-content") or soup.select_one(".klw-content")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_genk(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.title") or soup.find("h1")
    summary = soup.select_one(".sapo") or soup.select_one(".knc-sapo")
    date_el = soup.select_one("time") or soup.select_one(".time")
    content = soup.select_one(".knc-content") or soup.select_one("article.content") or soup.select_one(".article-body")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_baochinhphu(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.article-title") or soup.find("h1")
    summary = soup.select_one(".article-sapo") or soup.select_one("h2")
    date_el = soup.select_one(".article-date") or soup.select_one("time")
    content = soup.select_one(".article-body") or soup.select_one("article")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_nhandan(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.article__title") or soup.find("h1")
    summary = soup.select_one(".article__sapo") or soup.select_one("h2")
    date_el = soup.select_one(".article__meta time") or soup.select_one("time")
    content = soup.select_one(".article__body") or soup.select_one("article")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_thethao247(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.title") or soup.find("h1")
    summary = soup.select_one(".sapo") or soup.select_one("h2")
    date_el = soup.select_one("time") or soup.select_one(".time")
    content = soup.select_one(".article-content") or soup.select_one(".cms-body")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_cafef(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.title") or soup.find("h1")
    summary = soup.select_one(".sapo") or soup.select_one("h2")
    date_el = soup.select_one("time") or soup.select_one(".time")
    content = soup.select_one("#mainContent") or soup.select_one(".cfcontainer")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_vneconomy(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.article-title") or soup.find("h1")
    summary = soup.select_one(".article-sapo") or soup.select_one("h2")
    date_el = soup.select_one("time") or soup.select_one(".date")
    content = soup.select_one(".article-main-content") or soup.select_one("article")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_generic(soup: BeautifulSoup) -> dict:
    title = soup.find("h1")
    content = soup.find("article")
    if not content:
        candidates = sorted(soup.find_all("div"), key=lambda d: len(d.get_text()), reverse=True)
        content = candidates[0] if candidates else soup.find("body")
    return {
        "title":        _text(title),
        "summary":      "",
        "publish_date": _text(soup.find("time")),
        "content":      _content_text(content),
    }


def parse_thanhnien(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.detail__title") or soup.find("h1")
    summary = soup.select_one(".detail__summary") or soup.select_one("h2")
    date_el = soup.select_one(".detail-date") or soup.select_one("time")
    content = soup.select_one(".detail__content") or soup.select_one("article")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

def parse_znews(soup: BeautifulSoup) -> dict:
    title   = soup.select_one("h1.the-article-title") or soup.find("h1")
    summary = soup.select_one(".the-article-summary") or soup.select_one("p.summary")
    date_el = soup.select_one(".the-article-publish") or soup.select_one("time")
    content = soup.select_one(".the-article-body") or soup.select_one("article")
    return {
        "title":        _text(title),
        "summary":      _text(summary),
        "publish_date": _text(date_el),
        "content":      _content_text(content),
    }

# ------------------------------------------------------------------
# Router: domain -> parser
# ------------------------------------------------------------------
DOMAIN_PARSERS = {
    "vnexpress.net":  parse_vnexpress,
    "tuoitre.vn":     parse_tuoitre,
    "dantri.com.vn":  parse_dantri,
    "kenh14.vn":      parse_kenh14,
    "genk.vn":        parse_genk,
    "baochinhphu.vn": parse_baochinhphu,
    "nhandan.vn":     parse_nhandan,
    "thethao247.vn":  parse_thethao247,
    "cafef.vn":       parse_cafef,
    "vneconomy.vn":   parse_vneconomy,
    "thanhnien.vn":   parse_thanhnien,
    "znews.vn":       parse_znews,
}

async def crawl_url(url: str) -> dict:
    """
    Cào 1 bài báo, trả về dict với 7 trường:
    title, summary, publish_date, content, url, domain, label
    """
    html = await fetch_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    matched_domain = ""
    matched_parser = parse_generic
    for domain, parser_fn in DOMAIN_PARSERS.items():
        if domain in url:
            matched_domain = domain
            matched_parser = parser_fn
            break

    data = matched_parser(soup)
    data["url"]    = url
    data["domain"] = matched_domain or url.split("/")[2]
    data["label"]  = 1  # 1 = Real news

    return data
