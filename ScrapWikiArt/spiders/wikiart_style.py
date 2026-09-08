import scrapy

from bs4 import BeautifulSoup

from ScrapWikiArt.items import StyleItem
from ScrapWikiArt.utils import clean_name, item_id


class WikiArtArtistSpider(scrapy.Spider):
    name = "wikiart_style"
    allowed_domains = ["wikiart.org"]
    start_urls = ["https://www.wikiart.org/en/paintings-by-style"]

    def parse(self, response):
        for style_url in response.xpath('//ul[@class="dictionaries-list"]/li[@class="dottedItem"]/a/@href').getall():
            yield response.follow(style_url, callback=self.parse_style)

    def parse_style(self, response):
        name = clean_name(
            response.xpath('//div[@class="dictionary-illustration-container"]//h1/text()').get(),
            response.xpath('//main/header/h1/text()').get(),
        )
        if not name:
            self.logger.warning("No name found at %s", response.url)
            return
        link = response.url

        # WikiArt no longer serves the dictionary description server-side:
        # style/movement/school pages are client-rendered (AngularJS SPA) and the
        # old dictionary-description-text markup is gone, so Description is None.
        # The selector is kept intentionally to pick the description back up if
        # WikiArt restores the markup (see issue #43).
        description_raw = response.xpath('//p[@class="dictionary-description-text"]').get()
        description = BeautifulSoup(description_raw, features="lxml").get_text() if description_raw else description_raw

        itemid = item_id(response.url)
        yield StyleItem({
            "Id": itemid,
            "Name": name,
            "Link": link,
            "Description": description,
        })



