"""Immutable acquisition of official Concealing Prices OSF Study 1/3 files."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
RAW_ROOT = REPOSITORY / "data/raw/concealing_prices/osf"
MANIFEST = ROOT / "manifests/OSF_ACQUISITION_MANIFEST.json"
NODE_URL = "https://api.osf.io/v2/nodes/xt42w/"
FOLDERS = {
    "Study 1": "67d7303eed9107a459a72fa9",
    "Study 3": "67d730f6e8677f0660a72b82",
}
USER_AGENT = "Exergi-V9-scientific-replication/1.0"


class AcquisitionError(RuntimeError):
    """Raised if official acquisition cannot be verified."""


def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.loads(response.read())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        data = response.read()
    destination.write_bytes(data)


def acquire() -> dict[str, Any]:
    node = _request_json(NODE_URL)["data"]
    if node["id"] != "xt42w" or not node["attributes"]["public"]:
        raise AcquisitionError("official OSF node is unavailable or not public")
    records: list[dict[str, Any]] = []
    acquired_at = datetime.now(UTC).isoformat()
    for study, folder_id in FOLDERS.items():
        url = (
            "https://api.osf.io/v2/nodes/xt42w/files/osfstorage/"
            f"{folder_id}/?page%5Bsize%5D=100"
        )
        listing = _request_json(url)
        if listing["links"]["meta"]["total"] != len(listing["data"]):
            raise AcquisitionError(f"paginated or incomplete OSF listing for {study}")
        destination_folder = RAW_ROOT / study
        destination_folder.mkdir(parents=True, exist_ok=True)
        for item in listing["data"]:
            attributes = item["attributes"]
            if attributes["kind"] != "file":
                raise AcquisitionError(f"unexpected nested OSF item in {study}")
            name = str(attributes["name"])
            destination = destination_folder / name
            expected_hash = str(attributes["extra"]["hashes"]["sha256"])
            if destination.exists():
                destination.chmod(0o644)
                if _sha256(destination) != expected_hash:
                    raise AcquisitionError(f"existing raw checksum mismatch: {study}/{name}")
            else:
                _download(str(item["links"]["download"]), destination)
            observed_hash = _sha256(destination)
            observed_size = destination.stat().st_size
            if observed_hash != expected_hash or observed_size != int(attributes["size"]):
                raise AcquisitionError(f"download verification failed: {study}/{name}")
            destination.chmod(0o444)
            mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            records.append(
                {
                    "study": study,
                    "original_filename": name,
                    "osf_file_id": item["id"],
                    "osf_guid": attributes["guid"],
                    "osf_current_version": attributes["current_version"],
                    "source_url": item["links"]["download"],
                    "osf_info_url": item["links"]["info"],
                    "date_created": attributes["date_created"],
                    "date_modified": attributes["date_modified"],
                    "byte_size": observed_size,
                    "sha256": observed_hash,
                    "mime_type": mime_type,
                    "license": "No explicit OSF node license stated",
                    "terms": (
                        "Publicly readable OSF research project; "
                        "no additional license inferred"
                    ),
                    "local_relative_path": str(destination.relative_to(REPOSITORY)),
                    "filesystem_mode": oct(os.stat(destination).st_mode & 0o777),
                    "downloaded_at_utc": acquired_at,
                }
            )
    if len(records) != 40:
        raise AcquisitionError(f"expected 40 Study 1/3 files, acquired {len(records)}")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "OFFICIAL_OSF_ACQUISITION_VERIFIED",
        "project_id": "xt42w",
        "project_url": "https://osf.io/xt42w/",
        "api_url": NODE_URL,
        "title": node["attributes"]["title"],
        "project_public": node["attributes"]["public"],
        "project_license": node["attributes"]["node_license"],
        "project_date_modified": node["attributes"]["date_modified"],
        "scope": "All official files in OSF Study 1 and Study 3 folders",
        "acquired_at_utc": acquired_at,
        "file_count": len(records),
        "total_bytes": sum(int(record["byte_size"]) for record in records),
        "files": sorted(records, key=lambda record: (record["study"], record["original_filename"])),
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    result = acquire()
    print(
        json.dumps(
            {
                "status": result["status"],
                "file_count": result["file_count"],
                "total_bytes": result["total_bytes"],
            },
            indent=2,
        )
    )
