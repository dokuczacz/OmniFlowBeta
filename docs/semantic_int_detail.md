# Latest Semantic INT Artifacts

The WP7 sync run that completed after the Responses output fix produced the following five semantic artifacts (the most recent entries in Azurite). Each section cites the interaction ID, summary, category, confidence, signal level, tags, and timestamp so you can review exactly what the new `INT_*` blobs contain.

1. **`users/MarioBros/interactions/semantic/INT_20260105_110253_420030.json`**
   - Summary: Read index file; `read_blob_file` showed `index.jsonl` is newline-delimited JSON with one record per interaction.
   - Category: `PS`
   - Confidence: `0.95`
   - Signal: `high`
   - Tags: `read-index`, `ndjson`, `index-structure`
   - Timestamp: `2026-01-05T12:03:20.563162Z`

2. **`users/MarioBros/interactions/semantic/INT_20260105_110716_767360.json`**
   - Summary: Listed blobs, noted there are 10 INT files, index/indexer queue present, and file sizes vary.
   - Category: `PS`
   - Confidence: `0.89`
   - Signal: `high`
   - Tags: `quality-assessment`, `int-count`, `indexer`
   - Timestamp: `2026-01-05T12:03:20.623179Z`

3. **`users/MarioBros/interactions/semantic/INT_20260105_110911_920589.json`**
   - Summary: Recommended reading DEEP samples and index entries to confirm schema stability.
   - Category: `PS`
   - Confidence: `0.86`
   - Signal: `medium`
   - Tags: `recommendation`, `deep-read`, `schema-check`
   - Timestamp: `2026-01-05T12:03:20.675302Z`

4. **`users/MarioBros/interactions/semantic/INT_20260105_111113_314056.json`**
   - Summary: Read sample INT/index data; confirmed each INT file exposes `interaction_id`, metadata, and index mapping.
   - Category: `PS`
   - Confidence: `0.95`
   - Signal: `high`
   - Tags: `read-samples`, `field-confirmation`, `ndjson-index`
   - Timestamp: `2026-01-05T12:03:20.723873Z`

5. **`users/MarioBros/interactions/semantic/INT_20260105_111531_541442.json`**
   - Summary: Verified that INT files contain `user_message`, `assistant_response`, and embedded metadata; index maps each INT correctly.
   - Category: `PS`
   - Confidence: `0.95`
   - Signal: `high`
   - Tags: `confirmation`, `mapping`, `metadata`
   - Timestamp: `2026-01-05T12:03:20.761754Z`
