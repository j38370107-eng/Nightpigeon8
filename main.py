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

    bot = None
    if token:
        from bot.core.bot import NightpigeonBot
        bot = NightpigeonBot()

    app = create_app(bot=bot)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)

    if bot:
        log.info(f"Starting Nightpigeon bot + FastAPI on port {port}")
        server_task = asyncio.create_task(server.serve())
        try:
            await bot.start(token)
        except Exception as e:
            log.error(f"Bot login failed ({e}) — continuing in dashboard-only mode")
        await server_task
    else:
        log.warning("DISCORD_TOKEN not set — starting dashboard only")
        await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
