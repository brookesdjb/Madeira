#!/usr/bin/env python3
"""Record source pins and optional binary hashes without changing the checkout."""
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def inventory(root, prefix=""):
    result = []
    for item in git(root, "ls-tree", "-r", "HEAD").splitlines():
        metadata, path = item.split("\t", 1)
        mode, kind, sha = metadata.split()
        if mode != "160000":
            continue
        child = root / path
        present = (child / ".git").exists()
        entry = {"path": prefix + path, "gitlink": sha, "available": present}
        if present:
            entry["checkout"] = git(child, "rev-parse", "HEAD")
            entry["matches_pin"] = entry["checkout"] == sha
        result.append(entry)
        if present:
            result.extend(inventory(child, prefix + path + "/"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--binary", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        hashes = {}
        for path in args.binary:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[str(path)] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
        print(json.dumps({"head": git(args.repo, "rev-parse", "HEAD"),
                          "platform": platform.platform(),
                          "git_status": git(args.repo, "status", "--short"),
                          "submodules": inventory(args.repo), "binaries": hashes}, indent=2))
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
