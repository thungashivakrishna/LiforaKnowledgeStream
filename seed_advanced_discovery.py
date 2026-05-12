import asyncio
import uuid
from sqlalchemy import select
from apps.api.database import AsyncSessionFactory
from ks.domain.models import DiscoveryFilterProfile
from ks.domain.enums import DiscoveryMode

async def seed_profiles():
    async with AsyncSessionFactory() as session:
        existing = await session.execute(select(DiscoveryFilterProfile).where(DiscoveryFilterProfile.name == "Clinical Diagnostic Framework"))
        if existing.scalar_one_or_none():
            print("Diagnostic profiles already seeded!")
            return

        diag_profile = DiscoveryFilterProfile(
            id=uuid.uuid4(),
            name="Clinical Diagnostic Framework",
            mode=DiscoveryMode.FOCUSED,
            topics=["biomarkers", "reference_intervals", "lab_testing", "radiology", "blood_chemistry"],
            synonyms={"labs": ["reference ranges", "normal values", "panic levels"]},
            frameworks=["DIAGNOSTICS_AND_LABS", "EVIDENCE_BASED_WESTERN_MEDICINE"],
            max_candidates=200,
            per_source_limit=50
        )

        pharm_profile = DiscoveryFilterProfile(
            id=uuid.uuid4(),
            name="Pharmacology & RX Vault",
            mode=DiscoveryMode.FOCUSED,
            topics=["pharmacokinetics", "drug_interactions", "contraindications", "dosages", "prescription_guidelines"],
            synonyms={"rx": ["drugs", "medication", "pharmaceutical"]},
            frameworks=["PHARMACOLOGY_MEDICINE", "EVIDENCE_BASED_WESTERN_MEDICINE"],
            max_candidates=200,
            per_source_limit=50
        )

        session.add(diag_profile)
        session.add(pharm_profile)
        await session.commit()
        print("🚀 Successfully seeded new specialty Discovery Filter Profiles into system!")

if __name__ == "__main__":
    asyncio.run(seed_profiles())
