"""Fetch kreuzberg model repos from HuggingFace into the HF cache at build time.

Populates $HF_HOME/hub so the cache can be COPY'd into the final image and read
by kreuzberg at runtime without network access or blob-lock contention.
"""

import os
import sys

from huggingface_hub import snapshot_download

REPOS = [
    "Kreuzberg/paddleocr-onnx-models",
    "Kreuzberg/layout-models",
]


def main() -> int:
    hf_home = os.environ.get("HF_HOME")
    if not hf_home:
        print("HF_HOME not set", file=sys.stderr)
        return 1
    for repo_id in REPOS:
        print(f"[fetch] {repo_id} -> {hf_home}", flush=True)
        snapshot_download(repo_id=repo_id)
    print("[fetch] done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
