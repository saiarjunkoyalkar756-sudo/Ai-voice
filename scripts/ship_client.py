#!/usr/bin/env python3
"""
CLI: build a client codebase ZIP after Platform approve.

  python3 scripts/ship_client.py sp-67223
  python3 scripts/ship_client.py sp-67223 --out /tmp/

Requires: compiled + approved + validation OK + no critic blockers.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Ship Voicely client codebase ZIP")
    parser.add_argument("client_id", help="Platform client id (e.g. sp-67223)")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: clients/<id>/shipments/)",
    )
    parser.add_argument("--by", default="cli", help="shipped_by label")
    args = parser.parse_args()

    from ship.packager import ShipError, build_client_codebase_zip

    try:
        payload, filename, meta = build_client_codebase_zip(
            ROOT, args.client_id, shipped_by=args.by
        )
    except ShipError as exc:
        print(f"Ship refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Ship failed: {exc}", file=sys.stderr)
        return 1

    out_dir = args.out or (ROOT / "clients" / args.client_id / "shipments")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(payload)
    (out_dir / "LATEST.txt").write_text(filename, encoding="utf-8")
    (out_dir / f"{filename}.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(json.dumps({"ok": True, "path": str(path), **meta}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
