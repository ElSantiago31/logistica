import asyncio, asyncpg
async def main():
    for pwd in ['postgres', 'logistica_dev_2024', 'admin', '']:
        try:
            c = await asyncpg.connect(host='localhost', port=5432, user='postgres', password=pwd, database='postgres')
            print(f'CONNECTED with password: {pwd!r}')
            r = await c.fetchval('SELECT version()')
            print(f'PostgreSQL: {r}')
            await c.close()
            return pwd
        except Exception as e:
            print(f'Failed with {pwd!r}: {e}')
    print('Could not connect with any password')
asyncio.run(main())