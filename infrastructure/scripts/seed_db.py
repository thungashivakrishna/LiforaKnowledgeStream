"""Seed loader — loads framework taxonomy and source seed data into the database."""
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ks.config.settings import get_settings
from ks.domain.enums import DiscoveryMode, Framework, SourceApprovalStatus, SourceType
from ks.domain.models import SourceFrameworkMap, SourceRegistry

SEED_DIR = Path(__file__).parent.parent / "seed"


async def seed_sources(session: AsyncSession) -> None:
    sources_path = SEED_DIR / "sources_seed.json"
    sources = json.loads(sources_path.read_text())

    for entry in sources:
        # Check for existing
        from sqlalchemy import select
        existing = await session.execute(
            select(SourceRegistry).where(SourceRegistry.root_url == entry["root_url"])
        )
        if existing.scalar_one_or_none():
            print(f"  SKIP (exists): {entry['name']}")
            continue

        source = SourceRegistry(
            id=uuid.uuid4(),
            name=entry["name"],
            root_url=entry["root_url"],
            source_type=SourceType(entry["source_type"].upper()),
            language=entry.get("language", "en"),
            region=entry.get("region"),
            trust_tier=entry.get("trust_tier", 2),
            approval_status=SourceApprovalStatus(entry.get("approval_status", "CANDIDATE").upper()),
            crawl_policy=entry.get("crawl_policy"),
            freshness_days=entry.get("freshness_days", 30),
        )
        session.add(source)
        await session.flush()

        # Framework maps
        primary = entry.get("primary_framework")
        if primary:
            session.add(SourceFrameworkMap(
                id=uuid.uuid4(),
                source_id=source.id,
                framework=Framework(primary.upper()),
                is_primary=True,
            ))
        for sec in entry.get("secondary_frameworks", []):
            session.add(SourceFrameworkMap(
                id=uuid.uuid4(),
                source_id=source.id,
                framework=Framework(sec.upper()),
                is_primary=False,
            ))

        print(f"  ADDED: {entry['name']}")

    await session.commit()
    print(f"Source seeding complete — {len(sources)} entries processed.")


async def seed_discovery_profiles(session: AsyncSession) -> None:
    from ks.domain.models import DiscoveryFilterProfile
    profiles_path = SEED_DIR / "discovery_profiles_seed.json"
    if not profiles_path.exists():
        return
        
    profiles = json.loads(profiles_path.read_text())
    for entry in profiles:
        from sqlalchemy import select
        existing = await session.execute(
            select(DiscoveryFilterProfile).where(DiscoveryFilterProfile.name == entry["name"])
        )
        if existing.scalar_one_or_none():
            print(f"  SKIP (exists): {entry['name']}")
            continue
            
        profile = DiscoveryFilterProfile(
            id=uuid.uuid4(),
            name=entry["name"],
            mode=DiscoveryMode(entry["mode"].upper()),
            topics=entry["topics"],
            frameworks=entry["frameworks"],
            max_candidates=entry.get("max_candidates", 100),
            per_source_limit=entry.get("per_source_limit", 20),
        )
        session.add(profile)
        print(f"  ADDED: {entry['name']}")
        
    await session.commit()
    print(f"Discovery profile seeding complete — {len(profiles)} entries processed.")


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.db.url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        print("Seeding sources...")
        await seed_sources(session)
        print("Seeding discovery profiles...")
        await seed_discovery_profiles(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
