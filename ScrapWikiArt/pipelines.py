# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

from datetime import datetime, timezone

from ScrapWikiArt import db
from ScrapWikiArt.items import ImageItem


def _now_iso():
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ScrapwikiartPipeline:
    def process_item(self, item, spider):
        return item


class SQLiteWorksPipeline:
    """Persist ImageItem rows into the works table via INSERT OR IGNORE.

    Priority 1 in the wikiart spider — runs before ImagesPipeline (priority 2)
    so the DB row exists before images are downloaded.
    """

    def open_spider(self, spider):
        self.db_path = db.default_db_path(spider.settings)
        self.conn = db.connect(self.db_path)
        db.create_tables(self.conn)

    def process_item(self, item, spider):
        if not isinstance(item, ImageItem):
            return item
        row = dict(item)
        # works.scraped_at is NOT NULL — stamp rows that lack it (e.g. when
        # the pipeline runs without the spider setting the field).
        row.setdefault("scraped_at", _now_iso())
        db.insert_ignore(self.conn, "works", row)
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
        db.create_tables(self.conn)

    def process_item(self, item, spider):
        table = db.table_for_item(item)
        if table is None:
            return item
        db.insert_ignore(self.conn, table, dict(item))
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
            db.update_fields(self.conn, table, item_id, fields)
        return item

    def close_spider(self, spider):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
