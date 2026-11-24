#!/usr/bin/env python3
"""One-query smoke test of the existing File Search store."""
import os
from pathlib import Path
from google import genai

base = Path(__file__).resolve().parent
store_file = base / 'store_id.txt'
if not store_file.exists():
    raise SystemExit('Missing store_id.txt. Verify your existing store first.')
store = store_file.read_text(encoding='utf-8').strip()
key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
if not key:
    raise SystemExit('Gemini API key missing.')
model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
client = genai.Client(api_key=key)
question = 'From reference NBD-LIDAR-203, what are the first three missing details to clarify for a 42 km road LiDAR project if only length and LAZ output are supplied?'
response = client.interactions.create(
    model=model,
    input=question + ' Cite the uploaded document. Do not invent quantities.',
    tools=[{'type': 'file_search', 'file_search_store_names': [store]}],
)
sources = []
for step in response.steps:
    if step.type != 'model_output':
        continue
    for block in step.content:
        if block.type == 'text':
            print(block.text)
            for annotation in (block.annotations or []):
                if annotation.type == 'file_citation':
                    sources.append(annotation.file_name)
print('File citations:', ', '.join(sources) if sources else 'NONE (review retrieval before claiming success)')
