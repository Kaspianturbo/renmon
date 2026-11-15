"""CSV presentation of the current monitoring session."""

import csv
import io


def export_csv(snapshot):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["mode", "timestamp", "code", "value", "error"])
    for sample in snapshot["samples"]:
        for code in sorted(set(sample["values"]) | set(sample["errors"])):
            writer.writerow(
                [
                    snapshot["mode"],
                    sample["at"],
                    code,
                    sample["values"].get(code, ""),
                    sample["errors"].get(code, ""),
                ]
            )
    return output.getvalue().encode("utf-8-sig")
