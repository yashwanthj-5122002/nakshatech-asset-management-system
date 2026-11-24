import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

examples = json.loads(
    (BASE / "examples.json").read_text(encoding="utf-8")
)

with (BASE / "training.jsonl").open(
    "w", encoding="utf-8"
) as file:

    for example in examples:
        record = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": example["input"]}
                    ]
                },
                {
                    "role": "model",
                    "parts": [
                        {
                            "text": json.dumps(
                                example["output"],
                                ensure_ascii=False
                            )
                        }
                    ]
                }
            ]
        }

        file.write(
            json.dumps(record, ensure_ascii=False)
            + "\n"
        )

print(f"Prepared {len(examples)} examples.")