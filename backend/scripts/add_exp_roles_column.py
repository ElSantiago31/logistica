import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def run():
    e = create_async_engine('postgresql+asyncpg://logistica:logistica_dev_2024@localhost:5432/logistica')
    async with e.begin() as conn:
        await conn.execute(text('ALTER TABLE operators ADD COLUMN IF NOT EXISTS experience_roles TEXT'))
    print('Column experience_roles added to operators')
    await e.dispose()

asyncio.run(run())