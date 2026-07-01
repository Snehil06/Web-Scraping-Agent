"""
generate_report_ui.py — Algihaz Competitive Intelligence Dashboard Generator
Reads  : competitor_deals_report.json
Writes : competitor_intelligence_dashboard.html
"""

import json
import html
import re
from pathlib import Path
from datetime import datetime, timezone

INPUT_FILE  = Path("./competitor_deals_report.json")
OUTPUT_HTML = Path("./competitor_intelligence_dashboard.html")

# ─── Sample data (used when no JSON file is present) ─────────────────────────
SAMPLE_DATA = {
    "report_metadata": {"generated_at": "2026-06-28T08:30:00Z"},
    "intelligence": {
        "Alfanar Projects": {"deals": [
            {
                "project_title": "220kV GIS Substation – Qassim Grid Upgrade",
                "client_entity": "Saudi Electricity Company (SEC)",
                "deal_status": "Awarded",
                "declared_value": "SAR 340M",
                "deal_date": "March 2026",
                "is_new": True,
                "scraped_at": "2026-06-27T10:00:00Z",
                "source_url": "https://alfanarprojects.com/en-us/newsroom/",
                "strategic_implication_for_algihaz": "Direct competitor wins SEC GIS package in Central Region – high overlap with Algihaz's core substation portfolio.",
            },
            {
                "project_title": "Riyadh Industrial Zone OHTL Package",
                "client_entity": "MODON",
                "deal_status": "Under Execution",
                "declared_value": "SAR 180M",
                "deal_date": "October 2025",
                "is_new": False,
                "scraped_at": "2026-05-10T10:00:00Z",
                "source_url": "https://alfanarprojects.com/en-us/newsroom/",
                "strategic_implication_for_algihaz": "MODON electrification work taken by Alfanar; monitor Phase 2 tender opportunity.",
            },
        ]},
        "Nesma & Partners": {"deals": [
            {
                "project_title": "SEC 380kV Double Circuit Transmission Line – Makkah Region",
                "client_entity": "Saudi Electricity Company (SEC)",
                "deal_status": "Tender Bid",
                "declared_value": "SAR 620M",
                "deal_date": "May 2026",
                "is_new": True,
                "scraped_at": "2026-06-25T10:00:00Z",
                "source_url": "https://www.nesmapartners.com/en/media-room",
                "strategic_implication_for_algihaz": "Nesma bidding on large OHTL package; Algihaz should assess competitiveness on the same lot.",
            },
            {
                "project_title": "Jubail Industrial City Substation Retrofit",
                "client_entity": "Marafiq",
                "deal_status": "Signed",
                "declared_value": "SAR 95M",
                "deal_date": "January 2026",
                "is_new": False,
                "scraped_at": "2026-04-01T10:00:00Z",
                "source_url": "https://www.nesmapartners.com/en/media-room",
                "strategic_implication_for_algihaz": "Marafiq retrofit locked by Nesma; builds their industrial utility track record.",
            },
        ]},
        "Rawabi Electric": {"deals": [
            {
                "project_title": "NEOM Smart Grid Electrification Phase 1",
                "client_entity": "NEOM",
                "deal_status": "Under Execution",
                "declared_value": "USD 210M",
                "deal_date": "August 2025",
                "is_new": False,
                "scraped_at": "2026-03-15T10:00:00Z",
                "source_url": "https://www.rawabielectric.com/news-media",
                "strategic_implication_for_algihaz": "NEOM relationship established by Rawabi; Phase 2 bidding approaching Q4 2026.",
            },
        ]},
        "Tata Projects": {"deals": [
            {
                "project_title": "Saudi Aramco Ras Tanura Power Upgrade",
                "client_entity": "Saudi Aramco",
                "deal_status": "Awarded",
                "declared_value": "USD 145M",
                "deal_date": "April 2026",
                "is_new": True,
                "scraped_at": "2026-06-20T10:00:00Z",
                "source_url": "https://www.tataprojects.com/media/press-releases/",
                "strategic_implication_for_algihaz": "Tata deepens Aramco relationship in Eastern Province – core Algihaz territory.",
            },
        ]},
        "L&T Power Transmission & Distribution": {"deals": [
            {
                "project_title": "National Grid SA 500kV Interconnection Scheme",
                "client_entity": "National Grid SA",
                "deal_status": "Signed",
                "declared_value": "SAR 880M",
                "deal_date": "February 2026",
                "is_new": True,
                "scraped_at": "2026-06-22T10:00:00Z",
                "source_url": "https://www.larsentoubro.com/corporate/media/media-releases/",
                "strategic_implication_for_algihaz": "L&T secures flagship National Grid contract; significant competitive threat on major transmission lot.",
            },
            {
                "project_title": "Yanbu Industrial OHTL Expansion",
                "client_entity": "Saudi Aramco",
                "deal_status": "Pipeline",
                "declared_value": "SAR 230M",
                "deal_date": "Pipeline/Active Tracking",
                "is_new": False,
                "scraped_at": "2026-05-01T10:00:00Z",
                "source_url": "https://www.larsentoubro.com/corporate/media/media-releases/",
                "strategic_implication_for_algihaz": "Pipeline opportunity L&T is positioned for; Algihaz should pre-qualify now.",
            },
        ]},
        "SSEM": {"deals": [
            {
                "project_title": "SEC 132kV AIS Substation – Eastern Region",
                "client_entity": "Saudi Electricity Company (SEC)",
                "deal_status": "Awarded",
                "declared_value": "SAR 65M",
                "deal_date": "June 2026",
                "is_new": True,
                "scraped_at": "2026-06-28T08:00:00Z",
                "source_url": "https://ssem.com.sa/news-media/",
                "strategic_implication_for_algihaz": "SSEM wins smaller AIS package in Algihaz's home region – watch for bundled lots.",
            },
        ]},
    },
}

# ─── Client name normalisation ────────────────────────────────────────────────
CLIENT_ALIASES: dict[str, str] = {
    "saudi electricity company":                       "Saudi Electricity Company (SEC)",
    "saudi electricity company sec":                   "Saudi Electricity Company (SEC)",
    "saudi electric company":                          "Saudi Electricity Company (SEC)",
    "sec":                                             "Saudi Electricity Company (SEC)",
    "saudi electricity company national grid sa":      "Saudi Electricity Company (SEC)",
    "eetc saudi electricity company":                  "Saudi Electricity Company (SEC)",
    "national grid sa":                                "National Grid SA",
    "saudi aramco":                                    "Saudi Aramco",
    "saline water conversion corporation":             "Saline Water Conversion Corporation (SWCC)",
    "swcc":                                            "Saline Water Conversion Corporation (SWCC)",
    "marafiq":                                         "Marafiq",
    "modon":                                           "MODON",
    "neom":                                            "NEOM",
    "qatarenergy":                                     "QatarEnergy",
    "qatar energy":                                    "QatarEnergy",
    "gulf cooperation council interconnection authority": "GCCIA",
    "gccia":                                           "GCCIA",
    "kuwait oil company":                              "Kuwait Oil Company (KOC)",
    "koc":                                             "Kuwait Oil Company (KOC)",
    "qiddiya investment company":                      "Qiddiya Investment Company",
    "not specified":                                   "Not Specified",
}


def normalize_client(client: str) -> str:
    if not client:
        return "Not Specified"
    original = str(client).strip()
    cleaned  = re.sub(r"\([^)]*\)", "", original)
    cleaned  = cleaned.replace("/", " ").replace("&", " ")
    cleaned  = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned)
    key      = re.sub(r"\s+", " ", cleaned).lower().strip()
    return CLIENT_ALIASES.get(key, original)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def gen_token(title: str) -> str:
    t = str(title).lower()
    t = re.sub(
        r"\b(project|package|solutions|inc|co|ltd|u/g|underground|overhead|ohtl|"
        r"station|substation|line|lines|systems|kv|operating|area|of|the|and|for|"
        r"phase|expansion)\b",
        "", t,
    )
    return "".join(sorted(re.findall(r"\b\w+\b", t)))


def parse_date(s: str):
    s = str(s).strip()
    if not s or any(x in s.lower() for x in ("pipeline", "active", "tracking")):
        return None
    fmts = [
        "%B %Y", "%b %Y", "%B %d, %Y", "%b %d, %Y",
        "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%d %B %Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    m = re.search(r"(Q[1-4])\s+(\d{4})", s)
    if m:
        q = {"Q1": 1, "Q2": 4, "Q3": 7, "Q4": 10}[m.group(1)]
        return datetime(int(m.group(2)), q, 1, tzinfo=timezone.utc)
    m2 = re.search(r"\d{4}", s)
    if m2:
        return datetime(int(m2.group()), 6, 15, tzinfo=timezone.utc)
    return None


def week_bucket(d) -> str:
    if d is None:
        return "pipeline"
    diff = (datetime.now(timezone.utc) - d).days
    if diff < 0:    return "upcoming"
    if diff <= 7:   return "this_week"
    if diff <= 30:  return "this_month"
    if diff <= 90:  return "last_3m"
    return "older"


def sanitize_url(url: str) -> str:
    """Return a safe, non-empty URL string or empty string."""
    if not url:
        return ""
    url = str(url).strip()
    if url.lower() in ("", "none", "n/a", "null", "undefined"):
        return ""
    if not url.startswith(("http://", "https://")):
        return ""
    return url


# ─── Main generator ───────────────────────────────────────────────────────────
def generate() -> None:
    if INPUT_FILE.exists():
        try:
            data = json.loads(INPUT_FILE.read_text("utf-8"))
        except Exception:
            data = SAMPLE_DATA
    else:
        data = SAMPLE_DATA

    generated_at = data.get("report_metadata", {}).get("generated_at", "")
    try:
        dt       = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        friendly = dt.strftime("%d %b %Y, %I:%M %p UTC")
    except Exception:
        friendly = generated_at

    intelligence = data.get("intelligence", {})
    all_deals: list[dict] = []
    seen: set[str] = set()

    for comp, content in intelligence.items():
        for deal in content.get("deals", []):
            fp = gen_token(deal.get("project_title", ""))
            if fp in seen:
                continue
            seen.add(fp)
            d = dict(deal)
            d["client_entity"] = normalize_client(d.get("client_entity", ""))
            d["competitor"]    = comp
            d["_dt"]           = parse_date(d.get("deal_date", ""))
            d["_bucket"]       = week_bucket(d["_dt"])
            all_deals.append(d)

    all_deals.sort(key=lambda x: x.get("scraped_at", ""), reverse=True)

    deals_json: list[dict] = []
    for d in all_deals:
        deals_json.append({
            "id":         re.sub(r"[^a-z0-9]", "", d.get("project_title", "").lower())[:40],
            "title":      d.get("project_title", "Untitled"),
            "client":     d.get("client_entity", "Unknown"),
            "competitor": d.get("competitor", ""),
            "status":     d.get("deal_status", "Unknown"),
            "value":      d.get("declared_value", "Undisclosed"),
            "date":       d.get("deal_date", "Active Tracking"),
            "bucket":     d["_bucket"],
            "is_new":     d.get("is_new", False),
            # ── KEY FIX: source_url is the correct field name from the agent ──
            "source":     sanitize_url(d.get("source_url", "")),
            "implication": d.get("strategic_implication_for_algihaz", ""),
        })

    html_out = (
        HTML_TEMPLATE
        .replace("__DEALS_JSON__",  json.dumps(deals_json, ensure_ascii=False))
        .replace("__GENERATED_AT__", html.escape(friendly))
    )
    OUTPUT_HTML.write_text(html_out, encoding="utf-8")
    print(f"[✓] Dashboard written: {OUTPUT_HTML.resolve()}")


# ─── HTML Template ────────────────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Algihaz Competitive Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.47.0/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#0f111a;color:#e2e8f0;min-height:100vh;font-size:14px}
a{color:inherit;text-decoration:none}

/* ── Header ─────────────────────────────────────────────────────── */
header{background:#0a0c14;border-bottom:1px solid #1e2333;padding:16px 24px;
       display:flex;align-items:center;justify-content:space-between;
       position:sticky;top:0;z-index:100}
.logo-mark{font-size:18px;font-weight:600;color:#38bdf8;letter-spacing:.5px}
.logo-sub{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1.5px;margin-top:2px}
.scan-badge{background:#1e2333;border:1px solid #2d3654;padding:5px 12px;
            border-radius:6px;font-size:11px;color:#64748b}
.scan-badge span{color:#38bdf8}

main{max-width:1200px;margin:0 auto;padding:24px 20px}

/* ── KPI Row ─────────────────────────────────────────────────────── */
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
         gap:12px;margin-bottom:28px}
.kpi{background:#131726;border:1px solid #1e2333;border-radius:10px;padding:16px;
     cursor:pointer;transition:border-color .15s}
.kpi:hover{border-color:#334155}
.kpi.active{border-color:#38bdf8;background:#0f2233}
.kpi-label{font-size:11px;color:#64748b;text-transform:uppercase;
           letter-spacing:.8px;margin-bottom:8px}
.kpi-val{font-size:28px;font-weight:600;color:#f1f5f9;line-height:1}
.kpi-sub{font-size:11px;color:#94a3b8;margin-top:4px}
.kpi-new{display:inline-block;background:#f97316;color:#fff;font-size:9px;
         font-weight:600;padding:1px 5px;border-radius:3px;vertical-align:middle;
         margin-left:4px}

/* ── Section titles ──────────────────────────────────────────────── */
.section-title{font-size:11px;color:#64748b;text-transform:uppercase;
               letter-spacing:1px;margin-bottom:12px;display:flex;
               align-items:center;gap:6px}

/* ── Timeline strip ──────────────────────────────────────────────── */
.timeline-strip{display:flex;gap:8px;margin-bottom:28px;
                overflow-x:auto;padding-bottom:4px}
.tl-bucket{background:#131726;border:1px solid #1e2333;border-radius:8px;
           padding:10px 14px;cursor:pointer;white-space:nowrap;
           transition:all .15s;flex-shrink:0}
.tl-bucket:hover{border-color:#334155}
.tl-bucket.active{border-color:#38bdf8;background:#0f2233}
.tl-bucket-label{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.8px}
.tl-bucket-count{font-size:20px;font-weight:600;color:#f1f5f9;line-height:1;margin-top:2px}
.tl-dot{display:inline-block;width:6px;height:6px;border-radius:50%;
        background:#f97316;margin-right:4px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* ── Status bar ──────────────────────────────────────────────────── */
.status-bar-wrap{background:#131726;border:1px solid #1e2333;border-radius:10px;
                 padding:16px 20px;margin-bottom:28px}
.status-bar-row{display:flex;border-radius:6px;overflow:hidden;height:32px;
                cursor:pointer;margin-bottom:12px}
.sb-seg{display:flex;align-items:center;justify-content:center;font-size:11px;
        font-weight:500;cursor:pointer;white-space:nowrap;padding:0 8px;
        transition:opacity .15s}
.sb-seg:hover{opacity:.85}
.sb-awarded{background:#059669;color:#d1fae5}
.sb-signed{background:#0284c7;color:#bae6fd}
.sb-execution{background:#7c3aed;color:#ddd6fe}
.sb-tender{background:#d97706;color:#fef3c7}
.sb-pipeline{background:#374151;color:#9ca3af}
.sb-legend{display:flex;flex-wrap:wrap;gap:12px}
.sbl{display:flex;align-items:center;gap:5px;font-size:11px;color:#94a3b8;cursor:pointer}
.sbl-dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}

/* ── Client accordion ────────────────────────────────────────────── */
.client-section{margin-bottom:8px}
.client-header{background:#131726;border:1px solid #1e2333;border-radius:10px;
               padding:14px 18px;display:flex;align-items:center;
               justify-content:space-between;cursor:pointer;transition:all .15s}
.client-header:hover{border-color:#334155}
.client-header.open{border-color:#334155;border-bottom-left-radius:0;border-bottom-right-radius:0}
.client-name{font-size:14px;font-weight:600;color:#f1f5f9}
.client-meta{display:flex;align-items:center;gap:10px;margin-top:3px}
.client-count{font-size:12px;color:#64748b}
.client-new-badge{background:#f97316;color:#fff;font-size:9px;font-weight:600;
                  padding:2px 6px;border-radius:3px}
.chevron{transition:transform .2s;color:#64748b;font-size:16px}
.chevron.open{transform:rotate(180deg)}
.client-body{background:#0d0f1a;border:1px solid #1e2333;border-top:none;
             border-bottom-left-radius:10px;border-bottom-right-radius:10px;
             overflow:hidden}

/* ── Deal row ────────────────────────────────────────────────────── */
.deal-row{padding:14px 18px;border-bottom:1px solid #1a1d2e;
          display:flex;flex-direction:column;gap:8px;transition:background .1s}
.deal-row:last-child{border-bottom:none}
.deal-row:hover{background:#121525}
.deal-row.is-new{border-left:3px solid #f97316}

.deal-row-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.deal-title{font-size:13px;font-weight:500;color:#e2e8f0;line-height:1.4}
.deal-title a{color:#38bdf8;margin-left:5px;font-size:11px;opacity:.7;
              vertical-align:middle}
.deal-title a:hover{opacity:1;text-decoration:underline}
.deal-value{font-size:12px;font-weight:600;color:#34d399;white-space:nowrap;flex-shrink:0}

.deal-row-mid{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.deal-contractor{font-size:11px;color:#94a3b8}
.deal-date-tag{font-size:11px;color:#64748b;display:flex;align-items:center;gap:3px}

/* ── Source link — always visible, prominent ─────────────────────── */
.deal-source-link{display:inline-flex;align-items:center;gap:4px;
                  font-size:11px;font-weight:500;color:#38bdf8;
                  background:#0c1e30;border:1px solid #1a3a54;
                  padding:2px 8px;border-radius:4px;cursor:pointer;
                  text-decoration:none;transition:background .15s}
.deal-source-link:hover{background:#132840;text-decoration:underline}
.deal-source-link i{font-size:10px}

.deal-row-implication{font-size:11px;color:#64748b;line-height:1.5;
                      padding:8px 10px;background:#0f111a;border-radius:6px;
                      border-left:2px solid #1e2333}

/* ── Badges ──────────────────────────────────────────────────────── */
.new-flash{background:#7c2d12;color:#fed7aa;font-size:9px;font-weight:600;
           padding:1px 5px;border-radius:3px;display:inline-flex;
           align-items:center;gap:2px;margin-right:4px}
.badge{font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;
       text-transform:uppercase;letter-spacing:.4px}
.badge-awarded{background:#064e3b;color:#6ee7b7}
.badge-signed{background:#0c2340;color:#7dd3fc}
.badge-execution{background:#2e1065;color:#c4b5fd}
.badge-tender{background:#451a03;color:#fcd34d}
.badge-pipeline{background:#1f2937;color:#9ca3af}
.badge-completed{background:#0f2e1a;color:#86efac}

/* ── Misc ────────────────────────────────────────────────────────── */
.sect-divider{margin:24px 0 20px;border-top:1px solid #1e2333}
.empty{text-align:center;padding:48px 20px;color:#374151;font-size:13px}
.empty i{font-size:32px;display:block;margin-bottom:8px}
</style>
</head>
<body>

<header>
  <div>
    <div class="logo-mark">ALGIHAZ HOLDING</div>
    <div class="logo-sub">Competitive Intelligence Engine</div>
  </div>
  <div class="scan-badge">Last scan: <span>__GENERATED_AT__</span></div>
</header>

<main>
  <div class="kpi-row" id="kpi-row"></div>

  <div class="section-title">
    <i class="ti ti-timeline" aria-hidden="true"></i> Timeline filter
  </div>
  <div class="timeline-strip" id="timeline-strip"></div>

  <div class="section-title">
    <i class="ti ti-chart-bar" aria-hidden="true"></i> Pipeline status
  </div>
  <div class="status-bar-wrap">
    <div class="status-bar-row" id="status-bar-row"></div>
    <div class="sb-legend" id="sb-legend"></div>
  </div>

  <div class="sect-divider"></div>

  <div class="section-title">
    <i class="ti ti-building" aria-hidden="true"></i> Projects by client
  </div>
  <div id="client-list"></div>
</main>

<script>
const ALL_DEALS = __DEALS_JSON__;

/* ── Status helpers ─────────────────────────────────────────────────────── */
const STATUS_META = {
  awarded:   {badge:"badge-awarded",   bar:"sb-awarded",   label:"Awarded",          color:"#059669"},
  signed:    {badge:"badge-signed",    bar:"sb-signed",    label:"Signed",            color:"#0284c7"},
  execution: {badge:"badge-execution", bar:"sb-execution", label:"Under Execution",   color:"#7c3aed"},
  tender:    {badge:"badge-tender",    bar:"sb-tender",    label:"Tender / Bid",      color:"#d97706"},
  pipeline:  {badge:"badge-pipeline",  bar:"sb-pipeline",  label:"Pipeline",          color:"#374151"},
  completed: {badge:"badge-completed", bar:"sb-awarded",   label:"Completed",         color:"#065f46"},
};
const BAR_ORDER = ["awarded","signed","execution","tender","pipeline","completed"];

function sk(s) {
  const sl = (s||"").toLowerCase();
  if (sl.includes("award"))                                     return "awarded";
  if (sl.includes("sign"))                                      return "signed";
  if (sl.includes("execution")||sl.includes("construct")||sl.includes("active")) return "execution";
  if (sl.includes("tender")||sl.includes("bid")||sl.includes("pq")||sl.includes("proposal")) return "tender";
  if (sl.includes("complet"))                                   return "completed";
  return "pipeline";
}

function badgeHtml(status) {
  const k   = sk(status);
  const m   = STATUS_META[k] || STATUS_META.pipeline;
  return `<span class="badge ${m.badge}">${m.label}</span>`;
}

function esc(s) {
  return String(s||"")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

/* Source URL link — always rendered when a real URL exists */
function sourceLinkHtml(url) {
  if (!url) return "";
  const label = url.replace(/^https?:\/\/(?:www\.)?/, "").split("/")[0];
  return `<a class="deal-source-link" href="${esc(url)}" target="_blank" rel="noopener">
    <i class="ti ti-external-link" aria-hidden="true"></i>${esc(label)}
  </a>`;
}

/* ── Filter state ───────────────────────────────────────────────────────── */
let activeTimeline = "all";
let activeStatus   = "all";

function filteredDeals() {
  return ALL_DEALS.filter(d => {
    if (activeTimeline !== "all" && d.bucket !== activeTimeline) return false;
    if (activeStatus   !== "all" && sk(d.status) !== activeStatus) return false;
    return true;
  });
}

/* ── KPI Row ────────────────────────────────────────────────────────────── */
function buildKpiRow() {
  const total       = ALL_DEALS.length;
  const newCount    = ALL_DEALS.filter(d => d.is_new).length;
  const clients     = new Set(ALL_DEALS.map(d => d.client)).size;
  const competitors = new Set(ALL_DEALS.map(d => d.competitor)).size;
  const confirmed   = ALL_DEALS.filter(d => ["awarded","signed"].includes(sk(d.status))).length;

  const kpis = [
    {label:"Total deals",      val:total,      sub:`${competitors} competitors tracked`},
    {label:"New this run",     val:newCount,   sub:"flagged entries",        orange:true},
    {label:"Clients tracked",  val:clients,    sub:"awarding authorities"},
    {label:"Awarded / Signed", val:confirmed,  sub:"contracts confirmed"},
  ];
  document.getElementById("kpi-row").innerHTML = kpis.map(k => `
    <div class="kpi">
      <div class="kpi-label">${esc(k.label)}</div>
      <div class="kpi-val">${k.val}${k.orange && k.val > 0 ? '<span class="kpi-new">NEW</span>' : ""}</div>
      <div class="kpi-sub">${esc(k.sub)}</div>
    </div>
  `).join("");
}

/* ── Timeline ───────────────────────────────────────────────────────────── */
function buildTimeline() {
  const buckets = [
    {key:"all",        label:"All time"},
    {key:"this_week",  label:"This week"},
    {key:"this_month", label:"This month"},
    {key:"last_3m",    label:"Last 3 months"},
    {key:"older",      label:"Older"},
    {key:"pipeline",   label:"Pipeline"},
    {key:"upcoming",   label:"Upcoming"},
  ];
  document.getElementById("timeline-strip").innerHTML = buckets.map(b => {
    const count  = b.key === "all" ? ALL_DEALS.length : ALL_DEALS.filter(d => d.bucket === b.key).length;
    const hasNew = ALL_DEALS.some(d => d.bucket === b.key && d.is_new);
    return `<div class="tl-bucket ${activeTimeline === b.key ? "active" : ""}"
                 onclick="setTimeline('${b.key}')">
      <div class="tl-bucket-label">${hasNew ? '<span class="tl-dot"></span>' : ""}${esc(b.label)}</div>
      <div class="tl-bucket-count">${count}</div>
    </div>`;
  }).join("");
}

function setTimeline(key) {
  activeTimeline = key;
  buildTimeline();
  buildStatusBar();
  buildClientList();
}

/* ── Status bar ─────────────────────────────────────────────────────────── */
function buildStatusBar() {
  const deals = filteredDeals();
  const counts = {};
  BAR_ORDER.forEach(k => counts[k] = 0);
  deals.forEach(d => counts[sk(d.status)]++);
  const total = deals.length || 1;

  document.getElementById("status-bar-row").innerHTML =
    BAR_ORDER.filter(k => counts[k] > 0).map(k => {
      const pct = Math.round(counts[k] / total * 100);
      const m   = STATUS_META[k];
      return `<div class="sb-seg ${m.bar}" style="width:${pct}%;min-width:${pct > 0 ? "40px" : "0"}"
                   onclick="setStatus('${k}')" title="${m.label}: ${counts[k]}">${counts[k]}</div>`;
    }).join("");

  document.getElementById("sb-legend").innerHTML =
    BAR_ORDER.filter(k => counts[k] > 0).map(k => {
      const m = STATUS_META[k];
      return `<div class="sbl ${activeStatus === k ? "sbl-active" : ""}" onclick="setStatus('${k}')">
        <div class="sbl-dot" style="background:${m.color}"></div>
        ${m.label} (${counts[k]})
      </div>`;
    }).join("") +
    `<div class="sbl" onclick="setStatus('all')">
       <div class="sbl-dot" style="background:#334155"></div>All
     </div>`;
}

function setStatus(key) {
  activeStatus = activeStatus === key ? "all" : key;
  buildStatusBar();
  buildClientList();
}

/* ── Client accordion list ──────────────────────────────────────────────── */
const openClients = new Set();

function buildClientList() {
  const deals = filteredDeals();
  const byClient = {};
  deals.forEach(d => {
    const c = d.client || "Unknown";
    (byClient[c] = byClient[c] || []).push(d);
  });
  const sorted = Object.entries(byClient).sort((a, b) => b[1].length - a[1].length);
  const container = document.getElementById("client-list");

  if (!sorted.length) {
    container.innerHTML = `<div class="empty"><i class="ti ti-zoom-cancel"></i>No deals match the current filters.</div>`;
    return;
  }

  /* Auto-open the top client on first render */
  if (openClients.size === 0 && sorted.length) openClients.add(sorted[0][0]);

  container.innerHTML = sorted.map(([client, cd]) => {
    const isOpen   = openClients.has(client);
    const newCount = cd.filter(d => d.is_new).length;
    const newBadge = newCount > 0
      ? `<span class="client-new-badge">${newCount} NEW</span>`
      : "";

    const rows = cd.map(d => {
      const newFlash   = d.is_new ? `<span class="new-flash">✦ New</span>` : "";
      const sourceLink = sourceLinkHtml(d.source);

      return `<div class="deal-row ${d.is_new ? "is-new" : ""}">
        <div class="deal-row-top">
          <div class="deal-title">
            ${newFlash}${esc(d.title)}
          </div>
          <div class="deal-value">${esc(d.value)}</div>
        </div>
        <div class="deal-row-mid">
          ${badgeHtml(d.status)}
          <span class="deal-contractor">
            <i class="ti ti-building-factory-2" aria-hidden="true" style="font-size:11px"></i>
            ${esc(d.competitor)}
          </span>
          <span class="deal-date-tag">
            <i class="ti ti-calendar" aria-hidden="true" style="font-size:10px"></i>
            ${esc(d.date)}
          </span>
          ${sourceLink}
        </div>
        ${d.implication
          ? `<div class="deal-row-implication">
               <i class="ti ti-alert-triangle" aria-hidden="true"
                  style="font-size:10px;color:#f97316"></i>
               ${esc(d.implication)}
             </div>`
          : ""}
      </div>`;
    }).join("");

    const safeId = encodeURIComponent(client);
    return `<div class="client-section" id="cs-${safeId}">
      <div class="client-header ${isOpen ? "open" : ""}"
           onclick="toggleClient('${esc(client).replace(/'/g, "\\'")}')">
        <div>
          <div class="client-name">${esc(client)}</div>
          <div class="client-meta">
            <span class="client-count">${cd.length} deal${cd.length !== 1 ? "s" : ""}</span>
            ${newBadge}
          </div>
        </div>
        <i class="ti ti-chevron-down chevron ${isOpen ? "open" : ""}" aria-hidden="true"></i>
      </div>
      <div class="client-body" style="display:${isOpen ? "block" : "none"}">${rows}</div>
    </div>`;
  }).join("");
}

function toggleClient(name) {
  const el = document.getElementById("cs-" + encodeURIComponent(name));
  if (!el) return;
  const header  = el.querySelector(".client-header");
  const body    = el.querySelector(".client-body");
  const chevron = el.querySelector(".chevron");
  const isOpen  = body.style.display !== "none";
  body.style.display = isOpen ? "none" : "block";
  header.classList.toggle("open",  !isOpen);
  chevron.classList.toggle("open", !isOpen);
  if (!isOpen) openClients.add(name);
  else         openClients.delete(name);
}

/* ── Init ───────────────────────────────────────────────────────────────── */
buildKpiRow();
buildTimeline();
buildStatusBar();
buildClientList();
</script>
</body>
</html>"""


if __name__ == "__main__":
    generate()