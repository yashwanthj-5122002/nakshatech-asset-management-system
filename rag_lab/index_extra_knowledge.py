#!/usr/bin/env python3
"""Opt-in, standalone knowledge uploader for Gemini File Search.

Runs a dry-run by default. --upload is required to send data to Google.
Does not edit ERP code or access a database.
"""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KNOWLEDGE = ROOT / 'knowledge'
STORE_ID = ROOT / 'store_id.txt'
STATE = ROOT / 'extra_knowledge_upload_state.json'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upload', action='store_true', help='Upload files to Gemini File Search (may incur usage costs)')
    args = parser.parse_args()
    files = sorted(KNOWLEDGE.rglob('*.txt'))
    if not files:
        raise SystemExit('No knowledge/*.txt documents found.')

    records = {}
    if STATE.exists():
        records = json.loads(STATE.read_text(encoding='utf-8'))
    if not isinstance(records, dict):
        raise SystemExit('State file is not a JSON object; do not overwrite it blindly.')

    store = STORE_ID.read_text(encoding='utf-8').strip() if STORE_ID.exists() else ''
    if not store:
        raise SystemExit('Missing store_id.txt: verify indexing with your existing index_demo.py first.')

    client = None
    if args.upload:
        key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        if not key:
            raise SystemExit('GEMINI_API_KEY/GOOGLE_API_KEY missing. Do not print your API key.')
        from google import genai
        client = genai.Client(api_key=key)

    print('Knowledge store:', store)
    print('Mode:', 'UPLOAD' if args.upload else 'DRY RUN (nothing sent)')
    for file in files:
        name = file.relative_to(ROOT).as_posix()
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        signature = store + ':' + digest
        old = records.get(name)
        if old == signature:
            print('SKIP already uploaded:', name)
            continue
        if old is not None:
            print('CHANGED, NOT RE-UPLOADED:', name)
            print('  Publish a new versioned filename after reviewing old remote content to prevent duplicate/stale guidance.')
            continue
        if not args.upload:
            print('WOULD UPLOAD:', name)
            continue
        print('UPLOADING:', name)
        operation = client.file_search_stores.upload_to_file_search_store(
            file=str(file),
            file_search_store_name=store,
            config={'display_name': name},
        )
        while not operation.done:
            time.sleep(5)
            operation = client.operations.get(operation)
        if getattr(operation, 'error', None):
            raise RuntimeError('Upload failed for ' + name + ': ' + str(operation.error))
        records[name] = signature
        STATE.write_text(json.dumps(records, indent=2), encoding='utf-8')
        print('UPLOADED:', name)
    print('Finished. RAG indexing does not retrain Gemini or integrate the ERP.')


if __name__ == '__main__':
    main()
