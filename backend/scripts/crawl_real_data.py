import asyncio, os, sys, io, re
import httpx
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

# Đảm bảo in tiếng Việt không bị lỗi trong Terminal Windows
if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.closed:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

OUTPUT_FILE = "../Data/real_news.csv"
MAX_PAGES = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

SOURCES = {
    "vnexpress_bongda": {
        "url_template": "https://vnexpress.net/the-thao/bong-da-p{}",
        "domain": "vnexpress.net",
        "language": "vi",
        "category": "bong-da"
    },
    "reuters_football": {
        "url_template": "https://www.reuters.com/sports/soccer/",
        "domain": "reuters.com",
        "language": "en",
        "category": "bong-da"
    },
    "bongda24h_anh": {
        "url_template": "https://bongda24h.vn/bong-da-anh-c172-p{}.html",
        "domain": "bongda24h.vn",
        "language": "vi",
        "category": "bong-da"
    },
    "bbc_football": {
        "url_template": "https://www.bbc.com/sport/football",
        "domain": "bbc.com",
        "language": "en",
        "category": "bong-da"
    }
}

async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            res = await client.get(url, headers=HEADERS)
            res.raise_for_status()
            return res.text
        except Exception as e:
            print(f"    [LỖI] Không thể tải {url}: {e}")
            return None

def clean_text(el) -> str:
    return el.get_text(separator="\n", strip=True) if el else ""

async def extract_links(html: str, domain: str, base_url: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if domain == "vnexpress.net" and "-p" not in href and href.endswith(".html"):
            if href.startswith("/"): href = "https://vnexpress.net" + href
            links.add(href)
        elif domain == "bongda24h.vn" and href.endswith(".html") and "bong-da" in href:
            if href.startswith("/"): href = "https://bongda24h.vn" + href
            links.add(href)
        elif domain == "theguardian.com" and ("/football/20" in href or "/sport/20" in href):
            if href.startswith("/"): href = "https://www.theguardian.com" + href
            links.add(href)
        elif domain == "football365.com" and "/news/" in href and not href.endswith("/news/"):
            if href.startswith("/"): href = "https://www.football365.com" + href
            links.add(href)
        elif domain in ["hoopsrumors.com", "mlbtraderumors.com"] and href.startswith(f"https://www.{domain}/20"):
            links.add(href)
        elif domain == "sportando.basketball" and "sportando.basketball/en/" in href and "category" not in href and "news" not in href and len(href.split("/")) > 4:
            if href.startswith("/"): href = "https://sportando.basketball" + href
            links.add(href)
        elif domain == "perfect-tennis.com":
            if href.startswith("/"): href = "https://www.perfect-tennis.com" + href
            if href.startswith("https://www.perfect-tennis.com/") and href.count("/") == 4 and len(href.split("/")[-2]) > 20:
                links.add(href)
    return list(links)

async def crawl_article(url: str, domain: str, language: str, category: str) -> dict:
    html = await fetch_html(url)
    if not html: return None
    soup = BeautifulSoup(html, "html.parser")
    
    # Loại bỏ rác
    for tag in soup.find_all(["script", "style", "iframe", "aside"]): tag.decompose()

    title, summary, date_str, content = "", "", "", ""

    if domain == "vnexpress.net":
        title = clean_text(soup.select_one("h1.title-detail"))
        summary = clean_text(soup.select_one("p.description"))
        date_str = clean_text(soup.select_one("span.date"))
        content = clean_text(soup.select_one("article.fck_detail"))
    elif domain == "bongda24h.vn":
        title = clean_text(soup.select_one("h1.title-detail") or soup.find("h1"))
        summary = clean_text(soup.select_one(".sapo-detail") or soup.select_one("h2"))
        date_str = clean_text(soup.select_one(".time-detail") or soup.select_one(".time"))
        content = clean_text(soup.select_one(".content-detail") or soup.find("article"))
    elif domain == "theguardian.com":
        title = clean_text(soup.find("h1"))
        content_div = soup.select_one("#maincontent") or soup.find("article")
        if content_div:
            content = "\n".join([clean_text(p) for p in content_div.find_all("p") if len(clean_text(p)) > 30])
    elif domain == "football365.com":
        title = clean_text(soup.find("h1"))
        content = "\n".join([clean_text(p) for p in soup.find_all("p") if len(clean_text(p)) > 30])
    elif domain in ["hoopsrumors.com", "mlbtraderumors.com", "perfect-tennis.com"]:
        title = clean_text(soup.find("h1"))
        content = "\n".join([clean_text(p) for p in soup.select("div.entry-content p") if len(clean_text(p)) > 30])

    if not content:
        # Generic fallback
        title = title or clean_text(soup.find("h1"))
        ps = soup.find_all("p")
        content = "\n".join([clean_text(p) for p in ps if len(clean_text(p)) > 30])
        
    if not title or not content:
        return None

    return {
        "category": category,
        "title": title,
        "summary": summary,
        "publish_date": date_str,
        "url": url,
        "domain": domain,
        "content": content,
        "language": language
    }

async def main():
    print("⚽ BẮT ĐẦU CÀO DỮ LIỆU (SONG NGỮ) ⚽\n")
    all_articles = []
    seen_urls = set()

    if os.path.exists(OUTPUT_FILE):
        try:
            df_old = pd.read_csv(OUTPUT_FILE)
            seen_urls = set(df_old["url"].dropna())
            print(f"📂 Đã có {len(seen_urls)} bài báo trong DB cũ. Bỏ qua các URL trùng.")
        except: pass

    for src_key, cfg in SOURCES.items():
        domain = cfg["domain"]
        lang = cfg["language"]
        category = cfg.get("category", "the-thao")
        print(f"\n🌐 Nguồn: {domain} ({lang}) - Chuyên mục: {category.upper()}")
        
        # Với BBC và Reuters không có page ID rõ ràng trên URL, ta cào trực tiếp trang gốc
        pages = range(1, MAX_PAGES + 1) if "{}" in cfg["url_template"] else [1]
        
        for p in pages:
            url = cfg["url_template"].format(p) if "{}" in cfg["url_template"] else cfg["url_template"]
            print(f"  -> Quét trang: {url}")
            
            html = await fetch_html(url)
            if not html: continue
            
            links = await extract_links(html, domain, url)
            print(f"  -> Tìm thấy {len(links)} links. Bắt đầu cào chi tiết...")
            
            for link in links:
                if link in seen_urls: continue
                
                await asyncio.sleep(0.5)
                data = await crawl_article(link, domain, lang, category)
                if data:
                    all_articles.append(data)
                    seen_urls.add(link)
                    print(f"    ✅ [{lang.upper()}] {data['title'][:60]}...")
                else:
                    print(f"    ❌ Lỗi/Không đủ nội dung: {link}")

    if all_articles:
        df_new = pd.DataFrame(all_articles)
        
        if os.path.exists(OUTPUT_FILE):
            df_old = pd.read_csv(OUTPUT_FILE)
            merged = pd.concat([df_old, df_new]).drop_duplicates(subset=["url"], keep="first")
        else:
            merged = df_new

        # Sắp xếp và tạo cột stt
        merged.drop_duplicates(subset=["title"], keep="first", inplace=True)
        merged.reset_index(drop=True, inplace=True)
        if "stt" in merged.columns: merged.drop(columns=["stt"], inplace=True)
        merged.insert(0, "stt", range(1, len(merged) + 1))
        
        # Đảm bảo đúng chuẩn cột mà hệ thống yêu cầu
        cols = ["stt", "category", "title", "summary", "publish_date", "url", "domain", "content", "language"]
        for c in cols: 
            if c not in merged.columns: merged[c] = ""
        merged = merged[cols]

        merged.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
        print(f"\n🎉 Xong! Đã lưu {len(all_articles)} bài mới. Tổng DB: {len(merged)} bài.")
    else:
        print("\n⚠️ Không cào thêm được bài nào mới.")

if __name__ == "__main__":
    asyncio.run(main())
