
import os
from pathlib import Path
from google import genai

BASE = Path(__file__).resolve().parent

key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not key:
    raise SystemExit("Gemini API key is missing")

store_name = (BASE / "store_id.txt").read_text().strip()

client = genai.Client(api_key=key)

response = client.interactions.create(
    model="gemini-3.5-flash-lite",
    input=(
        "According to the uploaded Drone Survey Training Guide, "
        "what is its exact reference code? "
        "Also name three client details required before survey planning. "
        "Do not invent missing information."
    ),
    tools=[
        {
            "type": "file_search",
            "file_search_store_names": [store_name],
        }
    ],
)

answers = []
source_count = 0

for step in response.steps:
    if step.type != "model_output":
        continue

    for block in step.content:
        if block.type != "text":
            continue

        print(block.text)
        answers.append(block.text)

        for citation in block.annotations or []:
            if citation.type == "file_citation":
                source_count += 1
                print("Source:", citation.file_name)

answer_text = "\n".join(answers)

print("\n--- RAG TEST ---")

if "DEMO-DRONE-042" in answer_text and source_count > 0:
    print("PASS: Expected code found with file citation")
else:
    print("REVIEW: Exact code or supporting citation missing")
