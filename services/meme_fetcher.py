"""services/meme_fetcher.py"""

import logging
import aiohttp

logger = logging.getLogger("bump-bot")

MEME_API_URL = "https://meme-api.com/gimme"


class MemeFetcher:
    """Encapsula la obtención de un meme desde una fuente externa.
    Si mañana cambias de API, solo tocas esta clase."""

    async def get_meme(self, subreddit: str | None = None) -> dict | None:
        url = f"{MEME_API_URL}/{subreddit}" if subreddit else MEME_API_URL
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Meme API respondió {resp.status}")
                        return None
                    data = await resp.json()
                    if data.get("nsfw"):
                        return await self.get_meme(subreddit)  # reintenta
                    return {
                        "title": data["title"],
                        "image_url": data["url"],
                        "post_link": data["postLink"],
                        "subreddit": data["subreddit"],
                    }
        except Exception as e:
            logger.error(f"Error obteniendo meme: {e}")
            return None