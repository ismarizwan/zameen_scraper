# Zameen.com Islamabad Rental Scraper

A Python-based web scraper that extracts rental property data from Zameen.com for Islamabad, cleans the data, and exports it into CSV and Excel formats.

## Features

- Multi-page scraping with polite delays to avoid rate-limiting
- Automatic retries on failed requests
- Robust price parsing (supports PKR, Lakh, Crore, Thousand)
- Area normalization (converts Kanal to Marla for consistency)
- Filters data to ensure only authentic Islamabad properties are included

## Requirements

Ensure you have Python installed, then install the required dependencies:

```bash
pip install -r requirements.txt
