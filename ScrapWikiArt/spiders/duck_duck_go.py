import json
from contextlib import closing

import pandas as pd
import scrapy

from ScrapWikiArt import db
from ScrapWikiArt.items import ImageItem
from ScrapWikiArt.utils import spider_is_disabled


class DuckDuckGoSpider(scrapy.Spider):
    name = 'duck_duck_go'
    allowed_domains = ['api.duckduckgo.com']
    custom_settings = {
        "ITEM_PIPELINES": {
            "ScrapWikiArt.pipelines.SQLiteUpdatePipeline": 1,
        },
    }

    item_class = ImageItem
    query_feature = 'Title'
    # Columns that must be missing for a row to be re-queried. Computed as a
    # class attribute from the item's declared fields (design D5): the base
    # spider and the artist spider check both Description and WikiDescription.
    missing_columns = ["Description", "WikiDescription"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional per-run override of WIKIART_DB_PATH (defaults from settings).
        self.db_path = kwargs.get("db_path", None)

    def start_requests(self):
        # The disabled check wins over DB reads (issue #45).
        if spider_is_disabled(self):
            self.logger.info(
                "Spider %s is disabled via SPIDERS_ENABLED, skipping", self.name
            )
            return
        db_path = self.db_path or db.default_db_path(self.settings)
        table = db.table_for_class(self.item_class)
        with closing(db.connect(db_path)) as conn:
            if not db.table_exists(conn, table):
                self.logger.warning(
                    "Table %r not found in %s — no rows to enrich, skipping",
                    table, db_path,
                )
                return
            df = pd.read_sql(db.unenriched_sql(table, self.missing_columns), conn)

        fields = set(self.item_class.fields)
        for row_dict in df.to_dict(orient="records"):
            # Keep only declared item fields: the works table also carries
            # DB-only columns (scraped_at, ValidatedRaw, Validated) that
            # item_class(row_dict) would reject.
            row_dict = {k: v for k, v in row_dict.items() if k in fields}
            query = row_dict[self.query_feature]
            url = f'https://api.duckduckgo.com/?q={query}&format=json'
            yield scrapy.Request(url, meta={'row': row_dict}, callback=self.parse)

    def parse(self, response):
        row_dict = response.meta['row']
        # If RetryMiddleware exhausted its retries (RETRY_TIMES), the request
        # reaches parse() with a non-200 status.  We log and drop the row
        # instead of re-triggering a manual retry — RetryMiddleware already
        # did its job.
        if response.status in (429, 500, 502, 503, 504):
            self.logger.warning(
                "HTTP %d for query=%r — retries exhausted, row dropped",
                response.status, row_dict.get(self.query_feature),
            )
            return
        try:
            data = json.loads(response.text)
            if not isinstance(data, dict):
                self.logger.warning(
                    "Unexpected JSON payload for query=%r (attempt %d), retrying",
                    row_dict.get(self.query_feature),
                    response.meta.get('retry_count', 0) + 1,
                )
                yield from self.retry_request(response)
                return
            if not ('Abstract' in data and 'AbstractURL' in data):
                yield from self.retry_request(response)
                return

            if data['Abstract'] != '':
                row_dict["WikiLink"] = data["AbstractURL"]
                row_dict["WikiDescription"] = data["Abstract"]
                yield self.item_class(row_dict)
                return

            # HTTP 200 with empty Abstract — likely a DDG disambiguation or
            # thin result.  Retry with backoff handled by global throttle
            # (DOWNLOAD_DELAY + AUTOTHROTTLE) and per-domain concurrency cap.
            self.logger.warning(
                "Empty Abstract for query=%r (attempt %d), retrying",
                row_dict.get(self.query_feature),
                response.meta.get('retry_count', 0) + 1,
            )
            yield from self.retry_request(response)
            return
        except json.JSONDecodeError:
            self.logger.warning(
                "Invalid JSON for query=%r (attempt %d), retrying",
                row_dict.get(self.query_feature),
                response.meta.get('retry_count', 0) + 1,
            )
            yield from self.retry_request(response)
            return

    def retry_request(self, response):
        """Yield a retry request for content-level failures (empty Abstract,
        missing keys, invalid JSON).

        HTTP-level failures (429, 5xx) are additionally retried by Scrapy's
        built-in RetryMiddleware configured in settings.py (RETRY_TIMES,
        RETRY_HTTP_CODES).  Note that RetryMiddleware also applies to the
        requests yielded here (it copies the request and keeps dont_filter),
        so a row that keeps failing can generate up to (1 + 5) * (1 + 3) = 24
        HTTP requests before being dropped.  That bound is intentional:
        without the retry_count >= 5 guard the combination would be unbounded.

        Exponential backoff for the *content* retries is not natively supported
        by Scrapy without a custom downloader middleware.  Instead, global
        throttling (DOWNLOAD_DELAY + AUTOTHROTTLE + CONCURRENT_REQUESTS_PER_DOMAIN
        in settings.py) serializes requests to the same domain and adapts the
        pace based on server responses.  For true per-request exponential
        backoff a custom DownloaderMiddleware reading meta['retry_count'] and
        injecting a sleep would be needed — out of scope for this fix.
        """
        retry_count = response.meta.get('retry_count', 0)
        if retry_count >= 5:
            self.logger.warning(
                "Retries exhausted for query=%r after %d retries — row dropped",
                response.meta['row'].get(self.query_feature), retry_count,
            )
            return
        retry_count += 1
        yield scrapy.Request(
            response.url,
            meta={'row': response.meta['row'], 'retry_count': retry_count},
            callback=self.parse,
            dont_filter=True,
        )