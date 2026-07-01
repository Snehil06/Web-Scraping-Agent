"""
targets.py — Algihaz Competitive Intelligence Target Registry
═══════════════════════════════════════════════════════════════════════════════
Each target dict now carries a "scraper" key. The router in
competitive_intelligence_agent.py reads this key and dispatches to the right
function — no hardcoded company names in the router ever again.

SCRAPER KEY REFERENCE
─────────────────────
"js_generic"        Generic Playwright scraper  (scroll + multi-selector)
"aspx"              ASP.NET paginated sites      (Hyundai)
"alfanar"           React SPA newsroom
"nesma"             Drupal/JS CMS                (Nesma & Partners, Nesma NIT)
"larsentoubro"      Paginated JS news + PT&D filter
"tata"              Corporate JS press releases
"aramco"            Next.js heavy scroll         (Aramco news + supplier hub)
"sec"               Dynamic gov portal           (se.com.sa)
"modon"             SharePoint gov portal
"marafiq"           JS utility news portal
"rawabi"            Generic JS site
"bahra"             WP REST API → JS fallback
"wescosa"           Static attempt → JS fallback
"construction_week" ITP Media CMS                (CW Saudi, CW Online)
"saudi_gulf"        WP REST API → category pages (saudigulfprojects.com)
"saudi_projects"    WP search API → HTML fallback
"utilities_me"      WP REST API → HTML fallback
"etimad"            React SPA, Arabic+EN search  (tenders.etimad.sa)
"chinese"           GB18030/UTF-8 dual-attempt   (CET SGCC)
"homepage"          Homepage + 1-level deep crawl (small cos, no news page)
"rezayat"           Static subsidiary page       (NCC on rezayat.com)
"static"            Requests + BS4 / WP API auto-detect
"meed"              Premium paywall              (premium.meedprojects.com)
"""

TARGETS: dict[str, dict] = {

    # ── COMPETITORS ────────────────────────────────────────────────────────────

    "Alfanar Projects": {
        "scraper": "alfanar",
        "website_urls": [
            "https://alfanarprojects.com/en-us/newsroom/",
        ],
        "linkedin_slug": "alfanar",
        "linkedin_posts_url": "https://www.linkedin.com/company/alfanar/posts/?feedView=all",
    },

    "Nesma & Partners": {
        "scraper": "nesma",
        "website_urls": [
            "https://www.nesmapartners.com/en/media-room",
            "https://www.nesma.com/news",
        ],
        "linkedin_slug": "nesma-partners",
        "linkedin_posts_url": "https://www.linkedin.com/company/nesma-partners/posts/?feedView=all",
    },

    "Saudi Services for Electro Mechanic Works (SSEM)": {
        "scraper": "static",          # WP REST API auto-detected via ssem.com.sa
        "website_urls": [
            "https://ssem.com.sa/news-media/",
        ],
        "linkedin_slug": "ssem",
        "linkedin_posts_url": "https://www.linkedin.com/company/ssem/posts/?feedView=all",
    },

    "L&T Power Transmission & Distribution": {
        "scraper": "larsentoubro",
        "website_urls": [
            "https://www.larsentoubro.com/corporate/media/media-releases/",
        ],
        "linkedin_slug": "larsen-&-toubro",
        "linkedin_posts_url": "https://www.linkedin.com/company/larsen-&-toubro/posts/?feedView=all",
    },

    "National Contracting Company (NCC)": {
        "scraper": "rezayat",
        "website_urls": [
            "https://www.rezayat.com/company/ncc-td/",
        ],
        "linkedin_slug": "national-contracting-co--ltd-",
        "linkedin_posts_url": "https://www.linkedin.com/company/national-contracting-co--ltd-/posts/?feedView=all",
    },

    "Nesma Infrastructure & Technology": {
        "scraper": "nesma",
        "website_urls": [
            "https://www.nesmanit.com/media-center",
        ],
        "linkedin_slug": "nesma-infrastructure-&-technology",
        "linkedin_posts_url": "https://www.linkedin.com/company/nesma-infrastructure-&-technology/posts/?feedView=all",
    },

    "China Electric Power Equipment and Technology (CET)": {
        "scraper": "chinese",
        "website_urls": [
            "http://cet.sgcc.com.cn/html/cet_en/col1500000019/en_index.html",
        ],
        "linkedin_slug": "china-electric-power-equipment-and-technology-co-ltd-",
        "linkedin_posts_url": "https://www.linkedin.com/company/china-electric-power-equipment-and-technology-co-ltd-/posts/?feedView=all",
    },

    "Tata Projects": {
        "scraper": "tata",
        "website_urls": [
            "https://www.tataprojects.com/media/press-releases/",
        ],
        "linkedin_slug": "tata-projects",
        "linkedin_posts_url": "https://www.linkedin.com/company/tata-projects/posts/?feedView=all",
    },

    "Rawabi Electric": {
        "scraper": "rawabi",
        "website_urls": [
            "https://www.rawabielectric.com/news-media",
        ],
        "linkedin_slug": "rawabi-electric",
        "linkedin_posts_url": "https://www.linkedin.com/company/rawabi-electric/posts/?feedView=all",
    },

    "WESCOSA": {
        "scraper": "wescosa",
        "website_urls": [
            "https://www.wescosa.com/news",
        ],
        "linkedin_slug": "wahah-electric-supply-company-of-saudi-arabia-wescosa-",
        "linkedin_posts_url": "https://www.linkedin.com/company/wahah-electric-supply-company-of-saudi-arabia-wescosa-/posts/?feedView=all",
    },

    "Hyundai Engineering & Construction": {
        "scraper": "aspx",
        "website_urls": [
            "https://en.hdec.kr/en/newsroom/newsList.aspx",
        ],
        "linkedin_slug": "hyundai-engineering-&-construction-co--ltd",
        "linkedin_posts_url": "https://www.linkedin.com/company/hyundai-engineering-&-construction-co--ltd/posts/?feedView=all",
    },

    "Bahra Electric": {
        "scraper": "bahra",
        "website_urls": [
            "https://www.bahra-electric.com/news",
        ],
        "linkedin_slug": "bahra-electric",
        "linkedin_posts_url": "https://www.linkedin.com/company/bahra-electric/posts/?feedView=all",
    },

    "Al-Ojaimi Group": {
        "scraper": "homepage",
        "website_urls": [
            "https://alojaimi.com/",
        ],
        "linkedin_slug": "mohammed-al-ojaimi-group",
        "linkedin_posts_url": "https://www.linkedin.com/company/mohammed-al-ojaimi-group/posts/?feedView=all",
    },

    "MEMF Electrical Industries": {
        "scraper": "homepage",
        "website_urls": [
            "http://www.memf.com.sa/",
        ],
        "linkedin_slug": "memf-electrical-industries",
        "linkedin_posts_url": "https://www.linkedin.com/company/memf-electrical-industries/posts/?feedView=all",
    },

    "CEPCO": {
        "scraper": "homepage",
        "website_urls": [
            "https://www.cepco-sa.com/",
        ],
        "linkedin_slug": "cepco---civil-&-electrical-projects-contracting-co-",
        "linkedin_posts_url": "https://www.linkedin.com/company/cepco---civil-&-electrical-projects-contracting-co-/posts/?feedView=all",
    },

    "Sedar Group": {
        "scraper": "homepage",
        "website_urls": [
            "https://www.sedargroup.com/",
        ],
        "linkedin_slug": "sedargroup",
        "linkedin_posts_url": "https://www.linkedin.com/company/sedargroup/posts/?feedView=all",
    },

    "A. Al-Saihati Contracting (SIGMA)": {
        "scraper": "homepage",
        "website_urls": [
            "https://www.sigma-sa.com/",
        ],
        "linkedin_slug": "a--al-saihati-contracting-co--sigma-",
        "linkedin_posts_url": "https://www.linkedin.com/company/a--al-saihati-contracting-co--sigma-/posts/?feedView=all",
    },

    # ── CLIENTS (AWARDING AUTHORITIES) ────────────────────────────────────────

    "Saudi Electricity Company (SEC)": {
        "scraper": "sec",
        "website_urls": [
            "https://www.se.com.sa/en/media-center/news",
        ],
        "linkedin_slug": "saudi-electricity-company",
        "linkedin_posts_url": "https://www.linkedin.com/company/saudi-electricity-company/posts/?feedView=all",
    },

    "National Grid SA": {
        "scraper": "sec",                   # Same portal stack as SEC
        "website_urls": [
            "https://www.se.com.sa/en/national-grid",
        ],
        "linkedin_slug": "national-grid-sa",
        "linkedin_posts_url": "https://www.linkedin.com/company/national-grid-sa/posts/?feedView=all",
    },

    "MODON (Saudi Authority for Industrial Cities)": {
        "scraper": "modon",
        "website_urls": [
            "https://modon.gov.sa/en/media/pages/news.aspx",
        ],
        "linkedin_slug": "modongov",
        "linkedin_posts_url": "https://www.linkedin.com/company/modongov/posts/?feedView=all",
    },

    "Marafiq": {
        "scraper": "marafiq",
        "website_urls": [
            "https://www.marafiq.com.sa/en/media-center/news",
        ],
        "linkedin_slug": "marafiq",
        "linkedin_posts_url": "https://www.linkedin.com/company/marafiq/posts/?feedView=all",
    },

    "Saudi Aramco": {
        "scraper": "aramco",
        "website_urls": [
            "https://www.aramco.com/en/news-media/news",
            "https://www.aramco.com/en/what-we-do/suppliers/contracting-opportunities",
        ],
        "linkedin_slug": "aramco",
        "linkedin_posts_url": "https://www.linkedin.com/company/aramco/posts/?feedView=all",
    },

    # ── REGIONAL / NEWS PORTALS ───────────────────────────────────────────────

    "Saudi Government (Etimad)": {
        "scraper": "etimad",
        "website_urls": [
            "https://tenders.etimad.sa/Tender/AllTendersForPublic",
        ],
    },

    "Saudi Projects (Aggregator)": {
        "scraper": "saudi_projects",
        "website_urls": [
            "https://saudiprojects.net/?s=substation",
        ],
        "linkedin_slug": "saudi-projects",
    },

    "Construction Week Saudi": {
        "scraper": "construction_week",
        "website_urls": [
            "https://www.constructionweeksaudi.com/projects",
        ],
        "linkedin_slug": "construction-week",
    },

    "Utilities Middle East": {
        "scraper": "utilities_me",
        "website_urls": [
            "https://www.utilitiesme.com/power",
            "https://www.utilitiesme.com/news",
        ],
        "linkedin_slug": "utilities-middle-east",
        "linkedin_posts_url": "https://www.linkedin.com/company/utilities-middle-east/posts/?feedView=all",
    },

    "Saudi Gulf Projects": {
        "scraper": "saudi_gulf",
        "website_urls": [
            "https://www.saudigulfprojects.com/category/power/",
            "https://www.saudigulfprojects.com/category/substations/",
            "https://www.saudigulfprojects.com/category/transmission-line/",
        ],
        "linkedin_slug": "saudigulfprojects",
        "linkedin_posts_url": "https://www.linkedin.com/company/saudigulfprojects/posts/?feedView=all",
    },

    "Construction Week Middle East": {
        "scraper": "construction_week",
        "website_urls": [
            "https://www.constructionweekonline.com/projects-tenders",
            "https://www.constructionweekonline.com/news",
        ],
        "linkedin_slug": "construction-week-middle-east",
        "linkedin_posts_url": "https://www.linkedin.com/company/construction-week-middle-east/posts/?feedView=all",
    },

    # ── PREMIUM INTELLIGENCE NETWORKS ─────────────────────────────────────────

    "MEED (Middle East Economic Digest)": {
        "scraper": "meed",
        "is_premium_paywall": True,
    },
}