import logging
import math
import random
import sqlite3
import scrapy
from contextlib import closing

from bs4 import BeautifulSoup

from ScrapWikiArt import db
from ScrapWikiArt.items import ImageItem
from ScrapWikiArt.utils import (
    image_urls_or_empty,
    item_id,
    labeled_text,
    pipe_join,
    should_sample,
    spider_is_disabled,
)

logger = logging.getLogger(__name__)


class WikiArtSpider(scrapy.Spider):
    name = "wikiart"
    allowed_domains = ["wikiart.org"]
    domain = "wikiart.org"
    start_urls = ["https://www.wikiart.org/en/artists-by-nation"]
    custom_settings = {
        "ITEM_PIPELINES": {
            "scrapy.pipelines.images.ImagesPipeline": 1,
            "ScrapWikiArt.pipelines.SQLiteWorksPipeline": 2,
        },
    }

    @classmethod
    def from_crawler(cls, crawler):
        spider = super().from_crawler(crawler)
        spider.IMAGES_STORE = crawler.settings.get(
            "WIKIART_IMG_STORE", "data/img"
        )
        return spider

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # In-memory dedup set of artwork URLs across the whole crawl run
        # (design D3). Seeded from the works table in start_requests.
        self.seen: set[str] = set()
        # Sampling state is created by _init_sampling() in start_requests
        # (self.settings is unavailable in __init__). None sentinels keep
        # parse_artist inert (no-op) when called outside a start_requests
        # flow — e.g. directly from tests.
        self._p: float | None = None
        self._rng: random.Random | None = None

    def start_requests(self):
        if spider_is_disabled(self):
            self.logger.info(
                "Spider %s is disabled via SPIDERS_ENABLED, skipping", self.name
            )
            return
        # Seed the seen set from the DB. The works table may not exist yet on a
        # first run (pipelines create it only after start_requests is consumed),
        # hence the table_exists guard (design D3, Scrapy 2.10 timing).
        db_path = db.default_db_path(self.settings)
        try:
            with closing(db.connect(db_path)) as conn:
                if db.table_exists(conn, "works"):
                    self.seen |= db.load_seen_urls(conn)
        except sqlite3.Error:
            self.logger.warning(
                "Failed to seed seen set from %s — dedup across runs "
                "degrades for this run only",
                db_path,
            )
        self._init_sampling()
        yield from super().start_requests()

    def _init_sampling(self):
        """Read and validate sampling settings, create the RNG (issue #48).

        Reads WIKIART_SAMPLE_RATIO (default 1.0, must satisfy 0 < p <= 1)
        and WIKIART_RANDOM_SEED.  Numeric strings (e.g. from the ``-s``
        CLI side channel) are coerced with ``float()``; non-numeric or
        non-finite values raise ValueError.  Three-state seed detection:
        key absent or None -> non-deterministic; any integer including 0
        -> deterministic.
        """
        raw_p = self.settings.get("WIKIART_SAMPLE_RATIO", 1.0)
        # Numeric strings (CLI ``-s`` side channel) are coerced so the
        # documented ValueError contract holds for garbage instead of the
        # raw comparison's TypeError. Note: an explicit None never reaches
        # this code — Scrapy Settings.get() collapses stored None to the
        # default (1.0), same convention as spider_is_disabled. The
        # float() guard below only fires for non-str garbage when the
        # settings object does not collapse None (e.g. direct calls).
        if not isinstance(raw_p, (int, float)):
            try:
                p = float(raw_p)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"WIKIART_SAMPLE_RATIO must be > 0 and <= 1, got {raw_p!r}"
                ) from exc
        else:
            p = raw_p
        if not math.isfinite(p) or not (0 < p <= 1):
            raise ValueError(
                f"WIKIART_SAMPLE_RATIO must be > 0 and <= 1, got {p}"
            )
        # Scrapy Settings.get returns None for missing keys, so an absent
        # key, an explicit None, and the default all converge to a
        # non-deterministic RNG (random.Random(None)). seed 0 stays valid:
        # get() returns 0 and Random(0) is deterministic.
        seed = self.settings.get("WIKIART_RANDOM_SEED")
        self._p = p
        self._rng = random.Random(seed)

    def parse(self, response):
        for nation in response.xpath('//main/ul/li/a/@href').getall():
            yield response.follow(nation + "/text-list", callback=self.parse_nation)

    def parse_nation(self, response):
        for artist in response.xpath('//main/div/ul/li/a/@href').getall():
            yield response.follow(artist + "/all-works/text-list", callback=self.parse_artist)

    def parse_artist(self, response):
        for href in response.xpath('//main/div/ul/li/a/@href').getall():
            url = response.urljoin(href)
            if url in self.seen:
                continue
            self.seen.add(url)
            # seen-add ALWAYS precedes sampling (design invariant): a URL
            # rejected here is marked seen and never re-evaluated. The
            # _p is None guard keeps the gate inert when parse_artist is
            # called directly without start_requests (tests only).
            if self._p is not None and not should_sample(self._rng, self._p):
                continue
            yield response.follow(url, callback=self.parse_item)

    def parse_item(self, response):
        url = response.url
        title = response.xpath("//article/h3/text()").get()
        original_title_raw = response.xpath("//li[.//s[text()[contains(.,'Original Title:')]]]").get()
        original_title = labeled_text(original_title_raw)

        author = response.xpath("//article/h5[@itemprop='creator']/span[@itemprop='name']/a/text()").get()
        author_raw = response.xpath("//article/h5[@itemprop='creator']/span[@itemprop='name']/a/@href").get()
        author_link = (self.domain + author_raw) if author_raw else None
        date = response.xpath("//li[.//s[text()[contains(.,'Date:')]]]/span[@itemprop='dateCreated']/text()").get()

        styles_names = response.xpath("//li[.//s[text()[contains(.,'Style:')]]]/span/a/text()").getall()
        styles_links = [
            self.domain + url
            for url in response.xpath("//li[.//s[text()[contains(.,'Style:')]]]/span/a/@href").getall()
        ]
        styles = pipe_join(styles_names)
        styles_links_joined = pipe_join(styles_links)

        series = response.xpath("//li[.//s[text()[contains(.,'Series:')]]]/a/text()").get()
        series_link = response.xpath("//li[.//s[text()[contains(.,'Series:')]]]/a/@href").get()

        genre = response.xpath("//li[.//s[text()[contains(.,'Genre:')]]]/span/a/span[@itemprop='genre']/text()").get()
        genre_raw = response.xpath("//li[.//s[text()[contains(.,'Genre:')]]]/span/a/@href").get()
        genre_link = (self.domain + genre_raw) if genre_raw else None

        media = response.xpath("//li[.//s[text()[contains(.,'Media:')]]]/span/a/text()").getall()
        location = response.xpath("//li[.//s[text()[contains(.,'Location:')]]]/span/text()").get()

        dimensions_raw = response.xpath("//li[.//s[text()[contains(.,'Dimensions')]]]").get()
        dimensions = labeled_text(dimensions_raw)

        description_raw = response.xpath('//div[@id="info-tab-description"]/p').get()
        description = BeautifulSoup(description_raw, features="lxml").get_text() if description_raw else description_raw

        wiki_description_raw = response.xpath('//div[@id="info-tab-wikipediadescription"]/p').get()
        wiki_description = BeautifulSoup(wiki_description_raw, features="lxml").get_text() if wiki_description_raw else wiki_description_raw

        wiki_link = response.xpath('//a[@class="wiki-link"]/@href').get()

        tags = response.xpath("//div[@class='tags-cheaps']/div/a/text()").getall()
        tags = [tag.replace('\n', '').replace('\t', '').replace(' ', '') for tag in tags]

        img_urls = image_urls_or_empty(
            response.xpath('//ul[@class="image-variants-container"]//a/@data-image-url').getall(),
            response.xpath('//img[@itemprop="image"]/@src').get(),
        )
        if not img_urls:
            self.logger.warning("No image found at %s", response.url)

        itemid = item_id(response.url)
        yield ImageItem({
            "Id": itemid,
            "URL": url,
            "Title": title,
            "OriginalTitle": original_title,
            "Author": author,
            "AuthorLink": author_link,
            "Date": date,
            "Styles": styles,
            "StylesLinks": styles_links_joined,
            "Series": series,
            "SeriesLink": series_link,
            "Genre": genre,
            "GenreLink": genre_link,
            "Media": media,
            "Location": location,
            "Dimensions": dimensions,
            "Description": description,
            "WikiDescription": wiki_description,
            "WikiLink": wiki_link,
            "Tags": tags,
            "image_urls": img_urls,
        })


