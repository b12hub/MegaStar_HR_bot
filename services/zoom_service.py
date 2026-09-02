import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks

load_dotenv()


async def get_zoom_access_token(timeout: float = 20.0) -> str:
    """Retrieve a Zoom OAuth access token with a bounded timeout and crisp error handling."""
    account_id = os.getenv("ZOOM_ACCOUNT_ID")
    client_id = os.getenv("ZOOM_CLIENT_ID")
    client_secret = os.getenv("ZOOM_CLIENT_SECRET")

    if not all([account_id, client_id, client_secret]):
        raise ValueError("Zoom credential environment variables are missing.")

    url = "https://zoom.us/oauth/token"
    params = {"grant_type": "account_credentials", "account_id": account_id}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, params=params, auth=(client_id, client_secret))
            response.raise_for_status()
            data = response.json()
            return data["access_token"]
    except httpx.TimeoutException as exc:
        raise TimeoutError("Zoom access token request timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Zoom Token API Error [{exc.response.status_code}]: {exc.response.text}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unexpected Zoom auth failure: {exc}") from exc


async def create_zoom_meeting(
    topic: str,
    start_time: datetime,
    duration: int = 30,
    background_tasks: Optional[BackgroundTasks] = None,
    timeout: float = 20.0,
) -> str:
    """Create a scheduled Zoom meeting and return the join URL; safe for FastAPI background scheduling."""
    if background_tasks is not None:
        background_tasks.add_task(create_zoom_meeting, topic, start_time, duration, timeout=timeout)
        return ""

    token = await get_zoom_access_token(timeout=timeout)
    url = "https://api.zoom.us/v2/users/me/meetings"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    start_time_iso = start_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "topic": topic,
        "type": 2,
        "start_time": start_time_iso,
        "duration": duration,
        "settings": {
            "host_video": True,
            "participant_video": True,
            "waiting_room": True,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["join_url"]
    except httpx.TimeoutException as exc:
        raise TimeoutError("Zoom meeting creation timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Zoom Meeting Creation Error [{exc.response.status_code}]: {exc.response.text}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unexpected Zoom meeting creation failure: {exc}") from exc
