# =============================================================================
# Scrapy settings for ScrapWikiArt
# =============================================================================

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
