#!/usr/bin/env python3
"""
CLI helper to seed deterministic synthetic statutory registry data into PostgreSQL.
"""

import sys
import os
import asyncio

# Ensure backend root is on sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.database import AsyncSessionLocal
from app.services.mock_seeder import seed_all_mock_sources


async def run_seed():
    print("=" * 60)
    print("Seeding Deterministic Synthetic Statutory Data (1,000 / source)...")
    print("=" * 60)
    async with AsyncSessionLocal() as session:
        counts = await seed_all_mock_sources(session)
        print("\nSeeding Results:")
        for source, count in counts.items():
            print(f"  - {source.upper():<12}: {count} records verified")
    print("=" * 60)
    print("Statutory mock seeding complete & idempotent.")


if __name__ == "__main__":
    asyncio.run(run_seed())
