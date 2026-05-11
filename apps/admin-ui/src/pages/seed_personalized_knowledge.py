import uuid
import psycopg2
from datetime import datetime

# Connection parameters
conn_str = "postgresql://ks_user:ks_password@localhost:5432/knowledge_stream"

FACTS = [
    {
        "subject": "spearmint tea",
        "predicate": "reduces",
        "object": "PCOS",
        "fact_text": "Drinking spearmint tea twice daily has anti-androgenic properties and significantly reduces free testosterone levels in women with Polycystic Ovary Syndrome (PCOS).",
        "confidence": 0.95
    },
    {
        "subject": "Omega-3 supplementation",
        "predicate": "improves",
        "object": "Insulin Resistance",
        "fact_text": "Daily Omega-3 fatty acid supplementation improves insulin sensitivity, lowers inflammatory markers, and helps manage weight gain in individuals with insulin resistance.",
        "confidence": 0.92
    },
    {
        "subject": "turmeric and ghee",
        "predicate": "reduces",
        "object": "Cortisol stress",
        "fact_text": "Consuming hot water with turmeric and ghee on an empty stomach first thing in the morning reduces systemic inflammation and blunts early-morning cortisol stress spikes.",
        "confidence": 0.88
    },
    {
        "subject": "inclined treadmill walk",
        "predicate": "improves",
        "object": "Belly fat",
        "fact_text": "Walking on an inclined treadmill for 15-20 minutes in the morning promotes morning fat oxidation and targets deep visceral belly fat.",
        "confidence": 0.85
    },
    {
        "subject": "Zinc and Magnesium",
        "predicate": "reduces",
        "object": "Stomach bloating",
        "fact_text": "Taking Zinc and Magnesium supplements after dinner reduces stomach bloating, eases menstrual cramps associated with Endometriosis, and improves sleep quality.",
        "confidence": 0.90
    },
    {
        "subject": "plant-based protein",
        "predicate": "benefits",
        "object": "weight management",
        "fact_text": "Meeting a target of 50-70g of plant-based protein daily supports satiety, prevents muscle loss, and assists in reducing weight growth from insulin resistance.",
        "confidence": 0.91
    },
    {
        "subject": "Spearmint tea",
        "predicate": "manages",
        "object": "Adenomyosis",
        "fact_text": "Anti-inflammatory herbs like Spearmint tea and Turmeric help manage pain and severe bloating associated with Adenomyosis and Endometriosis.",
        "confidence": 0.87
    }
]

def seed_data():
    try:
        conn = psycopg2.connect(conn_str)
        cursor = conn.cursor()
        
        # 1. Ensure a valid Source exists
        cursor.execute("SELECT id FROM source_registry LIMIT 1;")
        source_row = cursor.fetchone()
        if not source_row:
            source_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO source_registry (id, name, root_url, source_type, approval_status) VALUES (%s, %s, %s, %s, %s);",
                (source_id, "Personalized Health Library", "https://personalized.health", "KNOWLEDGE_BASE_SOURCE", "APPROVED")
            )
        else:
            source_id = source_row[0]
            
        # 2. Ensure a valid Document exists
        doc_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO document_registry (id, source_id, canonical_url, title, status) VALUES (%s, %s, %s, %s, %s);",
            (doc_id, source_id, "https://personalized.health/profile-protocol", "Personalized Profile Protocol Insights", "COMPLETED")
        )
        
        # 3. Seed facts
        for fact in FACTS:
            fact_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO knowledge_fact (id, document_id, fact_type, fact_text, subject, predicate, object, confidence, validation_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);",
                (fact_id, doc_id, "CLINICAL_INSIGHT", fact["fact_text"], fact["subject"], fact["predicate"], fact["object"], fact["confidence"], "APPROVED")
            )
            
        conn.commit()
        print(f"Successfully seeded {len(FACTS)} highly tailored personalized guidelines into the database under document {doc_id[:8]}!")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Failed to seed data: {e}")

if __name__ == "__main__":
    seed_data()
