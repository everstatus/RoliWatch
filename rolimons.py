import aiohttp

ITEMS_URL = "https://www.rolimons.com/itemapi/itemdetails"

# Rolimons item detail indices
IDX_NAME  = 0
IDX_ACRO  = 1
IDX_RAP   = 2
IDX_VALUE = 3
IDX_TREND = 7

_session: aiohttp.ClientSession | None = None


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            headers={"User-Agent": "RoliWatch Discord Bot"}
        )
    return _session


async def close():
    if _session and not _session.closed:
        await _session.close()


async def fetch_all_items() -> dict:
    """Return the full Rolimons item catalogue as {item_id_str: [...fields]}."""
    session = await _get_session()
    async with session.get(ITEMS_URL) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
    return data.get("items", {})


async def fetch_item(item_id: int) -> dict | None:
    """Return parsed info for a single item, or None if not found."""
    all_items = await fetch_all_items()
    raw = all_items.get(str(item_id))
    if raw is None:
        return None
    return {
        "id":    item_id,
        "name":  raw[IDX_NAME],
        "acro":  raw[IDX_ACRO],
        "rap":   raw[IDX_RAP]   if raw[IDX_RAP]   != -1 else None,
        "value": raw[IDX_VALUE] if raw[IDX_VALUE]  != -1 else None,
        "trend": raw[IDX_TREND] if len(raw) > IDX_TREND else None,
    }
