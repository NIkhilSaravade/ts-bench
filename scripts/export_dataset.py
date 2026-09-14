"""T5: publish the current validated dataset as an immutable version.

Usage: uv run python scripts/export_dataset.py v0.1 "13 instances: zod, date-fns, trpc"
"""

import sys

from pipeline.dataset_export import export_version


def main() -> None:
    if len(sys.argv) != 3:
        print('usage: export_dataset.py <version> "<description>"', file=sys.stderr)
        sys.exit(1)

    version, description = sys.argv[1], sys.argv[2]
    out_dir = export_version(version, description)
    print(f"exported -> {out_dir}")


if __name__ == "__main__":
    main()
