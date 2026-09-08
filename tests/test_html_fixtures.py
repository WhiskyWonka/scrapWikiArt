import os
import unittest

import scrapy.http

from ScrapWikiArt.spiders.wikiart import WikiArtSpider
from ScrapWikiArt.spiders.wikiart_artist import WikiArtArtistSpider
from ScrapWikiArt.spiders.wikiart_style import WikiArtArtistSpider as WikiArtStyleSpider
from ScrapWikiArt.utils import item_id

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "rb") as fh:
        return fh.read()


def _build_response(fixture_filename, url):
    body = _load_fixture(fixture_filename)
    return scrapy.http.HtmlResponse(url=url, body=body, encoding="utf-8")


class TestParseItem(unittest.TestCase):
    def setUp(self):
        self.url = "https://www.wikiart.org/en/leonardo-da-vinci/mona-lisa-42097"
        response = _build_response("artwork.html", self.url)
        self.items = list(WikiArtSpider().parse_item(response))

    def test_parse_item_yields_one_item(self):
        self.assertEqual(len(self.items), 1)

    def test_title(self):
        self.assertEqual(self.items[0]["Title"], "Mona Lisa")

    def test_original_title(self):
        self.assertEqual(self.items[0]["OriginalTitle"], "La Gioconda")

    def test_author(self):
        self.assertEqual(self.items[0]["Author"], "Leonardo da Vinci")

    def test_author_link(self):
        self.assertEqual(
            self.items[0]["AuthorLink"], "wikiart.org/en/leonardo-da-vinci"
        )

    def test_date(self):
        self.assertEqual(self.items[0]["Date"], "1503 – 1519")

    def test_styles_pipe_joined(self):
        self.assertEqual(self.items[0]["Styles"], "Renaissance | High Renaissance")

    def test_styles_links_pipe_joined(self):
        self.assertIn("wikiart.org/en/renaissance", self.items[0]["StylesLinks"])
        self.assertIn("wikiart.org/en/high-renaissance", self.items[0]["StylesLinks"])

    def test_series(self):
        self.assertEqual(self.items[0]["Series"], "Self Portraits")

    def test_genre(self):
        self.assertEqual(self.items[0]["Genre"], "portrait")

    def test_media_list(self):
        self.assertEqual(self.items[0]["Media"], ["oil", "panel"])

    def test_location(self):
        self.assertEqual(
            self.items[0]["Location"], "Musée du Louvre, Paris, France"
        )

    def test_dimensions(self):
        self.assertEqual(self.items[0]["Dimensions"], "77 cm × 53 cm")

    def test_description(self):
        self.assertIn("Leonardo da Vinci", self.items[0]["Description"])

    def test_wiki_description(self):
        self.assertIn("oil painting", self.items[0]["WikiDescription"])

    def test_wiki_link(self):
        self.assertEqual(
            self.items[0]["WikiLink"], "https://en.wikipedia.org/wiki/Mona_Lisa"
        )

    def test_tags(self):
        tags = self.items[0]["Tags"]
        self.assertIn("sfumato", tags)
        self.assertIn("portrait", tags)
        self.assertIn("renaissance", tags)

    def test_image_urls(self):
        urls = self.items[0]["image_urls"]
        self.assertEqual(len(urls), 2)
        self.assertIn("mona-lisa-420x770.jpg", urls[0])
        self.assertIn("mona-lisa-840x1540.jpg", urls[1])

    def test_id_is_40_char_hex(self):
        import re
        self.assertRegex(self.items[0]["Id"], re.compile(r"^[0-9a-f]{40}$"))

    def test_id_matches_url(self):
        self.assertEqual(self.items[0]["Id"], item_id(self.url))


class TestParseArtist(unittest.TestCase):
    def setUp(self):
        self.url = "https://www.wikiart.org/en/leonardo-da-vinci"
        response = _build_response("artist.html", self.url)
        self.items = list(WikiArtArtistSpider().parse_artist(response))

    def test_parse_artist_yields_one_item(self):
        self.assertEqual(len(self.items), 1)

    def test_name(self):
        self.assertEqual(self.items[0]["Name"], "Leonardo da Vinci")

    def test_original_name(self):
        self.assertEqual(
            self.items[0]["OriginalName"],
            "Leonardo di ser Piero da Vinci",
        )

    def test_birth_date(self):
        self.assertEqual(self.items[0]["BirthDate"], "April 15, 1452")

    def test_birth_place(self):
        self.assertEqual(
            self.items[0]["BirthPlace"], "Anchiano, Republic of Florence"
        )

    def test_death_date(self):
        self.assertEqual(self.items[0]["DeathDate"], "May 2, 1519")

    def test_death_place(self):
        self.assertEqual(
            self.items[0]["DeathPlace"], "Amboise, Kingdom of France"
        )

    def test_active_years_label_stripped(self):
        self.assertEqual(self.items[0]["ActiveYears"], "1466 – 1519")

    def test_nationality(self):
        self.assertEqual(self.items[0]["Nationality"], "Italian")

    def test_art_movements(self):
        movements = self.items[0]["ArtMovements"]
        self.assertIn("High Renaissance", movements)
        self.assertIn("Italian Renaissance", movements)

    def test_description(self):
        self.assertIn("polymath", self.items[0]["Description"])

    def test_wiki_description(self):
        self.assertIn("painter, sculptor", self.items[0]["WikiDescription"])

    def test_wiki_link(self):
        self.assertEqual(
            self.items[0]["WikiLink"],
            "https://en.wikipedia.org/wiki/Leonardo_da_Vinci",
        )

    def test_id_matches_url(self):
        self.assertEqual(self.items[0]["Id"], item_id(self.url))


class TestParseStyle(unittest.TestCase):
    def setUp(self):
        self.url = "https://www.wikiart.org/en/style/imp-ressionism"
        response = _build_response("style.html", self.url)
        self.items = list(WikiArtStyleSpider().parse_style(response))

    def test_parse_style_yields_one_item(self):
        self.assertEqual(len(self.items), 1)

    def test_name(self):
        self.assertEqual(self.items[0]["Name"], "Impressionism")

    def test_description(self):
        self.assertIn("brush strokes", self.items[0]["Description"])

    def test_id_matches_url(self):
        self.assertEqual(self.items[0]["Id"], item_id(self.url))


class TestArtworkFixtureContract(unittest.TestCase):
    def setUp(self):
        self.raw = _load_fixture("artwork.html").decode("utf-8")

    def test_has_data_image_url(self):
        self.assertIn("data-image-url", self.raw)

    def test_has_image_variants_container(self):
        self.assertIn("image-variants-container", self.raw)

    def test_has_tags_cheaps(self):
        self.assertIn("tags-cheaps", self.raw)

    def test_has_info_tab_description(self):
        self.assertIn('id="info-tab-description"', self.raw)

    def test_has_wiki_link(self):
        self.assertIn('class="wiki-link"', self.raw)

    def test_has_itemprop_creator(self):
        self.assertIn('itemprop="creator"', self.raw)


if __name__ == "__main__":
    unittest.main()
