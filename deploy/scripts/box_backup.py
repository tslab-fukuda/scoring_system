#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import sys
from pathlib import Path

import requests


BOX_API_BASE = "https://api.box.com/2.0"
BOX_UPLOAD_BASE = "https://upload.box.com/api/2.0"
BOX_TOKEN_URL = "https://api.box.com/oauth2/token"


class BoxError(RuntimeError):
    pass


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] in ("'", '"') and value[-1] == value[0]:
            value = value[1:-1]
        else:
            try:
                value = shlex.split(value)[0] if value else ""
            except ValueError:
                value = value.strip("'\"")
        data[key] = value
    return data


def write_env_file(path: Path, env_data: dict[str, str]) -> None:
    lines = [f"{key}={shlex.quote(str(value))}" for key, value in sorted(env_data.items())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_config(env_file: str | None) -> tuple[dict[str, str], Path | None]:
    env_path = Path(env_file).resolve() if env_file else None
    file_values = parse_env_file(env_path) if env_path else {}
    config = dict(file_values)
    config.update({key: value for key, value in os.environ.items() if key.startswith("BOX_") or key.startswith("BACKUP_") or key.startswith("RESTORE_")})
    if not config.get("BOX_HOST_FOLDER_NAME"):
        config["BOX_HOST_FOLDER_NAME"] = socket.gethostname()
    config.setdefault("BOX_ROOT_FOLDER_ID", "0")
    config.setdefault("BOX_PROJECT_FOLDER_NAME", "scoring-system")
    config.setdefault("BOX_ENVIRONMENT_NAME", "prod")
    return config, env_path


def refresh_access_token(config: dict[str, str], env_path: Path | None) -> str:
    required = ["BOX_CLIENT_ID", "BOX_CLIENT_SECRET", "BOX_REFRESH_TOKEN"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise BoxError(f"missing Box config: {', '.join(missing)}")

    response = requests.post(
        BOX_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": config["BOX_REFRESH_TOKEN"],
            "client_id": config["BOX_CLIENT_ID"],
            "client_secret": config["BOX_CLIENT_SECRET"],
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise BoxError(f"failed to refresh Box token: {response.status_code} {response.text}")

    payload = response.json()
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not access_token:
        raise BoxError("Box token response did not contain access_token")

    if refresh_token and refresh_token != config.get("BOX_REFRESH_TOKEN"):
        config["BOX_REFRESH_TOKEN"] = refresh_token
        if env_path:
            merged = parse_env_file(env_path)
            merged.update(config)
            write_env_file(env_path, merged)
    return access_token


def api_request(access_token: str, method: str, url: str, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access_token}"
    response = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    if response.status_code >= 400:
        raise BoxError(f"Box API error: {response.status_code} {response.text}")
    return response


def iter_folder_items(access_token: str, folder_id: str) -> list[dict]:
    offset = 0
    limit = 1000
    items: list[dict] = []
    while True:
        response = api_request(
            access_token,
            "GET",
            f"{BOX_API_BASE}/folders/{folder_id}/items",
            params={"fields": "id,name,type,modified_at,size", "limit": limit, "offset": offset},
        ).json()
        chunk = response.get("entries", [])
        items.extend(chunk)
        if len(chunk) < limit:
            break
        offset += limit
    return items


def ensure_folder(access_token: str, parent_id: str, name: str) -> str:
    for item in iter_folder_items(access_token, parent_id):
        if item.get("type") == "folder" and item.get("name") == name:
            return str(item["id"])
    response = requests.post(
        f"{BOX_API_BASE}/folders",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name, "parent": {"id": str(parent_id)}},
        timeout=60,
    )
    if response.status_code == 409:
        conflict = response.json().get("context_info", {}).get("conflicts", {})
        if conflict and conflict.get("id"):
            return str(conflict["id"])
    if response.status_code >= 400:
        raise BoxError(f"failed to create Box folder '{name}': {response.status_code} {response.text}")
    return str(response.json()["id"])


def resolve_backup_folder(access_token: str, config: dict[str, str]) -> str:
    folder_id = str(config["BOX_ROOT_FOLDER_ID"])
    segments = [
        config.get("BOX_PROJECT_FOLDER_NAME") or "scoring-system",
        config.get("BOX_ENVIRONMENT_NAME") or "prod",
        config.get("BOX_HOST_FOLDER_NAME") or socket.gethostname(),
    ]
    for segment in segments:
        folder_id = ensure_folder(access_token, folder_id, segment)
    return folder_id


def upload_file(access_token: str, folder_id: str, path: Path) -> dict:
    attributes = {"name": path.name, "parent": {"id": str(folder_id)}}
    with path.open("rb") as fh:
        response = requests.post(
            f"{BOX_UPLOAD_BASE}/files/content",
            headers={"Authorization": f"Bearer {access_token}"},
            files=[
                ("attributes", (None, json.dumps(attributes), "application/json")),
                ("file", (path.name, fh, "application/octet-stream")),
            ],
            timeout=300,
        )
    if response.status_code >= 400:
        raise BoxError(f"failed to upload {path.name}: {response.status_code} {response.text}")
    entries = response.json().get("entries", [])
    if not entries:
        raise BoxError(f"Box did not return uploaded file entry for {path.name}")
    return entries[0]


def list_manifests(access_token: str, config: dict[str, str]) -> list[dict]:
    folder_id = resolve_backup_folder(access_token, config)
    manifests = []
    for item in iter_folder_items(access_token, folder_id):
        if item.get("type") == "file" and str(item.get("name", "")).endswith(".manifest.json"):
            manifests.append(item)
    manifests.sort(key=lambda x: x.get("name", ""), reverse=True)
    return manifests


def download_file(access_token: str, file_id: str, destination: Path) -> None:
    response = requests.get(
        f"{BOX_API_BASE}/files/{file_id}/content",
        headers={"Authorization": f"Bearer {access_token}"},
        allow_redirects=True,
        timeout=300,
        stream=True,
    )
    if response.status_code >= 400:
        raise BoxError(f"failed to download file {file_id}: {response.status_code} {response.text}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fh.write(chunk)


def command_upload(args: argparse.Namespace) -> int:
    config, env_path = load_config(args.env_file)
    access_token = refresh_access_token(config, env_path)
    folder_id = resolve_backup_folder(access_token, config)

    upload_targets = [Path(x).resolve() for x in args.files]
    manifest_path = Path(args.manifest).resolve()
    for target in [*upload_targets, manifest_path]:
        if not target.exists():
            raise BoxError(f"upload target not found: {target}")

    uploaded = []
    for target in upload_targets:
        uploaded.append(upload_file(access_token, folder_id, target))
    manifest_entry = upload_file(access_token, folder_id, manifest_path)
    print(json.dumps({
        "status": "ok",
        "folder_id": folder_id,
        "uploaded_files": [entry.get("name") for entry in uploaded],
        "manifest": manifest_entry.get("name"),
    }, ensure_ascii=False))
    return 0


def command_list(args: argparse.Namespace) -> int:
    config, env_path = load_config(args.env_file)
    access_token = refresh_access_token(config, env_path)
    manifests = list_manifests(access_token, config)
    print(json.dumps({"status": "ok", "manifests": manifests[: args.limit]}, ensure_ascii=False))
    return 0


def command_download(args: argparse.Namespace) -> int:
    config, env_path = load_config(args.env_file)
    access_token = refresh_access_token(config, env_path)
    manifests = list_manifests(access_token, config)
    if not manifests:
        raise BoxError("no manifest files found in Box backup folder")

    selected = None
    if args.manifest_name:
        for item in manifests:
            if item.get("name") == args.manifest_name:
                selected = item
                break
        if selected is None:
            raise BoxError(f"manifest not found: {args.manifest_name}")
    else:
        selected = manifests[0]

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / selected["name"]
    download_file(access_token, str(selected["id"]), manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    folder_id = resolve_backup_folder(access_token, config)
    items_by_name = {
        item.get("name"): item
        for item in iter_folder_items(access_token, folder_id)
        if item.get("type") == "file"
    }

    downloaded_parts = []
    for part in manifest.get("parts", []):
        name = part.get("name")
        item = items_by_name.get(name)
        if not item:
            raise BoxError(f"backup part not found in Box: {name}")
        target = output_dir / name
        download_file(access_token, str(item["id"]), target)
        downloaded_parts.append(str(target))

    print(json.dumps({
        "status": "ok",
        "manifest": str(manifest_path),
        "parts": downloaded_parts,
    }, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upload and download SQLite/media backups to Box.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload", help="Upload backup files and manifest to Box")
    upload.add_argument("--env-file", help="Path to Box env file", default=None)
    upload.add_argument("--manifest", required=True, help="Manifest JSON path")
    upload.add_argument("files", nargs="+", help="Backup part files")
    upload.set_defaults(func=command_upload)

    list_cmd = subparsers.add_parser("list", help="List uploaded backup manifests")
    list_cmd.add_argument("--env-file", help="Path to Box env file", default=None)
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.set_defaults(func=command_list)

    download = subparsers.add_parser("download", help="Download a backup manifest and all parts")
    download.add_argument("--env-file", help="Path to Box env file", default=None)
    download.add_argument("--manifest-name", help="Manifest file name. Omit to download the latest backup.", default=None)
    download.add_argument("--output-dir", required=True, help="Download destination directory")
    download.set_defaults(func=command_download)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except BoxError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
