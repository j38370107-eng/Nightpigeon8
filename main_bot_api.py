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
log = logging.getLogger("nightpigeon.bot_api")


async def main():
    token = os.environ.get("DISCORD_TOKEN")
    port = int(os.environ.get("PORT", 5000))

    if not token:
        raise RuntimeError("DISCORD_TOKEN is required for the bot+api service")

    from bot.core.bot import NightpigeonBot
    bot = NightpigeonBot()
    app = create_app(bot=bot, serve_dashboard=False)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    log.info(f"Starting Nightpigeon bot + API (no dashboard) on port {port}")
    await asyncio.gather(bot.start(token), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
