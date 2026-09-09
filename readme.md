
# WikiArt Scraper

This repository contains scrapers developed for 
[wikiart.org](https://www.wikiart.org/). The scraper is a part of the 
project [Art Guide](https://github.com/aguschin/art-guide) undertaken in 
[Practicing DS Skills in ML 
Competitions](https://harbour.space/data-science/courses/practicing-ds-skills-in-ml-competitions-alexander-guschin-875) and [Building ML-powered Applications](https://harbour.space/data-science/courses/building-ml-powered-application-alexander-guschin-960) 
classes. 

For our project, we required comprehensive metadata about art pieces, such 
as genres, styles, and other descriptors which were not present in other 
datasets I found. Thus, these scrapers are 
designed to extract all tabular information about Art Pieces, Artists, Art Movements, Schools and Styles.   
present on the website.

## Overview

The project consists of 5 crawlers:

1. **wikiart spider**: This crawler extracts comprehensive details and images of various art pieces from the WikiArt website.
2. **wikiart artists spider**: This crawler specializes in gathering information about artists.
3. **wikiart styles spider**: This crawler is focused on collecting extensive information about different art styles.
4. **wikiart movements spider**: This crawler delves into the world of art movements.
5. **wikiart schools spider**: This crawler concentrates on gathering comprehensive data about art schools.

In addition to the primary crawlers, the project includes DuckDuckGo spiders for updating descriptions in specific categories:

- **duck_duck_go.py**: Updates descriptions for art pieces.
- **duck_duck_go_artist.py**: Updates information about artists.
- **duck_duck_go_style.py**: Updates information about art styles.
- **duck_duck_go_movement.py**: Updates information about art movements.
- **duck_duck_go_school.py**: Updates information about art schools.

These DuckDuckGo spiders enhance and maintain the data integrity by fetching updated information for paintings, artists, styles, movements, and schools based on the existing datasets.

**Scraped Information for Artworks:**
- URL
- Title
- Original Title
- Author
- Author Link
- Date
- Styles (pipe-separated, e.g. `Cubism | Abstract Art`)
- StylesLinks (pipe-separated)
- Series
- Series Link
- Genre
- Genre Link
- Media
- Location
- Dimensions
- Description
- Wiki Description
- Wiki Link
- Tags
- Image URLs
- Images

**Scraped Information about Artists:**
- URL
- Name
- Original Name
- Birth Date
- Birthplace
- Death Date
- Death Place
- Active Years
- Nationality
- Art Movements
- Painting School
- Genres
- Fields
- Influenced On
- Influenced By
- Teachers
- Pupils
- Art Institutions
- Friends And Coworkers
- Description
- Wiki Description
- Wikipedia Link

**Scraped Information for Art Styles:**
- Name
- Link
- Description

**Scraped Information for Art Movements:**
- Name
- Link
- Description

**Scraped Information for Art Schools:**
- Name
- Link
- Description

The main objective is to extract detailed data about art pieces and artists from the website, providing valuable datasets for data science and machine learning endeavors.

*Scraping of 191265 images took **~14 hours** on a MacBook Pro (Retina, 
15-inch, Mid 2015, 2,2 GHz Quad-Core Intel Core i7). Scraping of 3521 
artists took **less than 10 
minutes***

## Prerequisites

- Python 3.x (3.10 is verified)
- Scrapy

## Installation

1. Clone this repository:
`git clone https://github.com/WhiskyWonka/scrapWikiArt`

2. Navigate to the repository and install the required packages:

`cd ScrapWikiArt`\
`pip install -r requirements.txt`

3. (Optional) To run the LLM-based data validation script
   (`data_validation_script.py`), additionally install the validation
   dependencies:

`pip install -r requirements-validation.txt`

| Crawler | Command                                                                                                                               |
|---------|---------------------------------------------------------------------------------------------------------------------------------------|
| Art Pieces Crawler | `scrapy crawl wikiart -o data/data.csv -t csv`                                                                                  |
| Artists Crawler | `scrapy crawl wikiart_artist -o data/artists.csv -t csv`                                                                        |
| Styles Crawler | `scrapy crawl wikiart_style -o data/styles.csv -t csv`                                                                          |
| Movements Crawler | `scrapy crawl wikiart_movement -o data/movements.csv -t csv`                                                                    |
| Schools Crawler | `scrapy crawl wikiart_school -o data/schools.csv -t csv`                                                                        |
| DuckDuckGo Crawler | `scrapy crawl duck_duck_go -a input_file=data/data.csv -o data/data_update.csv -t csv`                                       |
| DuckDuckGo Artist Spider | `scrapy crawl duck_duck_go_artist -a input_file=data/artists.csv -o data/artist_update.csv -t csv`                         |
| DuckDuckGo Styles Spider | `scrapy crawl duck_duck_go_style -a input_file=data/styles.csv -o data/styles_update.csv -t csv`                           |
| DuckDuckGo Movements Spider | `scrapy crawl duck_duck_go_movement -a input_file=data/movements.csv -o data/movements_update.csv -t csv`               |
| DuckDuckGo Schools Spider | `scrapy crawl duck_duck_go_school -a input_file=data/schools.csv -o data/schools_update.csv -t csv`                      |

> **Why `scrapy crawl` and not `scrapy runspider`?**
>
> `scrapy runspider <file.py>` executes the spider with the stock Scrapy
> defaults and **ignores the project's `ScrapWikiArt/settings.py`**. That
> means the polite-crawling configuration (see `settings.py`) does not
> apply: no `ROBOTSTXT_OBEY`, no `DOWNLOAD_DELAY`, no `AUTOTHROTTLE`, no
> retry on rate limits (429/5xx), and no concurrency caps. The Readme
> used to recommend `runspider`; the recommended commands above use
> `scrapy crawl <spider_name>` so every run applies the project settings.
> `runspider` still works, but only use it for one-off debugging when you
> deliberately want to skip the project configuration.

## Spider enablement (SPIDERS_ENABLED)

`SPIDERS_ENABLED` in `ScrapWikiArt/settings.py` decides which spiders may
crawl. The default is `["wikiart"]` — only `wikiart` crawls, the other 9
spiders no-op.

| Setting value | Effect |
|---------------|--------|
| `["wikiart"]` (default) | `wikiart` crawls; all other spiders no-op |
| `["duck_duck_go_artist", "wikiart"]` | Only the named spiders crawl |
| `[]` | Every spider no-ops (CI-safe kill switch) |
| unset / `None` | Falls back to the default `["wikiart"]` |

A disabled spider logs `Spider <name> is disabled via SPIDERS_ENABLED,
skipping` at INFO level, yields zero requests, and exits with code 0 — safe
for scripts and CI that invoke any spider name. When a spider is enabled it
crawls exactly as before.

`settings.py` is the ONLY supported configuration point: there is no CLI flag
to enable or disable spiders, and `scrapy crawl <name> -s SPIDERS_ENABLED=...`
is an unsupported side channel. Note that `scrapy list` always shows all 10
spiders regardless of this setting.

## Output

### Art Pieces Crawler

Image download is handled by Scrapy's `ImagesPipeline` (enabled via
`custom_settings` in the spider): the pipeline downloads the images listed
in the item's `image_urls` field into the `IMAGES_STORE` folder. By default
images go to `data/img` and data is saved in `data/data.csv`.

The download folder may be changed by editing `IMAGES_STORE` in the
spider's `custom_settings` (`ScrapWikiArt/spiders/wikiart.py`).

### Artists Crawler

By default, data will be saved in `data/artists.csv`.

### Styles Crawler

By default, data will be saved in `data/styles.csv`.

### Movements Crawler

By default, data will be saved in `data/movements.csv`.

### Schools Crawler

By default, data will be saved in `data/schools.csv`.