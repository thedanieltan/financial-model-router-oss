from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static FMR GitHub Pages artifact.")
    parser.add_argument("--wheel", required=True)
    parser.add_argument("--output", default="_site")
    parser.add_argument("--revision", default="unknown")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    source = root / "pages"
    wheel = Path(args.wheel).resolve()
    output = Path(args.output).resolve()
    if not source.is_dir():
        raise SystemExit("pages source directory is missing")
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise SystemExit("a built wheel is required")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output)
    shutil.copy2(wheel, output / "financial_model_router.whl")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    (output / "version.json").write_text(
        json.dumps(
            {
                "contract_version": "fmr-pages-build.v1",
                "revision": args.revision,
                "wheel": wheel.name,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    required = (
        "index.html",
        "styles.css",
        "app.js",
        "worker.js",
        "demo_runtime.py",
        "financial_model_router.whl",
        "version.json",
    )
    missing = [name for name in required if not (output / name).is_file()]
    if missing:
        raise SystemExit("pages build is incomplete: " + ",".join(missing))


if __name__ == "__main__":
    main()
