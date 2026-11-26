# NakshaTech BD AI - Synthetic RAG Starter Pack (Version 1.0)

Purpose: educational, fictional reference data for testing a Gemini File Search RAG pipeline for BD requirement analysis. This is NOT a NakshaTech-authorized SOP or a verified quotation template. No client-specific information is included.

## Contains
- `knowledge/` - 16 text documents organized by service and shared policy topics. These are the ONLY documents the bundled uploader sends.
- `feedback/CANDIDATE_corrections_NOT_APPROVED.jsonl` - 12 fictional candidate corrections; statuses all pending. DO NOT index as approved knowledge.
- `evaluation/held_out_bd_cases.jsonl` - 20 fictional test cases with expected details; DO NOT index this evaluation set (it would leak answers into retrieval).
- `index_extra_knowledge.py` - opt-in uploader that uses your existing Gemini File Search store.
- `query_extra_knowledge.py` - simple retrieval/citation smoke test.

## Beginner installation (Windows PowerShell + VS Code)
1. Keep a backup of the existing `E:\nakshatech-erp-shreeyansh1\rag_lab` folder.
2. Open this ZIP. Copy `knowledge`, `feedback`, `evaluation`, `index_extra_knowledge.py`, and `query_extra_knowledge.py` into `E:\nakshatech-erp-shreeyansh1\rag_lab\`.
3. Merge the `knowledge` subfolders. Do not replace `index_demo.py`, `query_demo.py`, `store_id.txt`, or any existing personal files. The starter pack uses distinct filenames.
4. In a VS Code PowerShell terminal, run:

   cd "E:\nakshatech-erp-shreeyansh1"
   python -m py_compile ".\rag_lab\index_extra_knowledge.py"
   python ".\rag_lab\index_extra_knowledge.py"

   The default DRY RUN only lists files; it does not upload them.
5. Confirm your existing `rag_lab/store_id.txt` is for your intended fictional training store and that the file-search store exists. If missing, complete your earlier standalone `index_demo.py` setup first.
6. To send the synthetic documents to your store, explicitly run:

   python ".\rag_lab\index_extra_knowledge.py" --upload

   This contacts Google. The script skips unchanged files uploaded with this script. It does NOT delete old remote versions, and it does NOT automatically update changed filenames. Review any warning before reindexing.
7. Once uploads have completed, test retrieval:

   python ".\rag_lab\query_extra_knowledge.py"

   A good result mentions NBD-LIDAR-203 and has a file citation. If the model endpoint is not available, check your configured Gemini model. This script does not change your ERP settings.

## Important limitations
- These files are not 'training' in the weight-update sense. File Search provides document retrieval (RAG); Gemini weights remain unchanged.
- Existing BD AI `service.py` does NOT automatically read these new files. Connecting the retriever to your existing BD AI backend requires a separate, reviewed change with authentication, authorized retrieval, schema compatibility and tests.
- A knowledge document about permissions cannot enforce permissions. Never index restricted company data in a shared store. Access control must be performed by trusted backend code before retrieval or prompt construction.
- Do not upload confidential Finance/Management records or real client documents to free-tier services without company authorization and appropriate terms. Google API free-tier data may be used to improve its products. Check current pricing/quota before uploading; free allowances are limited and not guaranteed for all accounts.
- Evaluation and feedback files should stay LOCAL until you implement a proper authorized review workflow and explicitly decide how to use them.
- The uploader remembers completed files in `extra_knowledge_upload_state.json`. If you use another computer or lose this file, reconcile remote file inventory before re-uploading to avoid duplicates.
- The generated pack has NOT been sent to Gemini or connected to live ERP. You must do the local steps yourself.

## Suggested smoke questions
1. Which reference ID covers LiDAR classification and what key missing facts are needed for a 42 km corridor survey?
2. According to NBD-DRONE-201, is 5 cm GSD the same as 5 cm horizontal accuracy?
3. Why must a lake-network DEM flow path be field-checked?
4. If a customer asks for orthophoto only, may the AI list DTM as a confirmed deliverable?
5. What rate in INR per acre has this training pack approved for drone work? (Correct: none.)
6. Can a written RAG policy by itself prevent access to restricted Finance data? (Correct: no.)

## How to evaluate improvement
Start with the held-out cases. Record baseline responses from your existing ERP, then RAG-enhanced responses after authorized integration, and compare confirmed facts, units, missing items, unsupported assertions and citations. Keep unrelated ERP modules unchanged.
