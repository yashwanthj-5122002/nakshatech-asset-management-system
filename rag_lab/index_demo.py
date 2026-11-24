
import hashlib
import os
import time
from pathlib import Path

from google import genai

BASE = Path(__file__).resolve().parent
DOCUMENT = BASE / "knowledge" / "drone_demo.txt"
STORE_FILE = BASE / "store_id.txt"
INDEX_MARKER = BASE / "drone_demo_indexed.txt"

key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not key:
    raise SystemExit("Gemini API key is missing")

if not DOCUMENT.exists():
    raise SystemExit("drone_demo.txt is missing")

client = genai.Client(api_key=key)

if STORE_FILE.exists() and STORE_FILE.read_text().strip():
    store_name = STORE_FILE.read_text().strip()
    print("Using existing store:", store_name)
else:
    store = client.file_search_stores.create(
        config={"display_name": "NakshaTech RAG Training"}
    )

    store_name = store.name
    STORE_FILE.write_text(store_name, encoding="utf-8")
    print("Created store:", store_name)

checksum = hashlib.sha256(DOCUMENT.read_bytes()).hexdigest()
index_signature = f"{store_name}|{checksum}"

if (
    INDEX_MARKER.exists()
    and INDEX_MARKER.read_text().strip() == index_signature
):
    print("Document already indexed. Skipping duplicate upload.")
else:
    print("Uploading document...")

    operation = client.file_search_stores.upload_to_file_search_store(
        file=str(DOCUMENT),
        file_search_store_name=store_name,
        config={"display_name": "Drone Survey Training Guide"},
    )

    while not operation.done:
        time.sleep(5)
        operation = client.operations.get(operation)

    if getattr(operation, "error", None):
        raise RuntimeError(str(operation.error))

    INDEX_MARKER.write_text(index_signature, encoding="utf-8")
    print("SUCCESS: Document indexed")

print("Knowledge store:", store_name)
