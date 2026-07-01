"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║          ALGIHAZ HOLDING — COMPETITIVE INTELLIGENCE AGENT                        ║
║          Powered by Gemini · Playwright · BeautifulSoup                          ║
║          Tracks: Competitors, Clients & Regional Project Portals                 ║
╚══════════════════════════════════════════════════════════════════════════════════╝
"""

# ─── Standard Library ─────────────────────────────────────────────────────────
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

# ─── Third-Party ──────────────────────────────────────────────────────────────
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai
from google.genai import types
from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

# ─── Local Modules ────────────────────────────────────────────────────────────
from keywords import DEAL_KEYWORDS
from targets import TARGETS

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
ENV_FILE      = Path(".env")
SESSION_DIR   = Path("./linkedin_session")
OUTPUT_FILE   = Path("./competitor_deals_report.json")
MAX_BLOCK_LEN = 2000   # chars sent per snippet to AI
MIN_BLOCK_LEN = 60     # minimum text length to keep a block

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─── Per-Domain Scraper Registry ──────────────────────────────────────────────
# Maps hostname fragments → scraper strategy tag
# Strategies:  "static"   → requests + BS4
#              "js"       → Playwright headless
#              "aspx"     → Playwright (ASP.NET forms)
#              "wordpress" → requests + WP REST API first, fallback BS4
#              "etimad"   → Playwright with heavy wait / pagination
JS_REQUIRED_DOMAINS = {
    "alfanarprojects.com",
    "nesmapartners.com",
    "rawabielectric.com",
    "tataprojects.com",
    "aramco.com",
    "se.com.sa",
    "modon.gov.sa",
    "larsentoubro.com",
    "wescosa.com",
    "nesmanit.com",
    "bahra-electric.com",
    "saudigulfprojects.com",  # WP but Cloudflare-protected
    "marafiq.com.sa",
    "constructionweeksaudi.com",
    "constructionweekonline.com",
}

ASPX_DOMAINS = {
    "en.hdec.kr",
}

ETIMAD_DOMAINS = {
    "tenders.etimad.sa",
}

WORDPRESS_API_SITES = {
    # domain → WP REST API base  (if known to support it)
    "utilitiesme.com": "https://www.utilitiesme.com/wp-json/wp/v2/posts",
    "ssem.com.sa": "https://ssem.com.sa/wp-json/wp/v2/posts",
    "nesma.com": "https://www.nesma.com/wp-json/wp/v2/posts",
    "bahra-electric.com": "https://www.bahra-electric.com/wp-json/wp/v2/posts",
}

# ─── Environment Loader ───────────────────────────────────────────────────────
def load_env() -> dict:
    load_dotenv(ENV_FILE)
    required = [
        "GEMINI_API_KEY",
        "LINKEDIN_USERNAME",
        "LINKEDIN_PASSWORD",
        "MEED_USERNAME",
        "MEED_PASSWORD",
    ]
    config, missing = {}, []
    for key in required:
        val = os.getenv(key, "").strip()
        if not val:
            missing.append(key)
        else:
            config[key] = val
    if missing:
        log.error("Missing credentials: %s — add them to your .env file.", missing)
        sys.exit(1)
    return config


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 ── STATIC (requests-based) SCRAPERS
# ══════════════════════════════════════════════════════════════════════════════

def fetch_html(url: str, timeout: int = 25, encoding_hint: Optional[str] = None) -> Optional[str]:
    """HTTP GET with sane error handling and optional encoding override."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        if encoding_hint:
            resp.encoding = encoding_hint
        elif resp.encoding and resp.encoding.lower() in ("iso-8859-1", "latin-1"):
            resp.encoding = resp.apparent_encoding  # fix mis-detected encoding
        return resp.text
    except requests.RequestException as exc:
        log.warning("HTTP fetch failed [%s]: %s", url, exc)
        return None


def extract_text_blocks(html: str, extra_selectors: list[str] | None = None) -> list[str]:
    """Parse HTML → deduplicated text blocks with priority selector ordering."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "form", "aside", "noscript"]):
        tag.decompose()

    base_selectors = [
        "article", ".news-item", ".press-release", ".news-card", ".card",
        ".post", ".entry", "[class*='article']", "[class*='news']",
        "[class*='press']", "[class*='release']",
        "h1", "h2", "h3", "h4", "p", "li",
    ]
    selectors = (extra_selectors or []) + base_selectors

    blocks, seen = [], set()
    for selector in selectors:
        for el in soup.select(selector):
            text = el.get_text(separator=" ", strip=True)
            if len(text) > MIN_BLOCK_LEN and text not in seen:
                seen.add(text)
                blocks.append(text)
    return blocks


def is_deal_relevant(text: str) -> bool:
    tl = text.lower()
    return any(kw in tl for kw in DEAL_KEYWORDS)


# ── WordPress REST API scraper ────────────────────────────────────────────────
def scrape_wordpress_api(api_url: str, per_page: int = 30) -> list[str]:
    """Fetch posts via WP JSON API — much cleaner than scraping rendered HTML."""
    try:
        params = {"per_page": per_page, "orderby": "date", "_fields": "title,excerpt,content,link"}
        resp = requests.get(api_url, headers=HEADERS, params=params, timeout=20)
        resp.raise_for_status()
        posts = resp.json()
        blocks = []
        for post in posts:
            title   = BeautifulSoup(post.get("title", {}).get("rendered", ""), "lxml").get_text()
            excerpt = BeautifulSoup(post.get("excerpt", {}).get("rendered", ""), "lxml").get_text()
            content = BeautifulSoup(post.get("content", {}).get("rendered", ""), "lxml").get_text()
            combined = f"{title} | {excerpt} | {content[:800]}"
            if len(combined.strip()) > MIN_BLOCK_LEN:
                blocks.append(combined.strip())
        return blocks
    except Exception as exc:
        log.warning("WP API failed [%s]: %s", api_url, exc)
        return []


# ── Chinese-site scraper (GB18030 encoding) ────────────────────────────────
def scrape_chinese_site(url: str) -> list[dict]:
    """CET SGCC and similar Chinese government sites with GB/UTF-8 encoding."""
    snippets = []
    html = fetch_html(url, encoding_hint="utf-8")
    if not html:
        html = fetch_html(url, encoding_hint="gb18030")
    if not html:
        return snippets
    blocks = extract_text_blocks(html, extra_selectors=[
        ".news-list li", ".content-list li", "td", ".article-content",
    ])
    for block in blocks:
        if is_deal_relevant(block):
            snippets.append({
                "source": "website",
                "source_url": url,
                "text": block[:MAX_BLOCK_LEN],
            })
    return snippets


# ── Saudi Gulf Projects (WordPress multi-category) ────────────────────────────
def scrape_saudigulfprojects(urls: list[str]) -> list[dict]:
    """WordPress news aggregator with category pages. Try WP API then fallback."""
    snippets = []
    api_url = "https://www.saudigulfprojects.com/wp-json/wp/v2/posts"
    api_blocks = scrape_wordpress_api(api_url, per_page=50)
    for block in api_blocks:
        if is_deal_relevant(block):
            snippets.append({"source": "website", "source_url": "saudigulfprojects.com", "text": block[:MAX_BLOCK_LEN]})

    if not snippets:
        # Fallback: scrape each category page
        for url in urls:
            html = fetch_html(url)
            if not html:
                continue
            blocks = extract_text_blocks(html, extra_selectors=[
                ".entry-title", ".entry-content", ".post-title", "h2 a", ".summary",
            ])
            for block in blocks:
                if is_deal_relevant(block):
                    snippets.append({"source": "website", "source_url": url, "text": block[:MAX_BLOCK_LEN]})
    return snippets


# ── Construction Week / MEED-style news portals ───────────────────────────────
def scrape_news_portal(company_name: str, urls: list[str]) -> list[dict]:
    """Generic news portal scraper (CW Saudi, CW Online, Utilities ME, etc.)"""
    snippets = []
    for url in urls:
        log.info("[%s] Static scrape: %s", company_name, url)
        html = fetch_html(url)
        if not html:
            continue
        extra = [
            ".article-teaser", ".article-item", ".story-item",
            ".news-listing", ".card-body", ".article__title",
            ".article__excerpt", "h2", "h3", ".teaser__title",
            ".teaser__body", "[class*='story']", "[class*='article']",
        ]
        blocks = extract_text_blocks(html, extra_selectors=extra)
        for block in blocks:
            if is_deal_relevant(block):
                snippets.append({"source": "website", "source_url": url, "text": block[:MAX_BLOCK_LEN]})
    return snippets


# ── Standard company website scraper (BS4) ───────────────────────────────────
def scrape_static_website(company_name: str, urls: list[str]) -> list[dict]:
    """Requests + BS4 for straightforward HTML sites."""
    snippets = []
    for url in urls:
        log.info("[%s] Static scrape: %s", company_name, url)
        # Detect WP API availability
        domain = urlparse(url).netloc.replace("www.", "")
        if domain in WORDPRESS_API_SITES:
            blocks = scrape_wordpress_api(WORDPRESS_API_SITES[domain])
            if blocks:
                for block in blocks:
                    if is_deal_relevant(block):
                        snippets.append({"source": "website", "source_url": url, "text": block[:MAX_BLOCK_LEN]})
                continue  # skip raw HTML if API worked

        html = fetch_html(url)
        if not html:
            continue
        blocks = extract_text_blocks(html)
        for block in blocks:
            if is_deal_relevant(block):
                snippets.append({"source": "website", "source_url": url, "text": block[:MAX_BLOCK_LEN]})
    return snippets


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 ── PLAYWRIGHT-BASED SCRAPERS (JS-heavy / SPA / ASPX)
# ══════════════════════════════════════════════════════════════════════════════

async def pw_get_text_blocks(
    page: Page,
    url: str,
    company_name: str,
    scroll_rounds: int = 4,
    wait_after_load: float = 4.0,
    extra_selectors: list[str] | None = None,
) -> list[str]:
    """
    Core Playwright text extractor:
      1. Navigate to URL, wait for network idle
      2. Scroll incrementally to trigger lazy-load
      3. Extract text via CSS selectors + innerText fallback
    """
    blocks: list[str] = []
    try:
        log.info("[%s] Playwright scrape: %s", company_name, url)
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await asyncio.sleep(wait_after_load)

        # Try network idle (may timeout on infinite-scroll pages — ignore)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeoutError:
            pass

        # Incremental scroll to trigger lazy images / infinite scroll
        for _ in range(scroll_rounds):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            await asyncio.sleep(1.5)

        # Try structured selectors first
        target_selectors = (extra_selectors or []) + [
            "article", ".news-item", ".card", ".press-release",
            "[class*='article']", "[class*='news']", "[class*='press']",
            "h1", "h2", "h3", "p", "li",
        ]
        seen: set[str] = set()
        for sel in target_selectors:
            elements = await page.locator(sel).all()
            for el in elements:
                try:
                    text = (await el.inner_text()).strip()
                    if len(text) > MIN_BLOCK_LEN and text not in seen:
                        seen.add(text)
                        blocks.append(text)
                except Exception:
                    continue

        # Fallback: grab whole body text and split by newlines
        if len(blocks) < 5:
            body_text = await page.evaluate("document.body.innerText")
            for line in body_text.split("\n"):
                line = line.strip()
                if len(line) > MIN_BLOCK_LEN and line not in seen:
                    seen.add(line)
                    blocks.append(line)

    except PlaywrightTimeoutError:
        log.warning("[%s] Timeout on %s", company_name, url)
    except Exception as exc:
        log.warning("[%s] Playwright error on %s: %s", company_name, url, exc)

    return blocks


async def scrape_js_website(
    context: BrowserContext,
    company_name: str,
    urls: list[str],
    extra_selectors: list[str] | None = None,
    scroll_rounds: int = 4,
) -> list[dict]:
    """Wrapper: opens a fresh tab per URL, extracts blocks, closes tab."""
    snippets: list[dict] = []
    for url in urls:
        page = await context.new_page()
        try:
            blocks = await pw_get_text_blocks(
                page, url, company_name,
                scroll_rounds=scroll_rounds,
                extra_selectors=extra_selectors,
            )
            for block in blocks:
                if is_deal_relevant(block):
                    snippets.append({"source": "website", "source_url": url, "text": block[:MAX_BLOCK_LEN]})
        finally:
            await page.close()
    return snippets


# ── ASPX sites (Hyundai E&C) ─────────────────────────────────────────────────
async def scrape_aspx_site(
    context: BrowserContext,
    company_name: str,
    urls: list[str],
    max_pages: int = 3,
) -> list[dict]:
    """
    ASP.NET WebForms sites use __VIEWSTATE postbacks for pagination.
    Strategy: load page 1, scrape, then click 'Next' up to max_pages times.
    """
    snippets: list[dict] = []
    for url in urls:
        page = await context.new_page()
        try:
            log.info("[%s] ASPX scrape: %s", company_name, url)
            await page.goto(url, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            for page_num in range(max_pages):
                blocks = []
                # Extract table rows, list items, article blocks
                for sel in [".list-item", "td", "li", "p", "h3", "h4", ".news-title", ".board-list li"]:
                    els = await page.locator(sel).all()
                    for el in els:
                        try:
                            t = (await el.inner_text()).strip()
                            if len(t) > MIN_BLOCK_LEN:
                                blocks.append(t)
                        except Exception:
                            continue

                for block in blocks:
                    if is_deal_relevant(block):
                        snippets.append({"source": "website", "source_url": url, "text": block[:MAX_BLOCK_LEN]})

                # Try to click Next page button
                if page_num < max_pages - 1:
                    next_btn = page.locator(
                        'a:has-text("Next"), a:has-text("다음"), input[value="Next"], '
                        '.pager-next a, [class*="next"] a, [id*="next"] a'
                    ).first
                    if await next_btn.count() > 0:
                        await next_btn.click(timeout=8000)
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await asyncio.sleep(2)
                    else:
                        break

        except Exception as exc:
            log.warning("[%s] ASPX error: %s", company_name, exc)
        finally:
            await page.close()

    return snippets


# ── Etimad Tenders Portal ─────────────────────────────────────────────────────
async def scrape_etimad(context: BrowserContext) -> list[dict]:
    """
    tenders.etimad.sa is a React SPA. Strategy:
      1. Load the public tender listing
      2. Filter by energy/electricity keywords via search box
      3. Extract tender cards from DOM
    """
    snippets: list[dict] = []
    page = await context.new_page()
    try:
        log.info("[Etimad] Loading public tenders portal...")
        await page.goto("https://tenders.etimad.sa/Tender/AllTendersForPublic", timeout=45000, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # Try to dismiss cookie/consent banners
        for dismiss in ['button:has-text("Accept")', 'button:has-text("موافق")', '[class*="close"]']:
            btn = page.locator(dismiss).first
            if await btn.count() > 0:
                try:
                    await btn.click(timeout=3000)
                except Exception:
                    pass

        search_terms = ["كهرباء", "محطة", "نقل الكهرباء", "electricity", "substation", "transmission"]

        for term in search_terms:
            try:
                # Find search input
                search_input = page.locator(
                    'input[placeholder*="search" i], input[placeholder*="بحث"], '
                    'input[type="search"], input[id*="search" i], input[name*="search" i]'
                ).first
                if await search_input.count() == 0:
                    break

                await search_input.click(timeout=5000)
                await search_input.fill("")
                await search_input.fill(term)
                await asyncio.sleep(1)
                await search_input.press("Enter")
                await asyncio.sleep(4)

                # Scroll and collect
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await asyncio.sleep(1.5)

                cards = await page.locator(
                    '.tender-card, .card, [class*="tender"], [class*="row"] .col'
                ).all()
                for card in cards:
                    try:
                        text = (await card.inner_text()).strip()
                        if len(text) > MIN_BLOCK_LEN and is_deal_relevant(text):
                            snippets.append({
                                "source": "website",
                                "source_url": "https://tenders.etimad.sa",
                                "text": text[:MAX_BLOCK_LEN],
                            })
                    except Exception:
                        continue

            except Exception as exc:
                log.warning("[Etimad] Search term '%s' error: %s", term, exc)

    except Exception as exc:
        log.warning("[Etimad] Portal error: %s", exc)
    finally:
        await page.close()

    return snippets


# ── Larsen & Toubro (paginated corporate press releases) ──────────────────────
async def scrape_larsentoubro(context: BrowserContext) -> list[dict]:
    """
    L&T's site uses a standard paginated news list with JS rendering.
    Also try their newsroom API endpoint.
    """
    snippets: list[dict] = []
    urls = [
        "https://www.larsentoubro.com/corporate/media/media-releases/",
        "https://www.larsentoubro.com/corporate/media/media-releases/?category=Power+Transmission+%26+Distribution",
    ]
    page = await context.new_page()
    try:
        for url in urls:
            await page.goto(url, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeoutError:
                pass

            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1.5)

            for sel in [".media-release", ".press-card", "article", ".news-item", "h3", "p"]:
                els = await page.locator(sel).all()
                for el in els:
                    try:
                        text = (await el.inner_text()).strip()
                        if len(text) > MIN_BLOCK_LEN and is_deal_relevant(text):
                            snippets.append({"source": "website", "source_url": url, "text": text[:MAX_BLOCK_LEN]})
                    except Exception:
                        continue
    except Exception as exc:
        log.warning("[L&T] Scrape error: %s", exc)
    finally:
        await page.close()

    return snippets


# ── Aramco News (Next.js, heavy JS) ──────────────────────────────────────────
async def scrape_aramco(context: BrowserContext) -> list[dict]:
    """
    Aramco's site is Next.js. Their news page lazy-loads cards.
    Also look for contract award announcements in press releases.
    """
    snippets: list[dict] = []
    page = await context.new_page()
    urls = [
        "https://www.aramco.com/en/news-media/news",
        "https://www.aramco.com/en/what-we-do/suppliers/contracting-opportunities",
    ]
    try:
        for url in urls:
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass

            # Scroll multiple times to trigger lazy cards
            for _ in range(6):
                await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
                await asyncio.sleep(2)

            for sel in [
                "[class*='NewsCard']", "[class*='news-card']", "[class*='article']",
                "h2", "h3", "p", ".card-title", ".card-body",
            ]:
                els = await page.locator(sel).all()
                for el in els:
                    try:
                        text = (await el.inner_text()).strip()
                        if len(text) > MIN_BLOCK_LEN and is_deal_relevant(text):
                            snippets.append({"source": "website", "source_url": url, "text": text[:MAX_BLOCK_LEN]})
                    except Exception:
                        continue

    except Exception as exc:
        log.warning("[Aramco] Scrape error: %s", exc)
    finally:
        await page.close()

    return snippets


# ── SEC / National Grid SA (se.com.sa) ────────────────────────────────────────
async def scrape_sec(context: BrowserContext, urls: list[str], company_name: str) -> list[dict]:
    """
    Saudi Electricity Company site. Dynamic content, needs JS + scroll.
    Also covers the National Grid SA page.
    """
    snippets: list[dict] = []
    page = await context.new_page()
    try:
        for url in urls:
            await page.goto(url, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeoutError:
                pass

            for _ in range(4):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1.5)

            for sel in [
                ".news-card", ".media-card", ".article-card", ".press-item",
                "[class*='news']", "[class*='media']", "h2", "h3", "p", "li",
            ]:
                els = await page.locator(sel).all()
                for el in els:
                    try:
                        text = (await el.inner_text()).strip()
                        if len(text) > MIN_BLOCK_LEN and is_deal_relevant(text):
                            snippets.append({"source": "website", "source_url": url, "text": text[:MAX_BLOCK_LEN]})
                    except Exception:
                        continue

    except Exception as exc:
        log.warning("[%s] SEC scrape error: %s", company_name, exc)
    finally:
        await page.close()
    return snippets


# ── MODON (government portal) ─────────────────────────────────────────────────
async def scrape_modon(context: BrowserContext) -> list[dict]:
    """
    MODON's SharePoint-based portal. Navigate to news listing and scrape.
    """
    snippets: list[dict] = []
    page = await context.new_page()
    try:
        url = "https://modon.gov.sa/en/media/pages/news.aspx"
        await page.goto(url, timeout=40000, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(1.5)

        for sel in [".news-item", ".card", "article", "h2", "h3", "p", "li", ".ms-rtestate-field"]:
            els = await page.locator(sel).all()
            for el in els:
                try:
                    text = (await el.inner_text()).strip()
                    if len(text) > MIN_BLOCK_LEN and is_deal_relevant(text):
                        snippets.append({"source": "website", "source_url": url, "text": text[:MAX_BLOCK_LEN]})
                except Exception:
                    continue

    except Exception as exc:
        log.warning("[MODON] Scrape error: %s", exc)
    finally:
        await page.close()
    return snippets


# ── Marafiq (marafiq.com.sa) ──────────────────────────────────────────────────
async def scrape_marafiq(context: BrowserContext) -> list[dict]:
    snippets: list[dict] = []
    page = await context.new_page()
    try:
        url = "https://www.marafiq.com.sa/en/media-center/news"
        await page.goto(url, timeout=40000, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeoutError:
            pass

        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(1.5)

        body_text = await page.evaluate("document.body.innerText")
        for line in body_text.split("\n"):
            line = line.strip()
            if len(line) > MIN_BLOCK_LEN and is_deal_relevant(line):
                snippets.append({"source": "website", "source_url": url, "text": line[:MAX_BLOCK_LEN]})

    except Exception as exc:
        log.warning("[Marafiq] Scrape error: %s", exc)
    finally:
        await page.close()
    return snippets


# ── Alfanar Projects (React SPA) ─────────────────────────────────────────────
async def scrape_alfanar(context: BrowserContext) -> list[dict]:
    snippets: list[dict] = []
    page = await context.new_page()
    try:
        url = "https://alfanarprojects.com/en-us/newsroom/"
        await page.goto(url, timeout=40000, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass

        for _ in range(5):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(2)

        # React renders cards into generic divs — grab all text-bearing elements
        for sel in [
            "[class*='news']", "[class*='card']", "[class*='article']",
            "[class*='post']", "h1", "h2", "h3", "h4", "p",
        ]:
            els = await page.locator(sel).all()
            for el in els:
                try:
                    text = (await el.inner_text()).strip()
                    if len(text) > MIN_BLOCK_LEN and is_deal_relevant(text):
                        snippets.append({"source": "website", "source_url": url, "text": text[:MAX_BLOCK_LEN]})
                except Exception:
                    continue

    except Exception as exc:
        log.warning("[Alfanar] Scrape error: %s", exc)
    finally:
        await page.close()
    return snippets


# ── Construction Week portals ─────────────────────────────────────────────────
async def scrape_construction_week(context: BrowserContext, company_name: str, urls: list[str]) -> list[dict]:
    """CW Saudi & CW Online both use same Citywealth/ITP Media CMS."""
    snippets: list[dict] = []
    page = await context.new_page()
    try:
        for url in urls:
            await page.goto(url, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeoutError:
                pass

            for _ in range(4):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1.5)

            for sel in [
                ".article-teaser", ".article-item", ".story__title", ".story__body",
                ".card-title", ".card-text", "article", "h2", "h3", "p",
            ]:
                els = await page.locator(sel).all()
                for el in els:
                    try:
                        text = (await el.inner_text()).strip()
                        if len(text) > MIN_BLOCK_LEN and is_deal_relevant(text):
                            snippets.append({"source": "website", "source_url": url, "text": text[:MAX_BLOCK_LEN]})
                    except Exception:
                        continue

    except Exception as exc:
        log.warning("[%s] CW scrape error: %s", company_name, exc)
    finally:
        await page.close()
    return snippets


# ── Tata Projects & generic corporate JS sites ────────────────────────────────
async def scrape_tata_projects(context: BrowserContext) -> list[dict]:
    snippets: list[dict] = []
    urls = ["https://www.tataprojects.com/media/press-releases/"]
    return await scrape_js_website(
        context, "Tata Projects", urls,
        extra_selectors=[
            ".press-release-item", ".media-release", ".news-item", ".content-block",
        ],
        scroll_rounds=5,
    )


# ── Nesma & Partners (Drupal CMS, JS rendered) ────────────────────────────────
async def scrape_nesma_partners(context: BrowserContext) -> list[dict]:
    urls = [
        "https://www.nesmapartners.com/en/media-room",
        "https://www.nesma.com/news",
    ]
    return await scrape_js_website(
        context, "Nesma & Partners", urls,
        extra_selectors=[
            ".views-row", ".node--type-news", ".field--name-title",
            ".field--name-body", ".media-room-item", ".news-card",
        ],
        scroll_rounds=4,
    )


# ── Rawabi Electric (JS site) ─────────────────────────────────────────────────
async def scrape_rawabi(context: BrowserContext) -> list[dict]:
    urls = ["https://www.rawabielectric.com/news-media"]
    return await scrape_js_website(
        context, "Rawabi Electric", urls,
        extra_selectors=[".news-grid", ".news-item", ".media-item", "h2", "h3", "p"],
        scroll_rounds=4,
    )


# ── Bahra Electric ────────────────────────────────────────────────────────────
async def scrape_bahra(context: BrowserContext) -> list[dict]:
    """Try WP REST API first, then Playwright fallback."""
    snippets: list[dict] = []
    api_blocks = scrape_wordpress_api("https://www.bahra-electric.com/wp-json/wp/v2/posts")
    for b in api_blocks:
        if is_deal_relevant(b):
            snippets.append({"source": "website", "source_url": "bahra-electric.com", "text": b[:MAX_BLOCK_LEN]})

    if not snippets:
        snippets.extend(await scrape_js_website(
            context, "Bahra Electric", ["https://www.bahra-electric.com/news"],
            extra_selectors=[".news-item", ".post", "article", "h2", "h3"],
        ))
    return snippets


# ── WESCOSA ────────────────────────────────────────────────────────────────────
async def scrape_wescosa(context: BrowserContext) -> list[dict]:
    snippets: list[dict] = []
    # Try static first
    html = fetch_html("https://www.wescosa.com/news")
    if html:
        blocks = extract_text_blocks(html, extra_selectors=[
            ".news-item", ".news-listing", "article", ".post", "h2", "h3", "p",
        ])
        for b in blocks:
            if is_deal_relevant(b):
                snippets.append({"source": "website", "source_url": "wescosa.com", "text": b[:MAX_BLOCK_LEN]})

    if not snippets:
        snippets.extend(await scrape_js_website(
            context, "WESCOSA", ["https://www.wescosa.com/news"],
            extra_selectors=[".news-item", "article", "h2", "h3", "p"],
        ))
    return snippets


# ── Homepage-only companies ────────────────────────────────────────────────────
def scrape_homepage(company_name: str, urls: list[str]) -> list[dict]:
    """
    For companies with no dedicated news page, scrape the homepage and any
    linked sub-pages (1 level deep) looking for relevant text.
    """
    snippets: list[dict] = []
    for url in urls:
        log.info("[%s] Homepage scrape: %s", company_name, url)
        html = fetch_html(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "lxml")

        # Collect all visible text from homepage
        for tag in soup(["script", "style", "nav", "footer", "header", "form"]):
            tag.decompose()

        body_text = soup.get_text(separator="\n", strip=True)
        for line in body_text.split("\n"):
            line = line.strip()
            if len(line) > MIN_BLOCK_LEN and is_deal_relevant(line):
                snippets.append({"source": "website", "source_url": url, "text": line[:MAX_BLOCK_LEN]})

        # Follow links to news/projects sub-pages (one level deep)
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        sub_keywords = ["news", "project", "media", "press", "update", "contract", "award"]
        found_links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(base, href)
            if (
                urlparse(full).netloc == urlparse(base).netloc
                and any(k in href.lower() for k in sub_keywords)
                and full not in found_links
            ):
                found_links.append(full)

        for sub_url in found_links[:5]:  # cap at 5 sub-pages
            sub_html = fetch_html(sub_url)
            if not sub_html:
                continue
            blocks = extract_text_blocks(sub_html)
            for block in blocks:
                if is_deal_relevant(block):
                    snippets.append({"source": "website", "source_url": sub_url, "text": block[:MAX_BLOCK_LEN]})

    return snippets


# ── Rezayat / NCC page ────────────────────────────────────────────────────────
def scrape_rezayat_ncc(company_name: str, urls: list[str]) -> list[dict]:
    """NCC appears as a subsidiary page on Rezayat's site — static scrape."""
    snippets: list[dict] = []
    for url in urls:
        html = fetch_html(url)
        if not html:
            continue
        extra = [".company-intro", ".services-list", ".projects-list", "p", "li", "h2", "h3"]
        blocks = extract_text_blocks(html, extra_selectors=extra)
        for b in blocks:
            if is_deal_relevant(b):
                snippets.append({"source": "website", "source_url": url, "text": b[:MAX_BLOCK_LEN]})
    return snippets


# ── Saudi Projects (WordPress search results) ──────────────────────────────────
def scrape_saudi_projects_net() -> list[dict]:
    """WordPress search with multiple query terms."""
    snippets: list[dict] = []
    search_terms = ["substation", "transmission", "ohtl", "electrification"]

    # Try WP REST API with keyword filter
    for term in search_terms:
        api_url = f"https://saudiprojects.net/wp-json/wp/v2/posts?search={term}&per_page=20"
        blocks = scrape_wordpress_api(api_url, per_page=20)
        for b in blocks:
            if is_deal_relevant(b):
                snippets.append({"source": "website", "source_url": f"saudiprojects.net?s={term}", "text": b[:MAX_BLOCK_LEN]})

    # Fallback: scrape search result pages
    if not snippets:
        for term in search_terms:
            url = f"https://saudiprojects.net/?s={term}"
            html = fetch_html(url)
            if not html:
                continue
            blocks = extract_text_blocks(html, extra_selectors=[
                ".entry-title", ".entry-content", ".post", "h2", "h3", "p",
            ])
            for b in blocks:
                if is_deal_relevant(b):
                    snippets.append({"source": "website", "source_url": url, "text": b[:MAX_BLOCK_LEN]})

    return snippets


# ── Utilities Middle East ─────────────────────────────────────────────────────
def scrape_utilities_me(urls: list[str]) -> list[dict]:
    """Try WP API, fallback to BS4."""
    snippets: list[dict] = []
    api_blocks = scrape_wordpress_api(WORDPRESS_API_SITES["utilitiesme.com"], per_page=40)
    for b in api_blocks:
        if is_deal_relevant(b):
            snippets.append({"source": "website", "source_url": "utilitiesme.com", "text": b[:MAX_BLOCK_LEN]})

    if not snippets:
        snippets.extend(scrape_news_portal("Utilities ME", urls))

    return snippets


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 ── LINKEDIN SCRAPER
# ══════════════════════════════════════════════════════════════════════════════

async def check_linkedin_session(context: BrowserContext) -> bool:
    page = await context.new_page()
    try:
        await page.goto("https://www.linkedin.com/feed/", timeout=20000)
        await page.wait_for_load_state("domcontentloaded")
        if "feed" in page.url and await page.locator("nav.global-nav").count() > 0:
            return True
        return False
    except Exception:
        return False
    finally:
        await page.close()


async def linkedin_login(context: BrowserContext, username: str, password: str) -> bool:
    page = await context.new_page()
    try:
        log.info("Opening LinkedIn login...")
        await page.goto("https://www.linkedin.com/login", timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)

        if "feed" in page.url:
            log.info("[✓] Already authenticated on LinkedIn.")
            return True

        session_key = page.locator('input[name="session_key"]')
        if await session_key.count() > 0:
            await session_key.fill(username)
            await page.fill('input[name="session_password"]', password)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await asyncio.sleep(3)

        if "checkpoint" in page.url or "captcha" in page.url:
            log.warning("\n[🚨] CAPTCHA detected — solve it in the browser, then press ENTER.")
            input(">>> Press ENTER after resolving the challenge...")
            await asyncio.sleep(3)

        if "feed" in page.url or await page.locator("nav.global-nav").count() > 0:
            log.info("[✓] LinkedIn login verified.")
            return True

        return False
    except Exception as exc:
        log.error("LinkedIn login error: %s", exc)
        return "feed" in page.url
    finally:
        await page.close()


async def scrape_linkedin_posts(
    context: BrowserContext,
    company_name: str,
    posts_url: str,
    max_posts: int = 20,
) -> list[dict]:
    """Scrape company LinkedIn post feed for deal/contract announcements."""
    snippets: list[dict] = []
    page = await context.new_page()
    try:
        log.info("[%s] LinkedIn feed: %s", company_name, posts_url)
        await page.goto(posts_url, timeout=40000)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(5)

        # Scroll to load more posts
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, 1400)")
            await asyncio.sleep(2)

        # Multiple selector strategies for LinkedIn's evolving DOM
        selectors = [
            ".feed-shared-text",
            ".update-components-text",
            "[class*='feed-shared-update-v2'] span[dir='ltr']",
            ".break-words span[dir='ltr']",
            ".attributed-text-segment-list__content",
            ".update-components-text__text-view",
        ]
        seen_texts: set[str] = set()
        for selector in selectors:
            elements = await page.locator(selector).all()
            for el in elements:
                try:
                    text = (await el.inner_text()).strip()
                    if len(text) > 80 and text not in seen_texts:
                        seen_texts.add(text)
                        if is_deal_relevant(text):
                            snippets.append({
                                "source": "linkedin",
                                "source_url": posts_url,
                                "text": text[:MAX_BLOCK_LEN],
                            })
                        if len(snippets) >= max_posts:
                            return snippets
                except Exception:
                    continue

    except Exception as exc:
        log.warning("[%s] LinkedIn scrape error: %s", company_name, exc)
    finally:
        await page.close()

    return snippets


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 ── MEED PREMIUM SCRAPER
# ══════════════════════════════════════════════════════════════════════════════

async def meed_login_handler(context: BrowserContext, config: dict) -> bool:
    page = await context.new_page()
    try:
        log.info("Accessing MEED Premium Gateway...")
        await page.goto("https://premium.meedprojects.com/", timeout=40000)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(4)

        # 1. Detect if we are already logged in
        if "homepage" in page.url or "dashboard" in page.url:
            log.info("[✓] Active session detected.")
            await page.close()
            return True

        # 2. Use more specific selectors and force human-like interaction
        user_sel = 'input[id*="username" i], input[name*="user" i]'
        pass_sel = 'input[id*="password" i], input[name*="pass" i]'
        
        # Wait for fields to be visible
        await page.wait_for_selector(user_sel)
        
        # Fill with "delay" to simulate human typing
        await page.locator(user_sel).first.fill(config["MEED_USERNAME"], delay=100)
        await page.locator(pass_sel).first.fill(config["MEED_PASSWORD"], delay=100)
        
        # 3. Handle the login button click
        # Often these forms need a slight pause after filling for JS to enable the button
        await asyncio.sleep(2)
        
        # Try both the button ID and a generic 'Sign In' button text
        login_btn = page.locator('#btnLogin, button:has-text("Sign in"), input[type="submit"]')
        
        # Click and wait for navigation
        await login_btn.first.click()
        
        log.info("[MEED] Login trigger sent. Monitoring gateway...")
        
        # Wait for URL to change (confirming login)
        try:
            await page.wait_for_url("**/Home**", timeout=20000)
            await page.wait_for_load_state("networkidle")
            log.info("[✓] Login successful.")
        except:
            log.warning("Login redirect not detected, but attempting to proceed...")

        await page.close()
        return True

    except Exception as e:
        log.error(f"MEED Login failed: {e}")
        await page.close()
        return False

async def scrape_meed_unified_tabs(context: BrowserContext, config: dict) -> list[dict]:
    """
    Single-tab walk of MEED Premium:
      Track 1 → Projects grid with keyword filters
      Track 2 → News Feed with keyword filters
    """
    snippets: list[dict] = []
    page = await context.new_page()

    SEARCH_TERMS = ["Substation", "OHTL", "Transmission Line", "GIS", "Electrification", "Power"]

    async def _apply_filter_and_scrape(track_name: str, source_label: str):
        for term in SEARCH_TERMS:
            try:
                log.info("[MEED %s] Filtering: '%s'", track_name, term)
                kw_input = page.locator(
                    'input[id*="Keyword" i], input[placeholder*="Keyword" i], '
                    '.filter-keyword-input, input[name*="keyword" i]'
                ).first
                await kw_input.click(timeout=10000)
                await kw_input.fill("")
                await kw_input.type(term, delay=50)

                apply_btn = page.locator(
                    'button:has-text("Apply"), input[type="submit"][value="Search"], '
                    '.search-btn, button:has-text("Search"), button:has-text("Filter")'
                ).first
                await apply_btn.click(timeout=10000)
                await page.wait_for_timeout(5000)

                # Scroll through results
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await asyncio.sleep(1.5)

                text_dump = await page.evaluate("document.body.innerText")
                for line in text_dump.split("\n"):
                    line = line.strip()
                    if len(line) > 70 and is_deal_relevant(line):
                        snippets.append({
                            "source": "meed_premium",
                            "source_url": source_label,
                            "text": line[:MAX_BLOCK_LEN],
                        })
            except Exception as exc:
                log.warning("[MEED %s] Filter '%s' error: %s", track_name, term, exc)

    try:
        await page.goto("https://premium.meedprojects.com/", timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(4)

        # Track 1: Projects Grid
        log.info("[MEED] Navigating to Projects grid...")
        try:
            await page.locator('nav a:has-text("Projects"), a[href*="Project"]').first.click(timeout=8000)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(4)
            await _apply_filter_and_scrape("Projects", "MEED Projects Database")
        except Exception as exc:
            log.warning("[MEED] Projects nav error: %s", exc)

        # Track 2: News Feed
        log.info("[MEED] Navigating to News feed...")
        try:
            await page.locator('nav a:has-text("Project News"), a[href*="News"]').first.click(timeout=8000)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(4)
            await _apply_filter_and_scrape("News", "MEED News Listing")
        except Exception as exc:
            log.warning("[MEED] News nav error: %s", exc)

        # Track 3: Tenders (bonus)
        log.info("[MEED] Navigating to Tenders/Contracts...")
        try:
            tender_link = page.locator('nav a:has-text("Tender"), nav a:has-text("Contract"), a[href*="Tender"]').first
            if await tender_link.count() > 0:
                await tender_link.click(timeout=8000)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(4)
                await _apply_filter_and_scrape("Tenders", "MEED Tenders")
        except Exception as exc:
            log.warning("[MEED] Tenders nav error: %s", exc)

    except Exception as exc:
        log.error("[MEED] Unified handler error: %s", exc)
    finally:
        await page.close()

    return snippets


def parse_snippets_with_ai(client: genai.Client, company_name: str, snippets: list[dict]) -> list[dict]:
    if not snippets: return []
    
    # 1. Pre-filter relevant snippets to save tokens
    essential_keywords = ["transmission", "ohtl", "substation", "electrification", "upgrade", "gis", "grid", "contract", "awarded"]
    filtered_snippets = [s for s in snippets if any(kw in s["text"].lower() for kw in essential_keywords)]
    if not filtered_snippets: return []

    # 2. Batching Setup
    batch_size = 3
    final_deals = []
    today_str = datetime.now().strftime("%B %d, %Y")

    # 3. Restored Prompt
    prompt = f"""
You are a principal market intelligence analyst filtering high-voltage utility data for Algihaz Holding.
CRITICAL CONTEXT: Today's date is {today_str}. Use this to resolve relative timelines.

STRICT FILTERING MANDATE:
Extract a deal ONLY if it directly involves:
1. Overhead Transmission Lines (OHTL) or grid cabling.
2. Substations (GIS, AIS, switching stations, distribution networks).
3. Industrial Electrification, power upgrades, retrofits, or utility plant connections.
DISCARD general civil construction (highways, residential, hospitals unrelated to power).

EXTRACTION RULES:
- client_entity: Identify the AWARDING body (SEC, National Grid SA, Saudi Aramco, Marafiq, NEOM, MODON, etc.).
- deal_date (STRICT): DO NOT lazy-default to today's date. Search for: "Award Date", "Bid Date", "Completion Date", or explicit year/month markers. Resolve relative terms ("last month", "Q3 2025") using {today_str} as anchor. If no date found → use "Pipeline/Active Tracking".
- deal_status: One of: Awarded, Signed, Tender Bid, Under Execution, Pipeline, Completed.
- declared_value: Include currency (SAR, USD, etc.). Use "Undisclosed" if not found.
- strategic_implication_for_algihaz: Analyze the competitive threat or market signal. Be specific: which region, which client, what Algihaz should do.
"""

    # 4. Processing Loop with Retry Logic
    for i in range(0, len(filtered_snippets), batch_size):
        batch = filtered_snippets[i : i + batch_size]
        combined_text = "\n\n---\n\n".join(f"[Source: {s['source'].upper()}]\n{s['text']}" for s in batch)
        
        for attempt in range(3):
            try:
                log.info(f"[AI] Processing batch {i//batch_size + 1} for {company_name}...")
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt + f"\n\nDATA FRAGMENTS:\n{combined_text[:4000]}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=dict(
                            type="OBJECT",
                            properties=dict(
                                deals=dict(
                                    type="ARRAY",
                                    items=dict(
                                        type="OBJECT",
                                        properties=dict(
                                            project_title=dict(type="STRING"),
                                            client_entity=dict(type="STRING"),
                                            deal_status=dict(type="STRING"),
                                            declared_value=dict(type="STRING"),
                                            deal_date=dict(type="STRING"),
                                            strategic_implication_for_algihaz=dict(type="STRING"),
                                        ),
                                        required=["project_title", "client_entity", "deal_status", "declared_value", "deal_date", "strategic_implication_for_algihaz"]
                                    )
                                )
                            ),
                            required=["deals"]
                        ),
                        temperature=0.1
                    )
                )
                data = json.loads(response.text)
                for d in data.get("deals", []):
                    d["competitor"] = company_name
                    d["scraped_at"] = datetime.now(UTC).isoformat() + "Z"
                final_deals.extend(data.get("deals", []))
                break 
            
            except Exception as e:
                if "429" in str(e):
                    wait = (attempt + 1) * 30
                    log.warning(f"429 hit. Retrying batch in {wait}s...")
                    time.sleep(wait)
                else:
                    log.error(f"AI Error: {e}")
                    break
    return final_deals
# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 ── DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def normalize_project_title(title: str) -> str:
    text = str(title).lower()
    noise = [
        "project", "package", "solutions", "inc", "co", "ltd", "u/g",
        "underground", "overhead", "ohtl", "station", "substation",
        "line", "lines", "transmission", "electrification", "upgrade",
        "works", "contract", "phase",
    ]
    for word in noise:
        text = re.sub(rf"\b{word}\b", "", text)
    return "".join(c for c in text if c.isalnum())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 ── SCRAPER ROUTER
# ══════════════════════════════════════════════════════════════════════════════

async def route_scraper(
    company_name: str,
    sources: dict,
    context: BrowserContext,
    config: dict,
    meed_session_active: bool,
    li_session_active: bool,
) -> list[dict]:
    """
    Routes each company to the correct scraper based on its domain and config.
    Returns a unified list of raw text snippets.
    """
    all_snippets: list[dict] = []
    website_urls: list[str] = sources.get("website_urls", [])

    # ── MEED Premium ─────────────────────────────────────────────────────────
    if sources.get("is_premium_paywall"):
        if meed_session_active:
            all_snippets.extend(await scrape_meed_unified_tabs(context, config))
        return all_snippets  # No other sources for MEED

    # ── Website scraping — route by company name / domain ────────────────────
    if website_urls:
        first_domain = urlparse(website_urls[0]).netloc.replace("www.", "").lower()

        # Named company-specific routers
        if company_name == "Alfanar Projects":
            all_snippets.extend(await scrape_alfanar(context))

        elif company_name in ("Nesma & Partners", "Nesma Infrastructure & Technology"):
            all_snippets.extend(await scrape_nesma_partners(context))

        elif company_name == "L&T Power Transmission & Distribution":
            all_snippets.extend(await scrape_larsentoubro(context))

        elif company_name == "Tata Projects":
            all_snippets.extend(await scrape_tata_projects(context))

        elif company_name == "Saudi Electricity Company (SEC)":
            all_snippets.extend(await scrape_sec(context, website_urls, company_name))

        elif company_name == "National Grid SA":
            all_snippets.extend(await scrape_sec(context, website_urls, company_name))

        elif company_name == "MODON (Saudi Authority for Industrial Cities)":
            all_snippets.extend(await scrape_modon(context))

        elif company_name == "Marafiq":
            all_snippets.extend(await scrape_marafiq(context))

        elif company_name == "Saudi Aramco":
            all_snippets.extend(await scrape_aramco(context))

        elif company_name == "Saudi Aramco Supplier Hub":
            all_snippets.extend(await scrape_aramco(context))

        elif company_name == "Rawabi Electric":
            all_snippets.extend(await scrape_rawabi(context))

        elif company_name == "Bahra Electric":
            all_snippets.extend(await scrape_bahra(context))

        elif company_name == "WESCOSA":
            all_snippets.extend(await scrape_wescosa(context))

        elif company_name in ("Construction Week Saudi", "Construction Week Middle East"):
            all_snippets.extend(await scrape_construction_week(context, company_name, website_urls))

        elif company_name == "Saudi Gulf Projects":
            all_snippets.extend(scrape_saudigulfprojects(website_urls))

        elif company_name == "Saudi Projects (Aggregator)":
            all_snippets.extend(scrape_saudi_projects_net())

        elif company_name == "Utilities Middle East":
            all_snippets.extend(scrape_utilities_me(website_urls))

        elif company_name == "Saudi Government (Etimad)":
            all_snippets.extend(await scrape_etimad(context))

        elif company_name == "China Electric Power Equipment and Technology (CET)":
            for url in website_urls:
                all_snippets.extend(scrape_chinese_site(url))

        elif company_name == "Hyundai Engineering & Construction":
            all_snippets.extend(await scrape_aspx_site(context, company_name, website_urls))

        elif company_name == "National Contracting Company (NCC)":
            all_snippets.extend(scrape_rezayat_ncc(company_name, website_urls))

        elif company_name in (
            "Al-Ojaimi Group", "MEMF Electrical Industries", "CEPCO",
            "Sedar Group", "A. Al-Saihati Contracting (SIGMA)",
        ):
            all_snippets.extend(scrape_homepage(company_name, website_urls))

        # Domain-based fallback routing
        elif first_domain in JS_REQUIRED_DOMAINS:
            all_snippets.extend(
                await scrape_js_website(context, company_name, website_urls)
            )
        elif first_domain in ASPX_DOMAINS:
            all_snippets.extend(
                await scrape_aspx_site(context, company_name, website_urls)
            )
        else:
            # Default: try WP API then static
            all_snippets.extend(scrape_static_website(company_name, website_urls))

    # ── LinkedIn posts ────────────────────────────────────────────────────────
    if li_session_active and "linkedin_posts_url" in sources:
        li_snippets = await scrape_linkedin_posts(
            context, company_name, sources["linkedin_posts_url"]
        )
        all_snippets.extend(li_snippets)
        await asyncio.sleep(3)  # Be polite to LinkedIn's rate limits

    return all_snippets


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 ── ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

async def run_agent(config: dict) -> dict:
    gemini_client = genai.Client(api_key=config["GEMINI_API_KEY"])

    # Load historical ledger
    existing_report: dict = {"intelligence": {}}
    if OUTPUT_FILE.exists():
        try:
            existing_report = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            log.info("[✓] Historical intelligence ledger loaded for delta comparison.")
        except Exception as exc:
            log.warning("Could not parse historical report, starting fresh: %s", exc)

    # Build dedup signature set from historical data
    seen_signatures: set[tuple] = set()
    historical_pool: dict[str, list] = {}
    for comp, data in existing_report.get("intelligence", {}).items():
        historical_pool[comp] = data.get("deals", [])
        for deal in data.get("deals", []):
            norm = normalize_project_title(deal.get("project_title", ""))
            seen_signatures.add((comp.lower(), norm))

    report = {
        "report_metadata": {
            "generated_at": datetime.now(UTC).isoformat() + "Z",
            "run_type": "Daily Delta Analysis",
        },
        "intelligence": {},
    }

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            viewport={"width": 1280, "height": 900},
        )

        # ── Auth: LinkedIn ────────────────────────────────────────────────────
        li_active = await check_linkedin_session(context)
        if not li_active:
            li_active = await linkedin_login(context, config["LINKEDIN_USERNAME"], config["LINKEDIN_PASSWORD"])
        else:
            log.info("[✓] LinkedIn session confirmed.")

        # ── Auth: MEED ────────────────────────────────────────────────────────
        meed_active = await meed_login_handler(context, config)

        # ── Per-company scraping loop ─────────────────────────────────────────
        for company_name, sources in TARGETS.items():
            log.info("\n%s\n[SCAN] %s\n%s", "─" * 60, company_name, "─" * 60)

            raw_snippets = await route_scraper(
                company_name=company_name,
                sources=sources,
                context=context,
                config=config,
                meed_session_active=meed_active,
                li_session_active=li_active,
            )
            log.info("[%s] Raw snippets collected: %d", company_name, len(raw_snippets))

            # ── AI analysis ──────────────────────────────────────────────────
            new_deals = parse_snippets_with_ai(gemini_client, company_name, raw_snippets)

            # ── Deduplication & merge ─────────────────────────────────────────
            final_deals: list[dict] = []
            new_count = 0

            for deal in new_deals:
                norm = normalize_project_title(deal.get("project_title", ""))
                sig = (company_name.lower(), norm)
                if sig not in seen_signatures:
                    deal["is_new"] = True
                    new_count += 1
                    seen_signatures.add(sig)
                else:
                    deal["is_new"] = False
                final_deals.append(deal)

            # Backfill historical deals not found this run
            for old_deal in historical_pool.get(company_name, []):
                old_sig = (
                    company_name.lower(),
                    normalize_project_title(old_deal.get("project_title", "")),
                )
                already_present = any(
                    (company_name.lower(), normalize_project_title(x.get("project_title", ""))) == old_sig
                    for x in final_deals
                )
                if not already_present:
                    old_deal["is_new"] = False
                    final_deals.append(old_deal)

            log.info(
                "[%s] Result → %d total deals (%d NEW today)",
                company_name, len(final_deals), new_count,
            )

            report["intelligence"][company_name] = {
                "deals_identified": len(final_deals),
                "new_deals_today": new_count,
                "deals": final_deals,
            }

        await context.close()

    # ── Save report ───────────────────────────────────────────────────────────
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    banner = "═" * 70
    print(f"\n{banner}\nCOMPETITOR INTELLIGENCE RUN COMPLETED\n{banner}")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    config = load_env()
    asyncio.run(run_agent(config))


if __name__ == "__main__":
    main()