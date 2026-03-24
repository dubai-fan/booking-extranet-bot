"""
Messaging Module for Booking.com Extranet Bot

Handles listing and reading guest messages from the property inbox.
"""

import asyncio
import logging
import re
from typing import Optional, List, Dict
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class MessagingManager:
    """Handles guest messaging operations from Booking.com extranet"""

    def __init__(self, page: Page):
        self.page = page

    def _get_session(self) -> str:
        match = re.search(r'ses=([a-f0-9]+)', self.page.url)
        return match.group(1) if match else ''

    async def _navigate_to_inbox(self, hotel_id: str) -> bool:
        """Navigate to the reservation messages inbox for a property"""
        try:
            ses = self._get_session()
            url = (
                f"https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
                f"messaging/inbox.html?hotel_id={hotel_id}&ses={ses}&lang=en"
            )
            logger.info(f"Navigating to inbox for property {hotel_id}...")
            await self.page.goto(url, wait_until='domcontentloaded')
            await asyncio.sleep(5)  # Vue SPA needs time to render

            # Wait for the message list or filter to appear
            try:
                await self.page.wait_for_selector(
                    'select[data-test-id="inbox-conversation-filter-select"]',
                    timeout=15000,
                )
            except Exception:
                logger.warning("Filter dropdown not found, page may still be loading")
                await asyncio.sleep(5)

            return True
        except Exception as e:
            logger.error(f"Failed to navigate to inbox: {e}")
            return False

    async def list_messages(
        self,
        hotel_id: str,
        filter_type: str = 'unanswered',
    ) -> List[Dict]:
        """
        List messages from the inbox.

        Args:
            hotel_id: Property hotel ID
            filter_type: 'unanswered' (default), 'sent', or 'all'

        Returns:
            List of message dicts with guest_name, date, preview, status
        """
        try:
            if not await self._navigate_to_inbox(hotel_id):
                return []

            # Set the filter
            filter_map = {
                'unanswered': 'PENDING_PROPERTY',
                'sent': 'PENDING_GUEST',
                'all': 'ALL',
            }
            filter_value = filter_map.get(filter_type, 'PENDING_PROPERTY')

            try:
                await self.page.select_option(
                    'select[data-test-id="inbox-conversation-filter-select"]',
                    filter_value,
                    timeout=5000,
                )
                logger.info(f"Filter set to: {filter_type} ({filter_value})")
                await asyncio.sleep(3)
            except Exception:
                logger.warning("Could not set filter, using default")

            # Get the unanswered count from badge
            unanswered_count = 0
            try:
                badge = await self.page.query_selector('div[data-test-id="inbox-guest-counter"]')
                if badge and await badge.is_visible():
                    unanswered_count = int((await badge.inner_text()).strip())
            except Exception:
                pass

            # Scrape message list items
            messages = []
            msg_buttons = await self.page.query_selector_all('button.dadb648d92')

            for i, btn in enumerate(msg_buttons):
                try:
                    visible = await btn.is_visible()
                    if not visible:
                        continue

                    # Check bounding box to filter out non-message buttons
                    box = await btn.bounding_box()
                    if not box or box['width'] < 200 or box['height'] < 40:
                        continue

                    # Extract message details
                    name_el = await btn.query_selector('.list-item__title-text')
                    guest_name = (await name_el.inner_text()).strip() if name_el else 'Unknown'

                    # Date element
                    date_el = await btn.query_selector('.a91bd87e91')
                    date = (await date_el.inner_text()).strip() if date_el else ''

                    # Preview text
                    preview_el = await btn.query_selector('.b99b6ef58f')
                    preview = (await preview_el.inner_text()).strip() if preview_el else ''

                    messages.append({
                        'index': len(messages),
                        'guest_name': guest_name,
                        'date': date,
                        'preview': preview[:200],
                    })

                except Exception as e:
                    logger.debug(f"Error parsing message {i}: {e}")
                    continue

            # If we couldn't parse individual messages, try a broader approach
            if not messages and unanswered_count > 0:
                logger.info("Falling back to text-based message extraction")
                # Get all text from the message list area
                try:
                    list_area = await self.page.query_selector('.guest-tab--desktop')
                    if list_area:
                        text = await list_area.inner_text()
                        logger.info(f"Message list text: {text[:500]}")
                except Exception:
                    pass

            logger.info(f"Found {len(messages)} messages (unanswered badge: {unanswered_count})")

            return {
                'hotel_id': hotel_id,
                'filter': filter_type,
                'unanswered_count': unanswered_count,
                'messages': messages,
            }

        except Exception as e:
            logger.error(f"Error listing messages: {e}")
            return {'hotel_id': hotel_id, 'filter': filter_type, 'unanswered_count': 0, 'messages': []}

    async def read_conversation(
        self,
        hotel_id: str,
        message_index: int = 0,
    ) -> Optional[Dict]:
        """
        Open and read a specific conversation by clicking on it.

        Args:
            hotel_id: Property hotel ID
            message_index: Index of the message in the list (0-based)

        Returns:
            Dict with guest_name, reservation_info, and conversation messages
        """
        try:
            # Click on the message
            msg_buttons = await self.page.query_selector_all('button.dadb648d92')
            visible_buttons = []
            for btn in msg_buttons:
                box = await btn.bounding_box()
                if box and box['width'] > 200 and box['height'] > 40:
                    visible_buttons.append(btn)

            if message_index >= len(visible_buttons):
                logger.error(f"Message index {message_index} out of range ({len(visible_buttons)} messages)")
                return None

            await visible_buttons[message_index].click()
            await asyncio.sleep(3)

            # Read the conversation from the right panel
            conversation = {
                'index': message_index,
                'messages': [],
            }

            # Get the conversation container
            msg_list = await self.page.query_selector('.message-list')
            if msg_list:
                text = await msg_list.inner_text()
                conversation['full_text'] = text[:5000]

            return conversation

        except Exception as e:
            logger.error(f"Error reading conversation: {e}")
            return None
