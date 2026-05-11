-- 1. Create a dummy source if not exists
INSERT INTO source_registry (id, name, root_url, source_type, approval_status, language)
VALUES (
    '88888888-8888-4888-a888-888888888888',
    'Personalized Medical Library',
    'https://personalized.health',
    'GUIDELINE_SOURCE',
    'APPROVED_ACTIVE',
    'en'
) ON CONFLICT DO NOTHING;

-- 2. Create a dummy document for clinical protocols
INSERT INTO document_registry (id, source_id, canonical_url, title, status)
VALUES (
    '99999999-9999-4999-b999-999999999999',
    '88888888-8888-4888-a888-888888888888',
    'https://personalized.health/protocols',
    'Clinical PCOS, Endometriosis & Cortisol Interventions',
    'INDEXED'
) ON CONFLICT DO NOTHING;

-- 3. Insert matching facts for user profile
DELETE FROM knowledge_fact WHERE document_id = '99999999-9999-4999-b999-999999999999';

INSERT INTO knowledge_fact (id, document_id, fact_type, fact_text, subject, predicate, object, confidence, validation_status)
VALUES 
(
    gen_random_uuid(),
    '99999999-9999-4999-b999-999999999999',
    'CLINICAL_INSIGHT',
    'Drinking spearmint tea twice daily has anti-androgenic properties and significantly reduces free testosterone levels in women with Polycystic Ovary Syndrome (PCOS).',
    'spearmint tea',
    'reduces',
    'PCOS',
    0.95,
    'VALID'
),
(
    gen_random_uuid(),
    '99999999-9999-4999-b999-999999999999',
    'CLINICAL_INSIGHT',
    'Daily Omega-3 fatty acid supplementation improves insulin sensitivity, lowers inflammatory markers, and helps manage weight gain in individuals with insulin resistance.',
    'Omega-3 supplementation',
    'improves',
    'Insulin Resistance',
    0.92,
    'VALID'
),
(
    gen_random_uuid(),
    '99999999-9999-4999-b999-999999999999',
    'CLINICAL_INSIGHT',
    'Consuming hot water with turmeric and ghee on an empty stomach first thing in the morning reduces systemic inflammation and blunts early-morning cortisol stress spikes.',
    'turmeric and ghee',
    'reduces',
    'Cortisol stress',
    0.88,
    'VALID'
),
(
    gen_random_uuid(),
    '99999999-9999-4999-b999-999999999999',
    'CLINICAL_INSIGHT',
    'Walking on an inclined treadmill for 15-20 minutes in the morning promotes morning fat oxidation and targets deep visceral belly fat.',
    'inclined treadmill walk',
    'improves',
    'Belly fat',
    0.85,
    'VALID'
),
(
    gen_random_uuid(),
    '99999999-9999-4999-b999-999999999999',
    'CLINICAL_INSIGHT',
    'Taking Zinc and Magnesium supplements after dinner reduces stomach bloating, eases menstrual cramps associated with Endometriosis, and improves sleep quality.',
    'Zinc and Magnesium',
    'reduces',
    'Stomach bloating',
    0.90,
    'VALID'
),
(
    gen_random_uuid(),
    '99999999-9999-4999-b999-999999999999',
    'CLINICAL_INSIGHT',
    'Meeting a target of 50-70g of plant-based protein daily supports satiety, prevents muscle loss, and assists in reducing weight growth from insulin resistance.',
    'plant-based protein',
    'benefits',
    'weight management',
    0.91,
    'VALID'
),
(
    gen_random_uuid(),
    '99999999-9999-4999-b999-999999999999',
    'CLINICAL_INSIGHT',
    'Anti-inflammatory herbs like Spearmint tea and Turmeric help manage pain and severe bloating associated with Adenomyosis and Endometriosis.',
    'Spearmint tea',
    'manages',
    'Adenomyosis',
    0.87,
    'VALID'
);
