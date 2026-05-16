
import asyncio
from sqlalchemy import select, delete, func, text
from ks.domain.models import KnowledgeFact, KnowledgeTag
from apps.api.database import SessionLocal

async def dedup_facts():
    async with SessionLocal() as session:
        print("Deduplicating knowledge_fact...")
        # CTE to find duplicates
        # We keep the one with the lowest ID (first inserted)
        find_dups_sql = text("""
            SELECT id FROM (
                SELECT id,
                ROW_NUMBER() OVER (
                    PARTITION BY document_id, subject, predicate, object 
                    ORDER BY created_at ASC
                ) as row_num
                FROM knowledge_fact
            ) t
            WHERE row_num > 1
        """)
        
        result = await session.execute(find_dups_sql)
        ids_to_delete = [row[0] for row in result.all()]
        
        if ids_to_delete:
            print(f"Deleting {len(ids_to_delete)} duplicate facts...")
            # Delete in chunks if necessary, but here we can probably do it in one go if not too many
            await session.execute(
                delete(KnowledgeFact).where(KnowledgeFact.id.in_(ids_to_delete))
            )
            await session.commit()
            print("Facts deduplicated.")
        else:
            print("No duplicate facts found.")

async def dedup_tags():
    async with SessionLocal() as session:
        print("Deduplicating knowledge_tag...")
        find_dups_sql = text("""
            SELECT id FROM (
                SELECT id,
                ROW_NUMBER() OVER (
                    PARTITION BY document_id, tag_type, tag_value 
                    ORDER BY created_at ASC
                ) as row_num
                FROM knowledge_tag
            ) t
            WHERE row_num > 1
        """)
        
        result = await session.execute(find_dups_sql)
        ids_to_delete = [row[0] for row in result.all()]
        
        if ids_to_delete:
            print(f"Deleting {len(ids_to_delete)} duplicate tags...")
            await session.execute(
                delete(KnowledgeTag).where(KnowledgeTag.id.in_(ids_to_delete))
            )
            await session.commit()
            print("Tags deduplicated.")
        else:
            print("No duplicate tags found.")

async def main():
    await dedup_facts()
    await dedup_tags()

if __name__ == "__main__":
    asyncio.run(main())
