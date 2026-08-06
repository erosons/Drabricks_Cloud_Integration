from pathlib import Path
import pytz

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "storage" / "nigeria_finance.db"

WAT = pytz.timezone("Africa/Lagos")

SCRAPE_URLS = {
    # Nigerian Stock Exchange
    "ngx_home": "https://ngxgroup.com",
    "ngx_market_data": "https://ngxgroup.com/exchange/data/equities-price-list/",
    "ngx_api_equities": "https://ngxgroup.com/exchange/data/equities-price-list/",
    "ngx_market_summary": "https://ngxgroup.com/exchange/data/market-summary/",
    "ngx_equities_page": "https://ngxgroup.com/exchange/data/",
    # Central Bank of Nigeria — use main site and search pages
    "cbn_home": "https://www.cbn.gov.ng",
    "cbn_mpc": "https://www.cbn.gov.ng/monetary/mpc.asp",
    "cbn_mpc_alt": "https://www.cbn.gov.ng/MonetaryPolicy/MPC.asp",
    "cbn_press": "https://www.cbn.gov.ng/out/pressreleases.asp",
    "cbn_press_alt": "https://www.cbn.gov.ng/documents/pressrelease.asp",
    "cbn_rates": "https://www.cbn.gov.ng/rates/",
    "cbn_rates_alt": "https://www.cbn.gov.ng/rates/ExchRates.asp",
    # Debt Management Office
    "dmo_home": "https://www.dmo.gov.ng",
    "dmo_tbills": "https://www.dmo.gov.ng/debt-profile/domestic-debt/treasury-bills",
    "dmo_tbills_alt": "https://www.dmo.gov.ng/domestic-debt/treasury-bills/",
    "dmo_bonds": "https://www.dmo.gov.ng/debt-profile/domestic-debt/fgn-bonds",
    "dmo_bonds_alt": "https://www.dmo.gov.ng/domestic-debt/fgn-bonds/",
    "dmo_savings": "https://www.dmo.gov.ng/fgn-bonds/savings-bond",
    # SEC Nigeria
    "sec_home": "https://www.sec.gov.ng",
    "sec_public_offers": "https://www.sec.gov.ng/public-offers/",
    "sec_public_offers_alt": "https://www.sec.gov.ng/market/public-offers/",
    "sec_news": "https://www.sec.gov.ng/news/",
    "sec_news_alt": "https://sec.gov.ng/resources/press-releases/",
    # Fund managers
    "rise": "https://risevest.com",
    "piggyvest": "https://www.piggyvest.com",
    "bamboo": "https://www.bambooapp.co",
    "afriinvest": "https://www.afriinvest.com",
    "cowrywise": "https://cowrywise.com",
    # News RSS feeds
    "nairametrics_rss": "https://nairametrics.com/feed/",
    "businessday_rss": "https://businessday.ng/feed/",
    "proshare_rss": "https://proshareng.com/rss/",
    "proshare_home": "https://proshareng.com",
    "guardian_ng_rss": "https://guardian.ng/category/business/feed/",
    "stears_rss": "https://www.stears.co/feed/",
}

SCHEDULE = {
    "ngx_interval_minutes": 15,
    "cbn_interval_hours": 1,
    "dmo_cron_hour": 8,
    "funds_interval_hours": 6,
    "news_interval_minutes": 30,
    "ipo_interval_hours": 6,
    "opportunity_interval_minutes": 30,
}

OPPORTUNITY_WEIGHTS = {
    "HIGH_YIELD_TREASURY": 30,
    "POLICY_SHIFT": 40,
    "STOCK_BREAKOUT": 25,
    "IPO_ALERT": 35,
    "FUND_RATE_CHANGE": 20,
    "GOVT_FISCAL_MOVE": 30,
    "FX_OPPORTUNITY": 25,
    "SECTOR_SURGE": 20,
}

ALERT_THRESHOLDS = {
    "CRITICAL": 80,
    "HIGH": 60,
    "MEDIUM": 40,
    "LOW": 0,
}

POLICY_KEYWORDS = {
    "fiscal": ["budget", "fiscal", "revenue", "expenditure", "deficit", "surplus", "tax", "tariff"],
    "monetary": ["interest rate", "MPR", "MPC", "inflation", "monetary", "liquidity", "repo", "CRR"],
    "fx": ["forex", "exchange rate", "naira", "dollar", "devaluation", "revaluation", "FX", "BDC"],
    "investment": ["IPO", "bond", "treasury", "investment", "capital", "fund", "privatisation"],
    "economy": ["GDP", "growth", "recession", "unemployment", "poverty", "trade", "export", "import"],
}

SENTIMENT_POSITIVE = [
    "growth", "profit", "gain", "rise", "increase", "opportunity", "expand", "improve",
    "surge", "rally", "bullish", "recover", "boost", "positive", "strong", "record",
    "high", "advance", "upgrade", "beat", "exceed", "outperform",
]

SENTIMENT_NEGATIVE = [
    "loss", "decline", "fall", "drop", "decrease", "recession", "crash", "depreciate",
    "bearish", "plunge", "collapse", "concern", "risk", "weak", "poor", "miss",
    "below", "downgrade", "underperform", "crisis", "default", "inflation",
]

NGX_SECTORS = [
    "Agriculture", "Consumer Goods", "Financial Services", "Healthcare",
    "Industrial Goods", "ICT", "Natural Resources", "Oil & Gas",
    "Real Estate", "Services", "Utilities", "Conglomerates",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
