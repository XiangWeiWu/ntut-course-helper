"""重新產生 data/snapshot/（需先有 data/raw）：python -m scripts.build_snapshot 115 1"""
import sys

from backend.ingest.load import write_snapshot

if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]] or [115, 1]
    for y, s in zip(args[::2], args[1::2]):
        print(write_snapshot(y, s))
