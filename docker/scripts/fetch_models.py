"""Fetch kreuzberg model repos from HuggingFace into the HF cache at build time.

Populates $HF_HOME/hub so the cache can be COPY'd into the final image and read
by kreuzberg at runtime without network access or blob-lock contention.

Only the paddleocr-onnx-models artifacts actually referenced by kreuzberg
v4.9.2 (mobile tier) are pulled. layout-models is omitted entirely because
layout detection is disabled (layout=None) in this project. v6/, the server
tier, the doc-orientation/table classifiers, and legacy SHARED_MODELS are also
skipped to keep the image small. If kreuzberg is upgraded (e.g. to a v6 model
version) or model_tier/auto_rotate defaults change, revisit MODEL_SOURCES.
"""

import os
import sys

from huggingface_hub import snapshot_download

# allow_patterns is intentionally explicit per family so pattern matching is
# unambiguous across huggingface_hub versions. Add a family here if a new
# script family is introduced upstream.
MODEL_SOURCES = {
    "Kreuzberg/paddleocr-onnx-models": [
        "manifest.json",
        "v2/det/mobile.onnx",
        "v2/classifiers/PP-LCNet_x1_0_textline_ori.onnx",
        "v2/rec/unified_mobile/*",
        "rec/arabic/*",
        "rec/chinese/*",
        "rec/devanagari/*",
        "rec/english/*",
        "rec/eslav/*",
        "rec/greek/*",
        "rec/korean/*",
        "rec/latin/*",
        "rec/tamil/*",
        "rec/telugu/*",
        "rec/thai/*",
    ],
}


def main() -> int:
    hf_home = os.environ.get("HF_HOME")
    if not hf_home:
        print("HF_HOME not set", file=sys.stderr)
        return 1
    for repo_id, patterns in MODEL_SOURCES.items():
        print(f"[fetch] {repo_id} -> {hf_home} ({len(patterns)} patterns)", flush=True)
        snapshot_download(repo_id=repo_id, allow_patterns=patterns)
    print("[fetch] done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())