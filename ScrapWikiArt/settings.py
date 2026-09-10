# =============================================================================
# Scrapy settings for ScrapWikiArt
# =============================================================================

BOT_NAME = "ScrapWikiArt"

SPIDER_MODULES = ["ScrapWikiArt.spiders"]
NEWSPIDER_MODULE = "ScrapWikiArt.spiders"

# --- Polite crawling ----------------------------------------------------------
# robots.txt is NOT obeyed because api.duckduckgo.com/robots.txt is
# `Disallow: /` for all user agents.  Enabling ROBOTSTXT_OBEY would silently
# kill every DuckDuckGo spider (0 items, no errors).  wikiart.org allows
# crawling in its robots.txt, so disabling globally is safe for both targets.
ROBOTSTXT_OBEY = False

# Base delay (seconds) between consecutive requests to the same domain.
# With AUTOTHROTTLE enabled this acts as the *minimum* delay; Scrapy may
# increase it when the server responds slowly.
DOWNLOAD_DELAY = 1.0

# Absolute caps on parallel downloads.  These prevent us from hammering DDG
# (or any single domain) with too many concurrent connections.
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 4

# --- Auto-throttle ------------------------------------------------------------
# Scrapy adjusts DOWNLOAD_DELAY on-the-fly based on server latency and error
# rates.  When the server slows down, the delay increases (up to MAX_DELAY);
# when it responds quickly, the delay shrinks back toward START_DELAY.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2.0
AUTOTHROTTLE_MAX_DELAY = 30.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 4.0

# --- Retry (HTTP-level) -------------------------------------------------------
# Scrapy's built-in RetryMiddleware handles transport and rate-limit errors
# (429, 5xx) *before* the spider's parse() method runs.  This complements
# the manual retry in DuckDuckGoSpider.retry_request(), which only fires
# for content-level failures (valid HTTP but empty/missing data).
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# --- Rotating proxies (DISABLED) ----------------------------------------------
# NOTE: rotating proxies are DISABLED until proxy_list.txt is populated.
# With an empty proxy list the middleware silently passes all traffic through
# the local IP, which multiplies the ban/rate-limit risk.
# DOWNLOADER_MIDDLEWARES = {
#     'rotating_proxies.middlewares.RotatingProxyMiddleware': 610,
#     'rotating_proxies.middlewares.BanDetectionMiddleware': 620,
# }
# ROTATING_PROXY_LIST_PATH = "proxy_list.txt"

# --- Spider enablement (SPIDERS_ENABLED) --------------------------------------
# Controls which spiders may crawl (issue #45). A flat list of spider names;
# groups and aliases are not supported. Disabled spiders no-op cleanly: they
# log "Spider <name> is disabled via SPIDERS_ENABLED, skipping" at INFO level
# and exit 0 without yielding any requests.
#
# Default ["wikiart"]: only the wikiart spider crawls, the other 9 no-op.
# Explicit [] disables EVERY spider (CI-safe kill switch). Unset or None falls
# back to the same default as utils.DEFAULT_ENABLED_SPIDERS.
#
# settings.py is the ONLY supported configuration point: there is no CLI flag
# for enablement, and `scrapy crawl <name> -s SPIDERS_ENABLED=...` is an
# unsupported side channel.
SPIDERS_ENABLED = ["wikiart"]

# --- SQLite database path -----------------------------------------------------
# Single source of truth for the SQLite database used by crawl pipelines,
# DDG spiders, and the validation script.  All consumers resolve through
# db.default_db_path(spider.settings) which reads this value.
WIKIART_DB_PATH = "data/works.db"

# --- Image store path ---------------------------------------------------------
# Base directory for downloaded images (relative to project root).
# Scrapy's ImagesPipeline writes full-resolution images to <IMAGES_STORE>/full/.
# Override via -s IMAGES_STORE=/custom/path on the CLI.
WIKIART_IMG_STORE = "data/img"
IMAGES_STORE = WIKIART_IMG_STORE

# --- Random sampling (WIKIART_SAMPLE_RATIO) -----------------------------------
# Bernoulli(p) downsampling for the wikiart spider (issue #48): each unseen
# artwork URL is enqueued with probability p. Default 1.0 is a strict no-op —
# every unseen artwork is enqueued, matching pre-sampling behavior exactly.
# p must satisfy 0 < p <= 1; invalid values raise ValueError at spider start.
# sampling applies ONLY to the wikiart spider; dict spiders never sample.
WIKIART_SAMPLE_RATIO = 1.0

# Optional deterministic seed for the sampling RNG. None or unset -> the RNG
# seeds from system entropy (non-deterministic runs). Any integer, INCLUDING
# 0, is a valid deterministic seed: same seed + same page order -> same subset.
WIKIART_RANDOM_SEED = None
