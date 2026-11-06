
from __future__ import annotations

import argparse
import ast
import re
import shutil
from datetime import datetime
from pathlib import Path


PATCH_MARKER = "# NAKSHA_CLD_BLOCKS_PATCH_V1"

TARGET_RELATIVE = Path(
    "backend/app/modules/operations/production_allocation.py"
)

HELPER_CODE = r'''
# NAKSHA_CLD_BLOCKS_PATCH_V1
# Additive support for two-column CLD spreadsheets.
# Original six-column import and downstream allocation are unchanged.

def _parse_cld_block_rows(
    rows: list[list[Any]],
    filename: str,
) -> list[dict] | None:
    from decimal import Decimal, InvalidOperation

    def normalize(value: Any) -> str:
        if value is None:
            return ""
        return " ".join(
            str(value)
            .replace("\xa0", " ")
            .replace("\n", " ")
            .casefold()
            .split()
        )

    header_index = None
    block_column = None
    distance_column = None

    for index, row in enumerate(rows[:50]):
        names = [normalize(value) for value in row]

        if (
            "block name" in names
            and "cl distance (m)" in names
        ):
            block_column = names.index("block name")
            distance_column = names.index("cl distance (m)")
            header_index = index

            other_headers = [
                name
                for col, name in enumerate(names)
                if name
                and col not in {
                    block_column,
                    distance_column,
                }
            ]

            if other_headers:
                raise ValueError(
                    "CLD import has additional columns. "
                    "Review the workbook mapping before upload: "
                    + ", ".join(other_headers)
                )

            break

    if header_index is None:
        return None

    # These are explicit internal import-group labels.
    # They are NOT claims about the official lot/code.
    import_lot = "CLD_IMPORT"
    import_code = "CENTRELINE_M"

    entries: list[dict] = []
    seen_blocks: set[str] = set()

    source_name = filename.replace("\\", "/").split("/")[-1]

    for row_index, row in enumerate(
        rows[header_index + 1:],
        start=header_index + 2,
    ):
        if not any(
            value is not None and str(value).strip()
            for value in row
        ):
            continue

        block_value = (
            row[block_column]
            if block_column < len(row)
            else None
        )

        distance_value = (
            row[distance_column]
            if distance_column < len(row)
            else None
        )

        block = str(
            block_value if block_value is not None else ""
        ).strip()

        # Summary rows are NOT physical work items.
        if block.casefold() in {
            "total",
            "grand total",
            "sum",
        }:
            continue

        # Do not silently discard extra data.
        additional_values = [
            value
            for col, value in enumerate(row)
            if col not in {
                block_column,
                distance_column,
            }
            and value is not None
            and str(value).strip()
        ]

        if additional_values:
            raise ValueError(
                f"CLD row {row_index}: unexpected extra data"
            )

        if not block:
            raise ValueError(
                f"CLD row {row_index}: Block Name is blank"
            )

        if len(block) > 120:
            raise ValueError(
                f"CLD row {row_index}: Block Name is too long"
            )

        key = block.casefold()

        if key in seen_blocks:
            raise ValueError(
                f"CLD row {row_index}: duplicate Block Name "
                f"'{block}'"
            )

        if (
            distance_value is None
            or str(distance_value).strip() == ""
        ):
            raise ValueError(
                f"CLD row {row_index}: distance is missing "
                f"for block '{block}'"
            )

        try:
            distance = Decimal(
                str(distance_value).strip()
            )
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(
                f"CLD row {row_index}: invalid distance "
                f"'{distance_value}'"
            )

        if not distance.is_finite() or distance <= 0:
            raise ValueError(
                f"CLD row {row_index}: distance must "
                f"be a positive number"
            )

        seen_blocks.add(key)

        # ONE BLOCK = ONE ASSIGNABLE PHYSICAL WORK ITEM.
        # The original Block Name remains its identifier.
        # A unique Area avoids duplicating block lengths.
        entries.append({
            "row": row_index,
            "lot": import_lot,
            "code": import_code,
            "area_name": block,
            "item_number": block,
            "item_numbers": [block],
            "planned_quantity": distance,
            "area_planned_quantity": distance,
            "total_files": None,
            "unit": "m",
            "remarks": (
                f"CLD source: {source_name}; "
                f"Block Name: {block}"
            ),
            "item_name": block,
        })

        if len(entries) > 5000:
            raise ValueError(
                "CLD upload exceeds the 5000-block "
                "safety limit"
            )

    if not entries:
        raise ValueError(
            "CLD workbook has no valid block rows"
        )

    return entries
'''


"""def prepare_patch(source: str) -> str:
    if PATCH_MARKER in source:
        raise RuntimeError(
            "CLD patch is already installed. "
            "No file has been modified."
        )

    anchor = (
        "def parse_master_workbook("
        "filename: str, content: bytes) -> list[dict]:"
    )

    if source.count(anchor) != 1:
        raise RuntimeError(
            "Expected parse_master_workbook() signature "
            "was not found exactly once. No changes made."
        )

    pattern = re.compile(
        r"(?m)^    (?:"
        r"header_index, mapping, missing = "
        r"_find_import_header\(rows\)"
        r"|mapping, missing = "
        r"_map_headers\(rows\[0\]\)"
        r")[ \t]*$"
    )

    anchor_position = source.index(anchor)

    matches = [
        match
        for match in pattern.finditer(source)
        if match.start() > anchor_position
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "Cannot safely locate the existing header "
            "validation line. No changes made."
        )

    match = matches[0]

    branch = (
        "    cld_entries = "
        "_parse_cld_block_rows(rows, filename)\n"
        "    if cld_entries is not None:\n"
        "        return cld_entries\n\n"
    )

    source = (
        source[:match.start()]
        + branch
        + source[match.start():]
    )

    source = source.replace(
        anchor,
        HELPER_CODE.strip() + "\n\n\n" + anchor,
        1,
    )

    # Syntax verification before changing the actual file.
    ast.parse(source)

    return source"""

def prepare_patch(source: str) -> str:
    if PATCH_MARKER in source:
        raise RuntimeError(
            "CLD patch is already installed. "
            "No file has been modified."
        )

    # Find the actual Python function using AST.
    # This supports both single-line and multiline signatures.
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        raise RuntimeError(
            f"Existing production_allocation.py has a "
            f"Python syntax error: {exc}"
        ) from exc

    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "parse_master_workbook"
    ]

    if len(functions) != 1:
        raise RuntimeError(
            "Cannot uniquely locate parse_master_workbook(). "
            "No changes made."
        )

    function = functions[0]
    lines = source.splitlines(keepends=True)

    start = sum(
        len(line)
        for line in lines[:function.lineno - 1]
    )

    end = sum(
        len(line)
        for line in lines[:function.end_lineno]
    )

    function_source = source[start:end]

    # Find the existing header validation.
    # Both previously supported implementations are accepted.
    pattern = re.compile(
        r"(?m)^    (?:"
        r"header_index,\s*mapping,\s*missing\s*=\s*"
        r"_find_import_header\(rows\)"
        r"|"
        r"mapping,\s*missing\s*=\s*"
        r"_map_headers\(rows\[0\]\)"
        r")[ \t]*$"
    )

    matches = list(pattern.finditer(function_source))

    if len(matches) != 1:
        raise RuntimeError(
            "Cannot safely locate the existing header "
            "validation line inside parse_master_workbook(). "
            "No changes made."
        )

    match = matches[0]

    # Add CLD detection before the original header validation.
    # Normal six-column workbooks continue into the old parser.
    branch = (
        "    cld_entries = "
        "_parse_cld_block_rows(rows, filename)\n"
        "    if cld_entries is not None:\n"
        "        return cld_entries\n\n"
    )

    modified_function = (
        function_source[:match.start()]
        + branch
        + function_source[match.start():]
    )

    # Insert helper before the existing parser.
    # No other functions are replaced.
    patched = (
        source[:start]
        + HELPER_CODE.strip()
        + "\n\n\n"
        + modified_function
        + source[end:]
    )

    # Verify the resulting Python file before allowing apply.
    ast.parse(patched)

    return patched



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=".",
        help="ERP project root folder",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply after a successful dry run",
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()
    target = root / TARGET_RELATIVE

    if not target.is_file():
        raise SystemExit(
            f"Target file not found: {target}"
        )

    original = target.read_text(encoding="utf-8")
    patched = prepare_patch(original)

    if not args.apply:
        print("PASS: Expected importer anchors found")
        print("PASS: Modified Python syntax is valid")
        print("PASS: Existing source has NOT changed")
        print("Run again with --apply to install")
        return

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = target.with_name(
        target.name + f".before_cld_{stamp}.bak"
    )

    shutil.copy2(target, backup)

    try:
        target.write_text(
            patched,
            encoding="utf-8",
            newline="\n",
        )
    except Exception:
        shutil.copy2(backup, target)
        raise

    print("PASS: CLD parser patch installed")
    print("BACKUP:", backup)
    print("CHANGED:", target)
    print("No database records were modified")


if __name__ == "__main__":
    main()
