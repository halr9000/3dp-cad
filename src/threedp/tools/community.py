"""Community tools: model search and multi-platform publishing."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
import urllib.request
import urllib.parse

from threedp.config import ServerConfig
from threedp.helpers import ensure_exported
from threedp.logging_config import get_logger, log_tool_call, new_request_id
from threedp.model_store import ModelStore

log = get_logger()


def register_tools(mcp: Any, store: ModelStore, config: ServerConfig) -> None:
    """Register community/publishing tools with the MCP server."""

    @mcp.tool()
    def search_models(query: str, source: str = "thingiverse", max_results: int = 10) -> str:
        """Search for 3D models on Thingiverse.

        Requires THINGIVERSE_API_KEY environment variable.

        Args:
            query: Search query string
            source: Model source - "thingiverse" (default)
            max_results: Maximum number of results (default 10)
        """
        rid = new_request_id()
        with log_tool_call(log, "search_models", {"query": query, "source": source}, rid):
            if source.lower() != "thingiverse":
                return json.dumps({"success": False, "error": f"Unsupported source: {source}. Currently only 'thingiverse' is supported."})

            if not config.thingiverse_api_key:
                return json.dumps({
                    "success": False,
                    "error": "THINGIVERSE_API_KEY environment variable not set. "
                             "Register at https://www.thingiverse.com/developers to get an API key.",
                })

            try:
                encoded_query = urllib.parse.quote(query)
                url = f"https://api.thingiverse.com/search/{encoded_query}?type=things&per_page={max_results}"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {config.thingiverse_api_key}"})

                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())

                results = []
                hits = data if isinstance(data, list) else data.get("hits", data.get("things", []))
                for item in hits[:max_results]:
                    results.append({
                        "title": item.get("name", ""),
                        "author": item.get("creator", {}).get("name", "") if isinstance(item.get("creator"), dict) else "",
                        "url": item.get("public_url", ""),
                        "thumbnail": item.get("thumbnail", ""),
                        "like_count": item.get("like_count", 0),
                        "download_count": item.get("download_count", 0),
                    })

                log.info("models_searched", extra={
                    "request_id": rid, "query": query, "result_count": len(results),
                })

                return json.dumps({
                    "success": True, "query": query, "source": source,
                    "result_count": len(results), "results": results,
                }, indent=2)

            except Exception as e:
                log.error("search_models_failed", extra={"request_id": rid, "error": str(e)})
                return json.dumps({"success": False, "error": str(e), "traceback": __import__("traceback").format_exc()}, indent=2)

    @mcp.tool()
    def publish_github_release(
        name: str, repo: str, tag: str, description: str = "",
        formats: str = '["stl", "step"]', draft: bool = False,
    ) -> str:
        """Publish a model to GitHub Releases.

        Uploads STL/STEP files as release assets. Requires the `gh` CLI to be
        installed and authenticated, OR a GITHUB_TOKEN environment variable.

        Args:
            name: Model name (must exist in current session)
            repo: GitHub repo in "owner/repo" format (e.g. "brs077/my-models")
            tag: Release tag (e.g. "v1.0.0" or "box-v1")
            description: Release description/notes
            formats: JSON list of formats to upload (default: ["stl", "step"])
            draft: If True, create as draft release
        """
        rid = new_request_id()
        with log_tool_call(log, "publish_github_release", {"name": name, "repo": repo, "tag": tag}, rid):
            try:
                import subprocess
                import shutil

                fmt_list = json.loads(formats) if isinstance(formats, str) else formats
                files = [str(ensure_exported(store, config.output_dir, name, fmt)) for fmt in fmt_list]

                gh_path = shutil.which("gh")
                if gh_path:
                    cmd = [gh_path, "release", "create", tag, "--repo", repo,
                           "--title", f"{name} {tag}",
                           "--notes", description or f"3D model: {name}"]
                    if draft:
                        cmd.append("--draft")
                    cmd.extend(files)

                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if result.returncode != 0:
                        return json.dumps({"success": False, "error": f"gh release create failed: {result.stderr.strip()}"}, indent=2)

                    log.info("github_release_published", extra={
                        "request_id": rid, "name": name, "repo": repo, "tag": tag, "method": "gh_cli",
                    })

                    return json.dumps({
                        "success": True, "method": "gh_cli",
                        "release_url": result.stdout.strip(),
                        "tag": tag, "repo": repo,
                        "files_uploaded": [os.path.basename(f) for f in files],
                    }, indent=2)

                # Fallback: GitHub REST API
                if not config.github_token:
                    return json.dumps({
                        "success": False,
                        "error": "Neither `gh` CLI nor GITHUB_TOKEN environment variable found. "
                                 "Install gh (https://cli.github.com) or set GITHUB_TOKEN.",
                    }, indent=2)

                release_data = json.dumps({
                    "tag_name": tag, "name": f"{name} {tag}",
                    "body": description or f"3D model: {name}", "draft": draft,
                }).encode()

                req = urllib.request.Request(
                    f"https://api.github.com/repos/{repo}/releases",
                    data=release_data,
                    headers={
                        "Authorization": f"Bearer {config.github_token}",
                        "Accept": "application/vnd.github+json",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    release = json.loads(resp.read().decode())

                upload_url_template = release["upload_url"].replace("{?name,label}", "")
                uploaded = []
                for filepath in files:
                    filename = os.path.basename(filepath)
                    content_type = "application/sla" if filename.endswith(".stl") else "application/octet-stream"
                    with open(filepath, "rb") as f:
                        file_data = f.read()

                    upload_url = f"{upload_url_template}?name={urllib.parse.quote(filename)}"
                    req = urllib.request.Request(upload_url, data=file_data, headers={
                        "Authorization": f"Bearer {config.github_token}",
                        "Accept": "application/vnd.github+json",
                        "Content-Type": content_type,
                    }, method="POST")
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        asset = json.loads(resp.read().decode())
                        uploaded.append(asset.get("name", filename))

                log.info("github_release_published", extra={
                    "request_id": rid, "name": name, "repo": repo, "tag": tag, "method": "github_api",
                })

                return json.dumps({
                    "success": True, "method": "github_api",
                    "release_url": release.get("html_url", ""),
                    "tag": tag, "repo": repo, "files_uploaded": uploaded,
                }, indent=2)

            except Exception as e:
                log.error("publish_github_release_failed", extra={"request_id": rid, "error": str(e)})
                return json.dumps({"success": False, "error": str(e), "traceback": __import__("traceback").format_exc()}, indent=2)

    @mcp.tool()
    def publish_thingiverse(
        name: str, title: str, description: str = "",
        tags: str = '["3dprinting"]', category: str = "3D Printing", is_wip: bool = True,
    ) -> str:
        """Publish a model to Thingiverse.

        Creates a new Thing and uploads the STL file. Requires THINGIVERSE_TOKEN
        environment variable (OAuth access token).

        Args:
            name: Model name (must exist in current session)
            title: Thing title on Thingiverse
            description: Thing description (supports markdown)
            tags: JSON list of tags (e.g. '["box", "organizer"]')
            category: Thingiverse category name
            is_wip: If True, publish as work-in-progress (default: True for safety)
        """
        rid = new_request_id()
        with log_tool_call(log, "publish_thingiverse", {"name": name, "title": title}, rid):
            try:
                if not config.thingiverse_token:
                    return json.dumps({
                        "success": False,
                        "error": "THINGIVERSE_TOKEN environment variable not set. "
                                 "Create an app at https://www.thingiverse.com/developers and complete OAuth to get an access token.",
                    })

                stl_path = ensure_exported(store, config.output_dir, name, "stl")
                tag_list = json.loads(tags) if isinstance(tags, str) else tags

                thing_data = json.dumps({
                    "name": title,
                    "description": description or f"3D-printable model: {title}",
                    "tags": tag_list, "category": category, "is_wip": is_wip,
                }).encode()

                req = urllib.request.Request(
                    "https://api.thingiverse.com/things",
                    data=thing_data,
                    headers={"Authorization": f"Bearer {config.thingiverse_token}", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    thing = json.loads(resp.read().decode())

                thing_id = thing.get("id")
                if not thing_id:
                    return json.dumps({"success": False, "error": "Failed to create Thing — no ID returned", "response": thing}, indent=2)

                filename = stl_path.name
                file_req_data = json.dumps({"filename": filename}).encode()

                req = urllib.request.Request(
                    f"https://api.thingiverse.com/things/{thing_id}/files",
                    data=file_req_data,
                    headers={"Authorization": f"Bearer {config.thingiverse_token}", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    upload_info = json.loads(resp.read().decode())

                s3_action = upload_info.get("action", "")
                s3_fields = upload_info.get("fields", {})

                if s3_action and s3_fields:
                    import io
                    boundary = "----3dpMcpBoundary"
                    body = io.BytesIO()
                    for key, value in s3_fields.items():
                        body.write(f"--{boundary}\r\n".encode())
                        body.write(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
                        body.write(f"{value}\r\n".encode())
                    with open(stl_path, "rb") as f:
                        file_data = f.read()
                    body.write(f"--{boundary}\r\n".encode())
                    body.write(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
                    body.write(b"Content-Type: application/sla\r\n\r\n")
                    body.write(file_data)
                    body.write(b"\r\n")
                    body.write(f"--{boundary}--\r\n".encode())

                    req = urllib.request.Request(s3_action, data=body.getvalue(),
                                                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        pass

                    finalize_url = upload_info.get("finalize_url", f"https://api.thingiverse.com/things/{thing_id}/files/{upload_info.get('id', '')}/finalize")
                    req = urllib.request.Request(finalize_url, headers={"Authorization": f"Bearer {config.thingiverse_token}"}, method="POST")
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        pass

                thing_url = thing.get("public_url", f"https://www.thingiverse.com/thing:{thing_id}")

                log.info("thingiverse_published", extra={
                    "request_id": rid, "name": name, "thing_id": thing_id, "title": title,
                })

                return json.dumps({
                    "success": True, "thing_id": thing_id, "thing_url": thing_url,
                    "title": title, "file_uploaded": filename, "is_wip": is_wip,
                    "note": "Published as WIP. Edit on Thingiverse to add images and finalize." if is_wip else "",
                }, indent=2)

            except Exception as e:
                log.error("publish_thingiverse_failed", extra={"request_id": rid, "error": str(e)})
                return json.dumps({"success": False, "error": str(e), "traceback": __import__("traceback").format_exc()}, indent=2)

    @mcp.tool()
    def publish_myminifactory(
        name: str, title: str, description: str = "",
        tags: str = '["3dprinting"]', category_id: int = 0,
    ) -> str:
        """Publish a model to MyMiniFactory.

        Creates a new object and uploads the STL file. Requires
        MYMINIFACTORY_TOKEN environment variable (OAuth access token).

        Args:
            name: Model name (must exist in current session)
            title: Object title on MyMiniFactory
            description: Object description
            tags: JSON list of tags
            category_id: MyMiniFactory category ID (0 = uncategorized)
        """
        rid = new_request_id()
        with log_tool_call(log, "publish_myminifactory", {"name": name, "title": title}, rid):
            try:
                if not config.myminifactory_token:
                    return json.dumps({
                        "success": False,
                        "error": "MYMINIFACTORY_TOKEN environment variable not set. "
                                 "Register at https://www.myminifactory.com/api-documentation for API access.",
                    })

                stl_path = ensure_exported(store, config.output_dir, name, "stl")
                tag_list = json.loads(tags) if isinstance(tags, str) else tags

                object_data = json.dumps({
                    "name": title, "description": description or f"3D-printable model: {title}",
                    "tags": tag_list, "visibility": "draft",
                }).encode()

                req = urllib.request.Request(
                    "https://www.myminifactory.com/api/v2/objects",
                    data=object_data,
                    headers={"Authorization": f"Bearer {config.myminifactory_token}", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    obj = json.loads(resp.read().decode())

                object_id = obj.get("id")
                if not object_id:
                    return json.dumps({"success": False, "error": "Failed to create object", "response": obj}, indent=2)

                filename = stl_path.name
                with open(stl_path, "rb") as f:
                    file_data = f.read()

                boundary = "----3dpMcpBoundary"
                body = b""
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
                body += b"Content-Type: application/sla\r\n\r\n"
                body += file_data
                body += b"\r\n"
                body += f"--{boundary}--\r\n".encode()

                req = urllib.request.Request(
                    f"https://www.myminifactory.com/api/v2/objects/{object_id}/files",
                    data=body,
                    headers={"Authorization": f"Bearer {config.myminifactory_token}",
                             "Content-Type": f"multipart/form-data; boundary={boundary}"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    json.loads(resp.read().decode())

                object_url = obj.get("url", f"https://www.myminifactory.com/object/3d-print-{object_id}")

                log.info("myminifactory_published", extra={
                    "request_id": rid, "name": name, "object_id": object_id, "title": title,
                })

                return json.dumps({
                    "success": True, "object_id": object_id, "object_url": object_url,
                    "title": title, "file_uploaded": filename, "status": "draft",
                    "note": "Published as draft. Visit MyMiniFactory to add images, set category, and publish.",
                }, indent=2)

            except Exception as e:
                log.error("publish_myminifactory_failed", extra={"request_id": rid, "error": str(e)})
                return json.dumps({"success": False, "error": str(e), "traceback": __import__("traceback").format_exc()}, indent=2)

    @mcp.tool()
    def publish_cults3d(
        name: str, title: str, description: str = "",
        tags: str = '["3dprinting"]', license: str = "creative_commons_attribution",
        free: bool = True, price_cents: int = 0,
    ) -> str:
        """Publish a model to Cults3D via their GraphQL API.

        Requires CULTS3D_API_KEY environment variable.

        Args:
            name: Model name (must exist in current session)
            title: Creation title on Cults3D
            description: Creation description (HTML allowed)
            tags: JSON list of tags
            license: License type (e.g. "creative_commons_attribution")
            free: If True, publish as free model
            price_cents: Price in cents (only used if free=False)
        """
        rid = new_request_id()
        with log_tool_call(log, "publish_cults3d", {"name": name, "title": title}, rid):
            try:
                if not config.cults3d_api_key:
                    return json.dumps({
                        "success": False,
                        "error": "CULTS3D_API_KEY environment variable not set. "
                                 "Get your API key from https://cults3d.com/en/pages/api",
                    })

                stl_path = ensure_exported(store, config.output_dir, name, "stl")
                tag_list = json.loads(tags) if isinstance(tags, str) else tags

                auth_str = base64.b64encode(f"{config.cults3d_api_key}:".encode()).decode()

                query = """
                mutation CreateCreation($input: CreationInput!) {
                    createCreation(input: $input) {
                        creation { id slug url }
                        errors
                    }
                }
                """

                variables = {
                    "input": {
                        "name": title,
                        "description": description or f"3D-printable model: {title}",
                        "tags": tag_list, "license": license,
                        "free": free, "price": price_cents if not free else 0,
                        "status": "draft",
                    }
                }

                graphql_data = json.dumps({"query": query, "variables": variables}).encode()

                req = urllib.request.Request(
                    "https://cults3d.com/graphql",
                    data=graphql_data,
                    headers={"Authorization": f"Basic {auth_str}", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode())

                creation_data = result.get("data", {}).get("createCreation", {})
                errors = creation_data.get("errors", [])
                creation = creation_data.get("creation", {})

                if errors:
                    return json.dumps({"success": False, "errors": errors}, indent=2)

                log.info("cults3d_published", extra={
                    "request_id": rid, "name": name, "creation_id": creation.get("id"), "title": title,
                })

                return json.dumps({
                    "success": True, "creation_id": creation.get("id"),
                    "creation_url": creation.get("url", ""), "slug": creation.get("slug", ""),
                    "title": title, "status": "draft", "stl_path": str(stl_path),
                    "note": "Created as draft. Cults3D requires file upload through their web interface "
                            "or hosting files at a public URL. Upload the STL file manually at the creation URL.",
                }, indent=2)

            except Exception as e:
                log.error("publish_cults3d_failed", extra={"request_id": rid, "error": str(e)})
                return json.dumps({"success": False, "error": str(e), "traceback": __import__("traceback").format_exc()}, indent=2)
