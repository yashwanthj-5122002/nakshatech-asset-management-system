"""Render three review PDFs without writing any invoice/database state.

Run from backend: python scripts/render_invoice_theme_samples.py
Pass --invoice-id ID to use a read-only snapshot of an existing ERP invoice.
The default is clearly identified demonstration data, unrelated to the PNG examples.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.operations.invoice_documents import amount_in_words, build_invoice_a4_pdf


def sample_payload():
    return {
        "document_type": "TAX INVOICE", "document_source": "project_invoice",
        "company": {
            "name": "NAKSHA TECH PRIVATE LIMITED",
            "address": "Survey Technology Park, Bengaluru, Karnataka, India 560001",
            "phone": "+91 80 4000 1000", "gstin": "29ABCDE1234F1Z5",
            "pan": "ABCDE1234F", "hsn_sac": "998314",
        },
        "client": {
            "name": "Geospatial Review Client Private Limited",
            "address": "Plot 7, Technology Avenue,\nPune, Maharashtra 411019",
            "country": "India", "gstin": "27AAAAA0000A1Z5",
        },
        "invoice": {
            "invoice_number": "DESIGN-REVIEW-2026-001", "invoice_date": "2026-10-17",
            "due_date": "2026-11-16", "po_wo_reference": "WO-REVIEW-026",
            "work_order_date": "2026-10-10", "dispatch_date": "2026-10-17",
            "dispatch_details": "Digital delivery", "created_at": "2026-10-17T15:45:00+05:30",
        },
        "line_items": [
            {"sequence": 1, "description": "Topographical Survey", "detail": "Field survey and geospatial processing",
             "quantity": Decimal("1"), "unit": "Service", "rate": Decimal("20465"), "taxable_amount": Decimal("20465")},
            {"sequence": 2, "description": "Mapping & CAD Deliverables", "detail": "Quality review and final digital deliverables",
             "quantity": Decimal("1"), "unit": "Service", "rate": Decimal("12500"), "taxable_amount": Decimal("12500")},
        ],
        "tax_lines": [{"label": "CGST @ 9%", "amount": Decimal("2966.85")}, {"label": "SGST @ 9%", "amount": Decimal("2966.85")}],
        "totals": {"currency": "INR", "taxable_amount": Decimal("32965"), "invoice_total": Decimal("38898.70"),
                   "amount_in_words": amount_in_words(Decimal("38898.70"))},
        "terms_conditions": "1. Payment as agreed in the work order.\n2. Please quote the invoice number with your remittance.\n3. Services are subject to the agreed scope and applicable GST.",
        "qr_data": "INVOICE DESIGN REVIEW | DESIGN-REVIEW-2026-001 | INR 38898.70",
        "signature": {"signed": False},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invoice-id", type=int)
    parser.add_argument("--output", type=Path, default=Path("artifacts/invoice-theme-review"))
    args = parser.parse_args()
    payload = sample_payload()
    if args.invoice_id:
        from app.core.database import SessionLocal
        from app.modules.operations.invoice_documents import invoice_document_payload
        with SessionLocal() as db:
            payload = invoice_document_payload(db, args.invoice_id)
    args.output.mkdir(parents=True, exist_ok=True)
    # The saved payload makes the sample's provenance and exact data reviewable.
    (args.output / "sample-payload.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    names = {"blue_topographic": "01-modern-teal", "blue_classic": "02-clean-corporate-blue", "green_gold_premium": "03-premium-green-gold"}
    for key, name in names.items():
        document = deepcopy(payload)
        document.update(theme=key, theme_explicit=True)
        path = args.output / f"{name}.pdf"
        path.write_bytes(build_invoice_a4_pdf(document).getvalue())
        print(path)
        # Optional development-only preview dependency, never required by production.
        try:
            import pymupdf
        except ImportError:
            continue
        for previous in args.output.glob(f"{name}-page-*.png"):
            previous.unlink()
        with pymupdf.open(path) as pdf:
            for index, page in enumerate(pdf):
                page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(args.output / f"{name}-page-{index+1}.png")
            print(f"  {len(pdf)} A4 page(s)")


if __name__ == "__main__":
    main()
