"""Setup database: create user and databases."""
import asyncio
import asyncpg

POSTGRES_PASSWORD = input("Enter the postgres superuser password: ")

async def main():
    # Connect as postgres
    conn = await asyncpg.connect(
        host="localhost", port=5432,
        user="postgres", password=POSTGRES_PASSWORD,
        database="postgres"
    )
    
    # Create user
    try:
        await conn.execute("CREATE USER logistica WITH PASSWORD 'logistica_dev_2024'")
        print("✅ User 'logistica' created")
    except Exception as e:
        print(f"User: {e}")
    
    # Create databases
    try:
        await conn.execute("CREATE DATABASE logistica OWNER logistica")
        print("✅ Database 'logistica' created")
    except Exception as e:
        print(f"DB logistica: {e}")
    
    try:
        await conn.execute("CREATE DATABASE logistica_test OWNER logistica")
        print("✅ Database 'logistica_test' created")
    except Exception as e:
        print(f"DB logistica_test: {e}")
    
    await conn.close()
    print("\nDone! Now run: alembic upgrade head")

asyncio.run(main())