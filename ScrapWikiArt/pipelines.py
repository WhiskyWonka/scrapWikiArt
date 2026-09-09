# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

import logging
import sqlite3
from datetime import datetime, timezone

from ScrapWikiArt import db
from ScrapWikiArt.items import ImageItem

logger = logging.getLogger(__name__)


def _now_iso():
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ScrapwikiartPipeline:
    def process_item(self, item, spider):
        return item


class SQLiteWorksPipeline:
    """Persist ImageItem rows into the works table via INSERT OR IGNORE.

    Priority 2 in the wikiart spider — runs after ImagesPipeline (priority 1)
    so `images` is populated before the DB insert.
    """

    def open_spider(self, spider):
        self.db_path = db.default_db_path(spider.settings)
        self.conn = db.connect(self.db_path)
        self._db_errors = 0
        db.create_tables(self.conn)

    def process_item(self, item, spider):
        if not isinstance(item, ImageItem):
            return item
        row = dict(item)
        images = row.get("images")
        if not images:
            logger.debug("No image for %s — skipping DB insert", item.get("Id"))
            return item
        image_path = images[0]["path"]
        item_id = row.get("Id")
        row["ImagePath"] = image_path
        # works.scraped_at is NOT NULL — stamp rows that lack it (e.g. when
        # the pipeline runs without the spider setting the field).
        row.setdefault("scraped_at", _now_iso())
        try:
            cursor = db.insert_ignore(self.conn, "works", row)
            if cursor.rowcount == 0:
                # INSERT was ignored — row exists. Fill ImagePath only if
                # the existing row has none yet.
                self.conn.execute(
                    "UPDATE works SET ImagePath = ? WHERE Id = ? AND ImagePath IS NULL",
                    (image_path, item_id),
                )
        except sqlite3.Error:
            self._db_errors += 1
            logger.warning(
                "DB error inserting item %s into works: %s",
                row.get("Id"), item,
            )
        return item

    def close_spider(self, spider):
        if self.conn is not None:
            self.conn.close()
            self.conn = None


class SQLiteDictionaryPipeline:
    """Persist dictionary items (Artist/Style/Movement/School) via INSERT OR IGNORE.

    Dispatches to the correct table using db.table_for_item.
    """

    def open_spider(self, spider):
        self.db_path = db.default_db_path(spider.settings)
        self.conn = db.connect(self.db_path)
        self._db_errors = 0
        db.create_tables(self.conn)

    def process_item(self, item, spider):
        table = db.table_for_item(item)
        if table is None:
            return item
        try:
            db.insert_ignore(self.conn, table, dict(item))
        except sqlite3.Error:
            self._db_errors += 1
            logger.warning(
                "DB error inserting item %s into %s: %s",
                item.get("Id"), table, item,
            )
        return item

    def close_spider(self, spider):
        if self.conn is not None:
            self.conn.close()
            self.conn = None


class SQLiteUpdatePipeline:
    """Write back WikiDescription/WikiLink to the item's source table.

    Used by the DuckDuckGo spiders: dispatches by item type and performs an
    UPDATE ... SET WikiDescription=?, WikiLink=? WHERE Id (design D5/DD.5).
    Unknown Ids are a silent no-op; non-matching item types pass through.
    """

    def open_spider(self, spider):
        self.db_path = db.default_db_path(spider.settings)
        self.conn = db.connect(self.db_path)
        self._db_errors = 0
        db.create_tables(self.conn)

    def process_item(self, item, spider):
        table = db.table_for_item(item)
        if table is None:
            return item
        row = dict(item)
        fields = {}
        if row.get("WikiDescription") is not None:
            fields["WikiDescription"] = row["WikiDescription"]
        if row.get("WikiLink") is not None:
            fields["WikiLink"] = row["WikiLink"]
        item_id = row.get("Id")
        if item_id is not None and fields:
            try:
                db.update_fields(self.conn, table, item_id, fields)
            except sqlite3.Error:
                self._db_errors += 1
                logger.warning(
                    "DB error updating item %s in %s: %s",
                    item_id, table, item,
                )
        return item

    def close_spider(self, spider):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
