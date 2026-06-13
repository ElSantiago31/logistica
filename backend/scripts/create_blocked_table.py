"""Create blocked_documents table directly (PostgreSQL)."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import engine
from sqlalchemy import text

async def main():
    async with engine.begin() as conn:
        # Check if table exists (PostgreSQL)
        result = await conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'blocked_documents')"
        ))
        exists = result.scalar()
        if exists:
            print("Table blocked_documents already exists")
            return

        await conn.execute(text("""
            CREATE TABLE blocked_documents (
                id UUID PRIMARY KEY,
                document_type VARCHAR(10) NOT NULL,
                document_number VARCHAR(20) NOT NULL,
                reason TEXT,
                blocked_by UUID REFERENCES users(id) ON DELETE SET NULL,
                operator_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                operator_name VARCHAR(201),
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_blocked_documents_document_type ON blocked_documents(document_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_blocked_documents_document_number ON blocked_documents(document_number)"
        ))
        print("Table blocked_documents created successfully")

if __name__ == "__main__":
    asyncio.run(main())