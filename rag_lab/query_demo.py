import os
from pathlib import Path
from google import genai

BASE = Path(__file__).resolve().parent
store_name = (BASE / "store_id.txt").read_text().strip()

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

response = client.interactions.create(
    model="gemini-3.5-flash-lite",
    input=(
        "Using the uploaded training document, "
        "what is the reference code? "
        "Also list three questions to ask a client "
        "requesting a drone survey. "
        "Do not invent answers."
    ),
    tools=[{
        "type": "file_search",
        "file_search_store_names": [store_name]
    }]
)

for step in response.steps:
    if step.type == "model_output":
        for block in step.content:
            if block.type == "text":
                print(block.text)

                for annotation in block.annotations or []:
                    if annotation.type == "file_citation":
                        print(
                            "Source:",
                            annotation.file_name
                        )