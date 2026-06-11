import asyncio
import os
import logging
import uvicorn
from api.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nightpigeon")


async def main():
    token = os.environ.get("DISCORD_TOKEN")
    port = int(os.environ.get("PORT", 5000))

    tasks = []

    if token:
        from bot.core.bot import NightpigeonBot
        bot = NightpigeonBot()
        app = create_app(bot)
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        log.info(f"Starting Nightpigeon bot + FastAPI on port {port}")
        tasks = [bot.start(token), server.serve()]
    else:
        log.warning("DISCORD_TOKEN not set — starting dashboard only (no Discord bot)")
        app = create_app(bot=None)
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        tasks = [server.serve()]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
