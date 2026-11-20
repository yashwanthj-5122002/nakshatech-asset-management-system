import os
import time
from pathlib import Path
from google import genai

BASE = Path(__file__).resolve().parent
KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not KEY:
    raise SystemExit("ERROR: Gemini API key is missing")

document = BASE / "knowledge" / "drone_demo.txt"

if not document.exists():
    raise SystemExit("ERROR: drone_demo.md not found")

client = genai.Client(api_key=KEY)

store_file = BASE / "store_id.txt"

if store_file.exists():
    store_name = store_file.read_text().strip()
    print("Using existing store:", store_name)
else:
    print("Creating Gemini knowledge store...")

    store = client.file_search_stores.create(
        config={
            "display_name": "NakshaTech RAG Training"
        }
    )

    store_name = store.name
    store_file.write_text(store_name, encoding="utf-8")

    print("Knowledge store created:", store_name)

print("Uploading knowledge document...")

operation = client.file_search_stores.upload_to_file_search_store(
    file=str(document),
    file_search_store_name=store_name,
    config={
        "display_name": "Drone Survey Training Guide",
        "mime_type": "text/plain",
    },
)

while not operation.done:
    time.sleep(5)
    operation = client.operations.get(operation)

if getattr(operation, "error", None):
    raise RuntimeError(str(operation.error))

print("SUCCESS: Knowledge indexing completed!")
print("Store ID:", store_name)
