"""
Rate Management Module for Booking.com Extranet Bot

This module handles automated rate changes for different date ranges
in the Booking.com partner extranet calendar system.

Updated for the new monthly calendar UI (inline side panel, no modals).
"""

import asyncio
import logging
import csv
import os
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class RateManager:
    """
    Handles rate management operations for Booking.com extranet
    """

    def __init__(self, page: Page):
        self.page = page
        self.csv_data = []
        self.load_csv_data()

    async def human_delay(self, min_seconds: float = 2, max_seconds: float = 5, wait_for_network: bool = True) -> None:
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug(f"Human delay: {delay:.1f}s")
        await asyncio.sleep(delay)
        if wait_for_network:
            try:
                await self.page.wait_for_load_state('networkidle', timeout=5000)
            except Exception:
                pass

    # ─── CSV Data Management ──────────────────────────────────────

    def load_csv_data(self) -> None:
        try:
            self.csv_path = os.path.join(os.path.dirname(__file__), 'public', 'seasonal_room_prices_optimized.csv')
            with open(self.csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                self.csv_data = list(reader)

            if self.csv_data and 'Status' not in self.csv_data[0]:
                for record in self.csv_data:
                    record['Status'] = 'pending'
                self.save_csv_data()

            logger.info(f"Loaded {len(self.csv_data)} pricing records from CSV")
            completed = sum(1 for r in self.csv_data if r.get('Status', '').lower() == 'completed')
            logger.info(f"Status summary: {completed} completed, {len(self.csv_data) - completed} pending")
        except Exception as e:
            logger.error(f"Failed to load CSV data: {e}")
            self.csv_data = []

    def save_csv_data(self) -> None:
        try:
            if not self.csv_data:
                return
            fieldnames = list(self.csv_data[0].keys())
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.csv_data)
        except Exception as e:
            logger.error(f"Failed to save CSV data: {e}")

    def mark_record_completed(self, record: Dict) -> None:
        try:
            for i, csv_record in enumerate(self.csv_data):
                if (csv_record['Room ID'] == record['Room ID'] and
                    csv_record['Date Range'] == record['Date Range'] and
                    csv_record['Price'] == record['Price']):
                    self.csv_data[i]['Status'] = 'completed'
                    logger.info(f"Marked completed: Room {record['Room ID']}, {record['Date Range']}")
                    break
            self.save_csv_data()
        except Exception as e:
            logger.error(f"Failed to mark record completed: {e}")

    def get_progress_summary(self) -> Dict:
        total = len(self.csv_data)
        completed = sum(1 for r in self.csv_data if r.get('Status', '').lower() == 'completed')
        pending = total - completed
        pct = (completed / total * 100) if total > 0 else 0
        return {
            'total_records': total,
            'completed_records': completed,
            'pending_records': pending,
            'progress_percentage': round(pct, 2)
        }

    def reset_all_status(self) -> bool:
        try:
            for record in self.csv_data:
                record['Status'] = 'pending'
            self.save_csv_data()
            logger.info(f"Reset {len(self.csv_data)} records to pending")
            return True
        except Exception as e:
            logger.error(f"Failed to reset statuses: {e}")
            return False

    def get_room_data_by_id(self, room_id: str) -> List[Dict]:
        return [r for r in self.csv_data
                if r['Room ID'] == room_id and r.get('Status', '').lower() != 'completed']

    def get_pending_records(self) -> List[Dict]:
        return [r for r in self.csv_data if r.get('Status', '').lower() != 'completed']

    # ─── Date Parsing ─────────────────────────────────────────────

    def parse_date_range(self, date_range_str: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        try:
            date_range_str = date_range_str.replace('\u2013', '-').replace('\u2014', '-')
            start_str, end_str = date_range_str.split(' - ')
            current_year = datetime.now().year
            start_date = datetime.strptime(f"{start_str.strip()} {current_year}", "%B %d %Y")
            end_date = datetime.strptime(f"{end_str.strip()} {current_year}", "%B %d %Y")
            if start_date > end_date:
                end_date = end_date.replace(year=current_year + 1)
            cutoff = datetime(2027, 1, 1)
            if end_date > cutoff:
                end_date = cutoff
            return start_date, end_date
        except Exception as e:
            logger.error(f"Failed to parse date range '{date_range_str}': {e}")
            return None, None

    # ─── Navigation ───────────────────────────────────────────────

    async def navigate_to_property(self, hotel_id: str) -> bool:
        """Navigate from group homepage to a specific property page"""
        try:
            current_url = self.page.url

            # If already on the right property page (not group page), skip
            if f'hotel_id={hotel_id}' in current_url and 'groups' not in current_url:
                logger.info(f"Already on property {hotel_id}")
                return True

            # Navigate via direct URL (most reliable)
            import re
            ses_match = re.search(r'ses=([a-f0-9]+)', current_url)
            ses = ses_match.group(1) if ses_match else ''
            prop_url = f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/home.html?lang=xu&ses={ses}&hotel_id={hotel_id}"
            await self.page.goto(prop_url, wait_until='networkidle')
            await asyncio.sleep(3)  # Extra wait for JS rendering
            logger.info(f"Navigated to property {hotel_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to property {hotel_id}: {e}")
            return False

    async def navigate_to_calendar(self, hotel_id: str = None) -> bool:
        """
        Navigate to the rates & availability calendar.
        If hotel_id is provided, navigates to that property first.
        """
        try:
            logger.info("Navigating to rates & availability calendar...")

            # If we're on the group page, navigate to the property first
            if hotel_id:
                if not await self.navigate_to_property(hotel_id):
                    return False

            # Click on "Rates & availability" to expand submenu
            availability_btn = 'li[data-nav-tag="availability"] button'
            await self.page.wait_for_selector(availability_btn, state='visible', timeout=20000)
            await self.page.click(availability_btn)
            await asyncio.sleep(1)

            # Click on "Calendar" submenu
            calendar_link = 'li[data-nav-tag="availability_calendar"] a'
            await self.page.wait_for_selector(calendar_link, timeout=5000)
            await self.page.click(calendar_link)
            await self.page.wait_for_load_state('networkidle', timeout=15000)

            # Verify we're on the calendar page
            if 'calendar' in self.page.url:
                logger.info("Successfully navigated to calendar page")
                return True
            else:
                logger.error(f"Not on calendar page. URL: {self.page.url}")
                return False

        except Exception as e:
            logger.error(f"Failed to navigate to calendar: {e}")
            return False

    # ─── Calendar Side Panel Operations ───────────────────────────

    async def set_date_range(self, start_date: datetime, end_date: datetime) -> bool:
        """Set the date range in the calendar side panel"""
        try:
            # Format dates as the calendar expects: "Apr 1, 2026"
            start_str = start_date.strftime('%b %d, %Y').replace(' 0', ' ')
            end_str = end_date.strftime('%b %d, %Y').replace(' 0', ' ')

            # Also try YYYY-MM-DD format as fallback
            start_iso = start_date.strftime('%Y-%m-%d')
            end_iso = end_date.strftime('%Y-%m-%d')

            logger.info(f"Setting date range: {start_str} to {end_str}")

            # Clear and set start date
            start_input = self.page.locator('#selection-start-date')
            await start_input.click()
            await self.page.keyboard.press('Meta+a')
            await self.page.keyboard.press('Backspace')
            await asyncio.sleep(0.3)
            await start_input.type(start_str, delay=random.randint(30, 60))
            await self.page.keyboard.press('Tab')
            await asyncio.sleep(1)

            # Clear and set end date
            end_input = self.page.locator('#selection-end-date')
            await end_input.click()
            await self.page.keyboard.press('Meta+a')
            await self.page.keyboard.press('Backspace')
            await asyncio.sleep(0.3)
            await end_input.type(end_str, delay=random.randint(30, 60))
            await self.page.keyboard.press('Tab')
            await asyncio.sleep(1)

            logger.info(f"Date range set: {start_str} to {end_str}")
            return True

        except Exception as e:
            logger.error(f"Error setting date range: {e}")
            return False

    async def set_rooms_to_sell(self, num_rooms: str) -> bool:
        """Set the number of rooms to sell using the dropdown"""
        try:
            logger.info(f"Setting rooms to sell: {num_rooms}")

            rooms_select = self.page.locator('#roomsToSell')
            try:
                await rooms_select.wait_for(timeout=3000)
            except Exception:
                logger.warning("Rooms to sell dropdown not found")
                return False

            # Check if the dropdown is disabled (read-only in monthly view)
            is_disabled = await rooms_select.is_disabled()
            if is_disabled:
                logger.info("Rooms to sell dropdown is disabled in this view, skipping")
                return True

            # The options are like "0 options to sell", "1 option to sell", "2 options to sell"
            options = await rooms_select.locator('option').all()
            target_value = None
            for opt in options:
                text = (await opt.inner_text()).strip()
                if text.startswith(str(num_rooms)):
                    target_value = await opt.get_attribute('value')
                    break

            if target_value is not None:
                await rooms_select.select_option(value=target_value)
            else:
                await rooms_select.select_option(index=int(num_rooms))

            logger.info(f"Set rooms to sell to: {num_rooms}")
            return True

        except Exception as e:
            logger.error(f"Error setting rooms to sell: {e}")
            return False

    async def set_open_status(self, open: bool = True) -> bool:
        """Set the open/closed status for the selected dates"""
        try:
            status_text = "Open" if open else "Closed"
            logger.info(f"Setting booking status to: {status_text}")

            # The open/closed toggles are at the top of the side panel
            # Try clicking the "Open" or "Closed" text/radio
            target = self.page.locator(f'text="{status_text}"').first
            try:
                await target.click(timeout=5000)
                logger.info(f"Set status to: {status_text}")
                return True
            except Exception:
                # Try radio button approach
                if open:
                    radio = self.page.locator('input[value="open"], input[value="true"]').first
                else:
                    radio = self.page.locator('input[value="closed"], input[value="false"]').first
                await radio.click(timeout=5000)
                logger.info(f"Set status to: {status_text} (via radio)")
                return True

        except Exception as e:
            logger.error(f"Error setting open status: {e}")
            return False

    async def set_price(self, price: str) -> bool:
        """Set the price for all visible rate plan inputs"""
        try:
            logger.info(f"Setting price to: {price}")

            # Find all price inputs (they have IDs like price-52150641)
            price_inputs = self.page.locator('input[id^="price-"]')
            count = await price_inputs.count()

            if count == 0:
                logger.error("No price input fields found")
                return False

            # Set price for the first rate plan (Standard Rate)
            # We can set all if needed
            first_input = price_inputs.first
            await first_input.click()
            await self.page.keyboard.press('Meta+a')
            await self.page.keyboard.press('Backspace')
            await asyncio.sleep(0.3)
            await first_input.type(str(price), delay=random.randint(30, 60))
            await self.page.keyboard.press('Tab')

            logger.info(f"Set price to {price} for first rate plan")
            return True

        except Exception as e:
            logger.error(f"Error setting price: {e}")
            return False

    async def click_save(self) -> bool:
        """Click the Save button on the calendar side panel"""
        try:
            save_btn = self.page.locator('button:has-text("Save")').last
            await save_btn.click(timeout=5000)
            logger.info("Clicked Save button")

            # Wait for save to complete
            await self.human_delay(3, 6, wait_for_network=True)

            # Check for error messages
            try:
                error = self.page.locator(':has-text("Whoops"), :has-text("error"), :has-text("failed")')
                if await error.count() > 0 and await error.first.is_visible():
                    error_text = await error.first.inner_text()
                    logger.error(f"Save error: {error_text[:100]}")
                    return False
            except Exception:
                pass

            logger.info("Save completed successfully")
            return True

        except Exception as e:
            logger.error(f"Error clicking save: {e}")
            return False

    # ─── Main Processing ──────────────────────────────────────────

    async def process_all_rooms(self, hotel_id: str = None) -> bool:
        """
        Process all pending records from CSV using the calendar side panel.

        Args:
            hotel_id: Optional hotel ID to navigate to first
        """
        try:
            progress = self.get_progress_summary()
            logger.info(f"Starting: {progress['completed_records']}/{progress['total_records']} completed ({progress['progress_percentage']}%)")

            pending = self.get_pending_records()
            if not pending:
                logger.info("No pending records to process!")
                return True

            logger.info(f"Processing {len(pending)} pending records...")

            for i, record in enumerate(pending):
                logger.info("=" * 50)
                logger.info(f"Record {i+1}/{len(pending)}: {record['Room Name']} - {record['Date Range']} - ${record['Price']}")
                logger.info("=" * 50)

                success = await self.process_single_record(record)

                if success:
                    self.mark_record_completed(record)
                    progress = self.get_progress_summary()
                    logger.info(f"Progress: {progress['completed_records']}/{progress['total_records']} ({progress['progress_percentage']}%)")
                else:
                    logger.error(f"Failed to process record: {record['Room Name']} - {record['Date Range']}")

                # Delay between records
                await self.human_delay(3, 6)

            # Final summary
            final = self.get_progress_summary()
            logger.info("=" * 60)
            logger.info("FINAL SUMMARY")
            logger.info(f"  Total: {final['total_records']}")
            logger.info(f"  Completed: {final['completed_records']}")
            logger.info(f"  Pending: {final['pending_records']}")
            logger.info(f"  Progress: {final['progress_percentage']}%")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"Error in process_all_rooms: {e}")
            return False

    async def process_single_record(self, record: Dict) -> bool:
        """Process a single CSV record using the calendar side panel"""
        try:
            # Parse and validate dates
            start_date, end_date = self.parse_date_range(record['Date Range'])
            if not start_date or not end_date:
                logger.error(f"Failed to parse date range: {record['Date Range']}")
                return False

            today = datetime.now()
            if end_date.date() < today.date():
                logger.info(f"Skipping {record['Date Range']} - entirely in the past")
                return True  # Not an error, just skip

            if start_date.date() < today.date():
                start_date = today
                logger.info(f"Adjusted start date to today: {start_date.strftime('%Y-%m-%d')}")

            # Step 1: Set date range
            logger.info("Step 1: Setting date range...")
            if not await self.set_date_range(start_date, end_date):
                return False

            await self.human_delay(1, 3)

            # Step 2: Set rooms to sell
            logger.info("Step 2: Setting rooms to sell...")
            if not await self.set_rooms_to_sell(record['Number of Rooms']):
                logger.warning("Could not set rooms to sell, continuing...")

            # Step 3: Set open status
            logger.info("Step 3: Setting room status to Open...")
            if not await self.set_open_status(open=True):
                logger.warning("Could not set open status, continuing...")

            # Step 4: Set price
            logger.info("Step 4: Setting price...")
            if not await self.set_price(record['Price']):
                return False

            await self.human_delay(1, 2, wait_for_network=False)

            # Step 5: Save
            logger.info("Step 5: Saving changes...")
            if not await self.click_save():
                return False

            logger.info(f"✓ Successfully processed: {record['Room Name']} - {record['Date Range']} @ ${record['Price']}")
            return True

        except Exception as e:
            logger.error(f"Error processing record: {e}")
            return False

    # ─── Page Info (Debug) ────────────────────────────────────────

    async def get_current_page_info(self) -> Dict:
        try:
            return {
                'url': self.page.url,
                'title': await self.page.title(),
            }
        except Exception as e:
            logger.error(f"Error getting page info: {e}")
            return {}
