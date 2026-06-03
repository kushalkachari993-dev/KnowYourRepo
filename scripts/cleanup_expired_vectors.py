import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.ingest import get_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete expired temporary vector rows.")
    parser.add_argument(
        "--now",
        type=int,
        default=None,
        help="Unix timestamp cutoff. Defaults to the current time.",
    )
    args = parser.parse_args()

    cutoff = args.now or int(time.time())
    pipeline = get_pipeline()
    before = pipeline.get_status()["total_chunks"]
    pipeline.cleanup_expired(now=cutoff)
    after = pipeline.get_status()["total_chunks"]

    print(f"Cleanup cutoff: {cutoff}")
    print(f"Rows before: {before}")
    print(f"Rows after: {after}")
    print(f"Deleted: {max(before - after, 0)}")


if __name__ == "__main__":
    main()
