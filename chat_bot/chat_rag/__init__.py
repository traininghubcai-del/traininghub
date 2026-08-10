"""chat_rag — data ingest + RAG projections (indexes) over the canonical tables.

Nothing here talks to Llama. It loads data_global/*.csv, builds lean JSON indexes
(index_classes.json, index_dealers.json) the chat retrieves against, and formats
retrieved rows into a CONTEXT block using prompt_templates.yaml.
"""
