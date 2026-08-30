import os
import httpx
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables (optional if already loaded in main FastAPI app)
load_dotenv()


async def get_zoom_access_token() -> str:
    """
    Retrieves a Zoom Server-to-Server OAuth access token.
    """
    account_id = os.getenv("ZOOM_ACCOUNT_ID")
    client_id = os.getenv("ZOOM_CLIENT_ID")
    client_secret = os.getenv("ZOOM_CLIENT_SECRET")

    if not all([account_id, client_id, client_secret]):
        raise ValueError("Zoom credential environment variables are missing.")

    url = "https://zoom.us/oauth/token"
    params = {
        "grant_type": "account_credentials",
        "account_id": account_id
    }

    async with httpx.AsyncClient() as client:
        try:
            # httpx automatically encodes auth=(user, pass) into a Basic Auth header
            response = await client.post(
                url,
                params=params,
                auth=(client_id, client_secret)
            )
            response.raise_for_status()

            data = response.json()
            return data["access_token"]

        except httpx.HTTPStatusError as e:
            # Raise a clear exception containing the Zoom API error details
            error_msg = f"Zoom Token API Error [{e.response.status_code}]: {e.response.text}"
            raise RuntimeError(error_msg) from e


async def create_zoom_meeting(topic: str, start_time: datetime, duration: int = 30) -> str:
    """
    Creates a scheduled Zoom meeting and returns the join URL.

    :param topic: The meeting topic/title.
    :param start_time: A datetime object representing the meeting start time.
    :param duration: Meeting duration in minutes.
    :return: The URL to join the Zoom meeting.
    """
    token = await get_zoom_access_token()
    url = "https://api.zoom.us/v2/users/me/meetings"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Format datetime strictly to ISO 8601 as required by Zoom (e.g., "YYYY-MM-DDTHH:MM:SSZ")
    start_time_iso = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "topic": topic,
        "type": 2,  # Scheduled meeting
        "start_time": start_time_iso,
        "duration": duration,
        "settings": {
            "host_video": True,
            "participant_video": True,
            "waiting_room": True
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            return data["join_url"]

        except httpx.HTTPStatusError as e:
            error_msg = f"Zoom Meeting Creation Error [{e.response.status_code}]: {e.response.text}"
            raise RuntimeError(error_msg) from e