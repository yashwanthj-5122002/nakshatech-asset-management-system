"""Explicit additive Payables-only PostgreSQL migration / verification.

    python -m app.modules.payables.migrate --check
    python -m app.modules.payables.migrate --apply

Only creates five new tables; does not ALTER or DROP existing ERP tables.
Run on a backed-up staging database before production.
"""
from __future__ import annotations
import argparse
from sqlalchemy import inspect
from app.core.database import Base, engine
from app.models.entities import User  # register 'users' FK target
from .models import Payable, PayableApproval, PayablePayment, PayableDocument, PayableAudit

TABLES = [cls.__table__ for cls in (Payable, PayableApproval, PayablePayment, PayableDocument, PayableAudit)]


def run(apply: bool):
    tables = set(inspect(engine).get_table_names())
    missing = [table.name for table in TABLES if table.name not in tables]
    print('Payables tables present:', [t.name for t in TABLES if t.name in tables])
    print('Payables tables missing:', missing)
    if apply:
        Base.metadata.create_all(bind=engine, tables=TABLES, checkfirst=True)
        print('Additive Payables migration completed: no existing tables altered')
    elif missing:
        print('Dry-run only. --apply will create these Payables-only tables')
    else:
        print('Payables tables already exist')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    run(args.apply)
