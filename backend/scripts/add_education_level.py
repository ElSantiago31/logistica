"""Add education_level column to operators table."""
import sys
sys.path.insert(0, r'c:\Users\Karen\Downloads\logistica\backend')

import asyncio
from sqlalchemy import text
from app.database import engine


async def run():
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE operators ADD COLUMN IF NOT EXISTS education_level VARCHAR(50)"
        ))
        print("Column education_level added successfully!")


if __name__ == "__main__":
    asyncio.run(run())