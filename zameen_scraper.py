import logging
import os
import random
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.zameen.com"
URL_TEMPLATE = "https://www.zameen.com/Rentals_Houses_Property/Islamabad-3-{page}.html"

CSV_FILE = "data/zameen_rent.csv"
EXCEL_FILE = "data/zameen_rent.xlsx"
RAW_CSV_FILE = "data/raw_rows.csv"

TIMEOUT = 15
MAX_TRIES = 4
WAIT_BETWEEN_SCRAPING = (5, 10)
WAIT_BEFORE_RETRY = (10, 15)
TOTAL_PAGES = 10

USER_AGENT = "MyScrapingPractice/1.0 (+https://github.com/YOUR_USERNAME/zameen-scraper)"

FIELDS = ["title", "price", "location", "area", "beds", "baths", "link"]

ISLAMABAD_PATTERN = (
    r"(F-\d+|G-\d+|E-\d+|I-\d+|H-\d+|DHA|Bahria|Park View|"
    r"Gulberg|Bani Gala|Chak Shahzad|Soan Garden|PWD|"
    r"Korang Town|Diplomatic Enclave|Islamabad)"
)

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

logger = logging.getLogger("zameen_scraper")

def wait_randomly(delay_range):
    seconds = random.uniform(*delay_range)
    logger.info("Waiting %.1f seconds...", seconds)
    time.sleep(seconds)

def download(url, check_function=None):
    for attempt in range(1, MAX_TRIES + 1):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
            if response.status_code == 200:
                if check_function is None or check_function(response):
                    return response
            elif response.status_code in (401, 403, 429):
                logger.warning("Blocked (%s). Stopping.", response.status_code)
                return None
        except Exception as error:
            logger.warning("Attempt %s failed: %s", attempt, error)

        if attempt < MAX_TRIES:
            wait_randomly(WAIT_BEFORE_RETRY)
    return None

def to_price(text):
    if text is None:
        return None
    match = re.search(r"[\d,]+\.?\d*", str(text))
    if not match:
        return None
    try:
        number = float(match.group().replace(",", ""))
    except ValueError:
        return None

    lowered = str(text).lower()
    if "crore" in lowered:
        number *= 10_000_000
    elif "lakh" in lowered:
        number *= 100_000
    elif "thousand" in lowered:
        number *= 1_000
    return number

def to_area(text):
    if text is None:
        return None
    match = re.search(r"\d+(\.\d+)?", str(text))
    if not match:
        return None
    number = float(match.group())

    lowered = str(text).lower()
    if "kanal" in lowered:
        return number * 20
    if "marla" in lowered:
        return number
    return None

def to_location(text):
    if not text:
        return None
    first_part = str(text).split(",")[0].strip()
    return first_part or None

def get_property_links(soup):
    property_links = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("/Property/"):
            property_links.add(href)
    return property_links

def find_card(soup, href):
    anchor = soup.find("a", href=href)
    card = anchor
    while card is not None and "PKR" not in card.get_text():
        card = card.parent

    if card is None:
        return None

    hrefs = set()
    for a in card.find_all("a", href=True):
        if a["href"].startswith("/Property/"):
            hrefs.add(a["href"])
    if len(hrefs) != 1:
        return None
    return card

def get_title(card):
    heading = card.find(["h2", "h3"])
    if heading:
        text = heading.get_text(strip=True)
        if text:
            return text
    return None

def parse_details(tokens):
    result = {
        "price": None,
        "location": None,
        "area": None,
        "beds": None,
        "baths": None,
    }

    start = None
    for i, token in enumerate(tokens):
        if token.upper() == "PKR":
            start = i
            break

    if start is None or start + 2 >= len(tokens):
        return result

    result["price"] = to_price(tokens[start + 1])
    result["location"] = to_location(tokens[start + 2])

    numbers = []
    for token in tokens[start + 3:]:
        if re.fullmatch(r"\d{1,2}", token):
            numbers.append(int(token))
        elif re.fullmatch(r"\d+(\.\d+)?\s*(Marla|Kanal)", token, flags=re.IGNORECASE):
            result["area"] = to_area(token)
            break

    if len(numbers) == 2:
        result["beds"], result["baths"] = numbers

    return result

def parse_card(card, href):
    tokens = list(card.stripped_strings)
    details = parse_details(tokens)
    return {
        "title": get_title(card),
        "price": details["price"],
        "location": details["location"],
        "area": details["area"],
        "beds": details["beds"],
        "baths": details["baths"],
        "link": BASE_URL + href,
    }

def clean_and_filter_data(rows):
    df = pd.DataFrame(rows, columns=FIELDS)

    initial_count = len(df)
    logger.info("Cleaning & Filtering shuru. Shuruat mein rows: %s", initial_count)

    df = df.drop_duplicates(subset=["link"], keep="first")
    df = df.dropna(subset=["price", "location", "area"])

    def is_islamabad(row):
        text_to_check = str(row["location"]) + " " + str(row["title"])
        if "rawalpindi" in text_to_check.lower() and not re.search(
            r"[EFGHI]-\d+", text_to_check, re.IGNORECASE
        ):
            return False
        return bool(re.search(ISLAMABAD_PATTERN, text_to_check, re.IGNORECASE))

    df = df[df.apply(is_islamabad, axis=1)]

    final_count = len(df)
    logger.info(
        "Cleaning ke baad Islamabad rows: %s (Hataye gaye: %s)",
        final_count,
        initial_count - final_count,
    )
    return df

def save_to_files(df, csv_filename, excel_filename):
    os.makedirs(os.path.dirname(csv_filename), exist_ok=True)

    df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
    logger.info("CSV save ho gayi: %s", csv_filename)

    df.to_excel(excel_filename, index=False)
    logger.info("Excel save ho gayi: %s", excel_filename)

def main():
    setup_logging()
    all_rows = []

    for page in range(1, TOTAL_PAGES + 1):
        url = URL_TEMPLATE.format(page=page)
        logger.info("Page %s scrape ho raha hai: %s", page, url)

        response = download(url, check_function=lambda r: "/Property/" in r.text)
        if response is None:
            logger.warning("Page %s download nahi hua. Skip.", page)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        property_links = get_property_links(soup)
        logger.info("Page %s par %s links mile.", page, len(property_links))

        for href in sorted(property_links):
            card = find_card(soup, href)
            if card is None:
                continue
            all_rows.append(parse_card(card, href))

        if page < TOTAL_PAGES:
            wait_randomly(WAIT_BETWEEN_SCRAPING)

    print("Total rows collected:", len(all_rows))

    os.makedirs("data", exist_ok=True)
    pd.DataFrame(all_rows, columns=FIELDS).to_csv(
        RAW_CSV_FILE, index=False, encoding="utf-8-sig"
    )

    cleaned_df = clean_and_filter_data(all_rows)
    save_to_files(cleaned_df, CSV_FILE, EXCEL_FILE)

if __name__ == "__main__":
    main()