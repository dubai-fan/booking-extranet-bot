"""
Reservations Module for Booking.com Extranet Bot

Handles downloading reservation data from the group-level reservations page.
Scrapes the table across all pages and builds an Excel file.
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Optional, List, Dict
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Columns as scraped from the table (in table order)
SCRAPE_COLUMNS = [
    'Property ID', 'Property name', 'Location', 'Booker name',
    'Arrival', 'Departure', 'Status', 'Total payment',
    'Commission', 'Reservation number', 'Booked on',
]

# Output column order matching Booking.com's own export format exactly
OUTPUT_COLUMNS = [
    'Property name', 'Location', 'Booker name',
    'Arrival', 'Departure', 'Booked on', 'Status',
    'Total payment', 'Commission', 'Reservation number',
    'Property ID',  # extra column we have that Booking doesn't
]


class ReservationsManager:
    """Handles reservation data extraction from Booking.com extranet"""

    def __init__(self, page: Page):
        self.page = page
        self.downloads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
        os.makedirs(self.downloads_dir, exist_ok=True)

    def _get_session(self) -> str:
        match = re.search(r'ses=([a-f0-9]+)', self.page.url)
        return match.group(1) if match else ''

    async def _wait_for_table(self) -> int:
        """Wait for table data to load, return number of rows"""
        for _ in range(15):
            await asyncio.sleep(2)
            guest_links = await self.page.query_selector_all('table tbody tr a')
            if len(guest_links) > 0:
                rows = await self.page.query_selector_all('table tbody tr')
                return len(rows)
        return 0

    async def _scrape_current_page(self) -> List[List[str]]:
        """Scrape all rows from the currently displayed table page"""
        rows_data = []
        rows = await self.page.query_selector_all('table tbody tr')
        for row in rows:
            cells = await row.query_selector_all('td')
            if len(cells) < 10:
                continue
            cell_texts = []
            for cell in cells:
                text = (await cell.inner_text()).strip().replace('\n', ' ')
                cell_texts.append(text)
            rows_data.append(cell_texts)
        return rows_data

    async def _get_total_count(self) -> int:
        """Extract total reservation count from pagination text like '1-30 of 117 reservations'"""
        try:
            body_text = await self.page.inner_text('body')
            match = re.search(r'of\s+(\d+)\s+reservation', body_text)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return 0

    async def _scrape_all_pages(self, start_date: str, end_date: str, date_type: str) -> List[List[str]]:
        """Navigate to reservations page and scrape all pages. Returns raw row data."""
        ses = self._get_session()
        if not ses:
            logger.error("No session token found")
            return []

        type_map = {'arrival': 'ARRIVAL', 'departure': 'DEPARTURE', 'booking': 'BOOKING'}
        url_date_type = type_map.get(date_type, 'ARRIVAL')
        url = (
            f"https://admin.booking.com/hotel/hoteladmin/groups/reservations/index.html"
            f"?lang=xu&ses={ses}"
            f"&dateFrom={start_date}&dateTo={end_date}&dateType={url_date_type}"
        )
        logger.info(f"Navigating to reservations: {start_date} to {end_date} ({date_type})...")
        await self.page.goto(url, wait_until='networkidle')

        row_count = await self._wait_for_table()
        if row_count == 0:
            logger.warning("No reservations found for this date range")
            return []

        total = await self._get_total_count()
        logger.info(f"Found {total} reservations ({row_count} on first page)")

        all_data = await self._scrape_current_page()
        logger.info(f"Scraped page 1: {len(all_data)} rows")

        page_num = 1
        while len(all_data) < total:
            page_num += 1
            try:
                next_btn = self.page.locator('button[aria-label="Next page"]')
                if not await next_btn.is_visible():
                    break
                await next_btn.click()
                await self._wait_for_table()
                page_data = await self._scrape_current_page()
                if not page_data:
                    break
                all_data.extend(page_data)
                logger.info(f"Scraped page {page_num}: {len(page_data)} rows (total: {len(all_data)})")
            except Exception as e:
                logger.warning(f"Error scraping page {page_num}: {e}")
                break

        return all_data

    async def get_reservations_data(
        self,
        start_date: str,
        end_date: str,
        date_type: str = 'arrival',
    ) -> List[Dict]:
        """
        Scrape reservations and return as list of dicts (for JSON output).
        """
        try:
            all_data = await self._scrape_all_pages(start_date, end_date, date_type)
            columns = SCRAPE_COLUMNS
            result = []
            for row in all_data:
                record = {}
                for i, col in enumerate(OUTPUT_COLUMNS):
                    if col in columns:
                        idx = columns.index(col)
                        record[col] = row[idx] if idx < len(row) else ''
                result.append(record)
            return result
        except Exception as e:
            logger.error(f"Error getting reservations data: {e}")
            return []

    async def download_reservations(
        self,
        start_date: str,
        end_date: str,
        date_type: str = 'arrival',
        output_dir: Optional[str] = None,
    ) -> Optional[str]:
        """
        Scrape reservations and build an Excel file.

        Returns:
            Path to the generated Excel file, or None on failure
        """
        try:
            save_dir = output_dir or self.downloads_dir
            os.makedirs(save_dir, exist_ok=True)

            all_data = await self._scrape_all_pages(start_date, end_date, date_type)

            import pandas as pd
            df = pd.DataFrame(all_data, columns=SCRAPE_COLUMNS[:len(all_data[0])] if all_data else SCRAPE_COLUMNS)
            df = df[[c for c in OUTPUT_COLUMNS if c in df.columns]]

            filename = f"Reservations_{start_date}_{end_date}.xlsx"
            file_path = os.path.join(save_dir, filename)
            df.to_excel(file_path, index=False, engine='openpyxl')

            size = os.path.getsize(file_path)
            logger.info(f"Excel file created: {file_path} ({len(all_data)} rows, {size} bytes)")
            return file_path

        except Exception as e:
            logger.error(f"Error downloading reservations: {e}")
            return None
