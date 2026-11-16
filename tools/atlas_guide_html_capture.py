"""Offline conversion of *authorized saved* Ganymède pages to Atlas source JSON.

No network requests, permissions inference, text summarization, live route
activation or Qt. Every saved HTML article is exactly one authored Atlas step.
An incomplete paginated capture is rejected instead of padded with guesses.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from app.modules.encyclopedia.services.guide_shared_route_contract import (
    project_authorized_guide,
)
from tools.atlas_guide_importer import _load_strict_json

TOOL_SPEC = {
    "schema_version": 1,
    "id": "atlas-guide-html-capture",
    "role": "guide_authorized_source_capture",
    "capabilities": ["guide", "conversion"],
    "modes": ["offline_html", "dry_run", "explicit_source_export"],
    "cost_hint": "low",
    "side_effects": "artifact_output",
    "structured_output": True,
    "canonical": False,
    "recommended_tests": ["tests.test_atlas_guide_html_capture"],
    "target_scopes": ["encyclopedia_guide"],
}

_VOID = frozenset(("img", "input", "br", "hr", "meta", "link", "source", "wbr"))
_STEP = re.compile(r"step-([1-9][0-9]*)\Z")
_COORD = re.compile(r"\[\s*(-?[0-9]{1,5})\s*,\s*(-?[0-9]{1,5})\s*\]")
_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
_SIG = {
    "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda b: b.startswith(b"RIFF") and b[8:12] == b"WEBP",
}
_ALLOWED_ROLES = {"quest", "npc", "item", "equipment", "monster", "boss", "position"}


class SourceCaptureError(ValueError):
    """The saved page cannot be projected without silent content loss."""


class _Node:
    def __init__(self, tag: str, attrs: dict[str, str] | None = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[_Node | str] = []


class _DOM(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]
        self.feed(source)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _desc(node: _Node):
    for child in node.children:
        if isinstance(child, _Node):
            yield child
            yield from _desc(child)


def _plain(node: _Node) -> str:
    return "".join(
        child if isinstance(child, str) else _plain(child)
        for child in node.children
        if isinstance(child, str) or child.tag != "img"
    )


def _runs(node: _Node) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []

    def append(value: str, role: str, href: str | None) -> None:
        if not value:
            return
        run = {"text": value, "role": role}
        if href:
            run["href"] = href
        if result and {k: v for k, v in result[-1].items() if k != "text"} == {
            k: v for k, v in run.items() if k != "text"
        }:
            result[-1]["text"] += value
        else:
            result.append(run)

    def walk(current: _Node, role: str = "plain", href: str | None = None,
             icon: bool = False) -> None:
        if current.tag in {"script", "style", "iframe", "video", "canvas"}:
            raise SourceCaptureError(f"unsupported source element <{current.tag}>")
        marker = current.attrs.get("data-type", "")
        if marker == "custom-tag":
            typed = current.attrs.get("type", "")
            if typed in _ALLOWED_ROLES:
                role = typed
            icon = True
        if current.tag == "a":
            link = current.attrs.get("href", "")
            if link:
                parts = urlsplit(link)
                if parts.scheme != "https" or not parts.hostname:
                    raise SourceCaptureError(f"unsupported source link {link!r}")
                href = link
        if current.tag == "img":
            if not icon and current.attrs.get("alt") not in {
                "item", "quest", "monster", "GuideStep", "boss",
            }:
                raise SourceCaptureError("inline image needs a separate captured media block")
            return
        if current.tag == "input":
            return
        if current.tag == "br":
            append("\u2028", role, href)
            return
        for child in current.children:
            if isinstance(child, str):
                append(child, role, href)
            else:
                walk(child, role, href, icon)

    walk(node)
    # HTML indentation is not authored prose: browsers collapse formatting
    # whitespace. Keep inline roles/links while matching visible text.
    # The explicit <br> sentinel remains a real Atlas line break.
    normalized: list[dict[str, str]] = []
    for original in result:
        entry = dict(original)
        entry["text"] = re.sub(
            r"\s+", " ", entry["text"].replace("\u2028", "\x00")
        ).replace("\x00", "\n")
        if not normalized:
            entry["text"] = entry["text"].lstrip(" ")
        elif normalized[-1]["text"].endswith(" "):
            entry["text"] = entry["text"].lstrip(" ")
        if entry["text"].lstrip(" ").startswith((".", ",", ":", ";", "!", "?")):
            if normalized:
                normalized[-1]["text"] = normalized[-1]["text"].rstrip(" ")
            entry["text"] = entry["text"].lstrip(" ")
        if entry["text"]:
            normalized.append(entry)
    if normalized:
        normalized[-1]["text"] = normalized[-1]["text"].rstrip(" ")
    return [entry for entry in normalized if entry["text"]]


def _media(node: _Node, assets: dict[str, Path]) -> dict[str, Any]:
    src = node.attrs.get("src", "")
    alt = node.attrs.get("alt", "")
    if not alt.strip():
        raise SourceCaptureError("source image has no authored alt text")
    if src.startswith("data:"):
        match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)", src)
        if not match:
            raise SourceCaptureError("image data URL is unsupported or malformed")
        mime, encoded = match.groups()
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise SourceCaptureError("invalid source image bytes") from exc
    else:
        path = assets.get(src)
        if path is None:
            raise SourceCaptureError(f"source image missing local authorized asset: {src}")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise SourceCaptureError(f"invalid source media file for {src}")
        data = path.read_bytes()
        suffix = path.suffix.lower()
        mime = next((name for name, ext in _MIME.items() if suffix == ext), None)
        if suffix == ".jpeg":
            mime = "image/jpeg"
        if mime is None:
            raise SourceCaptureError(f"unsupported source image format for {src}")
    if not data or len(data) > 2 * 1024 * 1024 or not _SIG[mime](data):
        raise SourceCaptureError(f"invalid or oversized source image: {src}")
    return {
        "type": "image", "alt": alt, "mime": mime,
        "sha256": hashlib.sha256(data).hexdigest(),
        "data_base64": base64.b64encode(data).decode("ascii"),
    }


def _blocks(container: _Node, assets: dict[str, Path]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    check_index = 0

    def add(node: _Node) -> None:
        nonlocal check_index
        tag = node.tag
        if tag in {"script", "style", "iframe", "video", "canvas"}:
            raise SourceCaptureError(f"unsupported guide element <{tag}>")
        if tag in {"p", "h1", "h2", "h3", "h4"}:
            images = [x for x in _desc(node) if x.tag == "img"
                      and x.attrs.get("alt") not in {"item", "quest", "monster", "GuideStep", "boss"}]
            if images:
                if len(images) != 1 or _plain(node).strip():
                    raise SourceCaptureError("mixed inline media/text cannot be imported faithfully")
                result.append(_media(images[0], assets))
                return
            runs = _runs(node)
            if not "".join(run["text"] for run in runs).strip():
                return
            if tag == "p":
                result.append({"type": "paragraph", "runs": runs})
            else:
                result.append({"type": "heading", "level": min(int(tag[1]), 3), "runs": runs})
        elif tag == "img":
            result.append(_media(node, assets))
        elif tag in {"ul", "ol"}:
            entries = [child for child in node.children
                       if isinstance(child, _Node) and child.tag == "li"]
            if not entries:
                raise SourceCaptureError("source list has no items")
            if node.attrs.get("data-type") == "taskList":
                items: list[dict[str, Any]] = []
                for li in entries:
                    if li.attrs.get("data-checked") not in {"true", "false"}:
                        raise SourceCaptureError("source checklist state missing")
                    runs = _runs(li)
                    value = "".join(run["text"] for run in runs)
                    if not value.strip():
                        raise SourceCaptureError("empty source checklist entry")
                    check_index += 1
                    items.append({
                        "id": f"source-check-{check_index}",
                        "text": value, "checked": li.attrs.get("data-checked") == "true",
                        "runs": runs,
                    })
                result.append({"type": "checklist", "items": items})
            else:
                for li in entries:
                    runs = _runs(li)
                    if "".join(r["text"] for r in runs).strip():
                        result.append({"type": "paragraph", "runs": runs})
        else:
            for child in node.children:
                if isinstance(child, str):
                    if child.strip():
                        raise SourceCaptureError(f"unhandled source text inside <{tag}>")
                else:
                    add(child)

    for node in container.children:
        if isinstance(node, str):
            if node.strip():
                raise SourceCaptureError("source text outside a structured guide block")
        else:
            add(node)
    return result


def extract_saved_html(html: str, *, assets: dict[str, Path] | None = None
                       ) -> list[dict[str, Any]]:
    """Capture exactly the visible article boundaries from one saved HTML page."""
    dom = _DOM(html)
    articles = [node for node in _desc(dom.root)
                if node.tag == "article" and _STEP.fullmatch(node.attrs.get("id", ""))]
    if not articles:
        raise SourceCaptureError("no Ganymede step articles in saved HTML")
    result: list[dict[str, Any]] = []
    for article in articles:
        number = int(_STEP.fullmatch(article.attrs["id"]).group(1))
        headings = [node for node in _desc(article) if node.tag == "h2"]
        if len(headings) != 1:
            raise SourceCaptureError(f"step {number}: missing/ambiguous heading")
        heading_text = _plain(headings[0]).strip()
        positions = _COORD.findall(heading_text)
        if len(positions) > 1:
            raise SourceCaptureError(f"step {number}: ambiguous coordinates")
        contents = [node for node in _desc(article)
                    if node.tag == "div" and "guide-content" in node.attrs.get("class", "").split()]
        if len(contents) != 1:
            raise SourceCaptureError(f"step {number}: missing/ambiguous source content")
        blocks = _blocks(contents[0], assets or {})
        if not blocks or blocks[0]["type"] != "paragraph":
            raise SourceCaptureError(f"step {number}: source starts without paragraph")
        text = "".join(run["text"] for run in blocks[0]["runs"])
        if not text.strip():
            raise SourceCaptureError(f"step {number}: empty first paragraph")
        stage: dict[str, Any] = {
            "source_step_id": f"step-{number:04d}",
            "title": heading_text,
            "actions": [{
                "action_id": "authored-page-content", "kind": "quest",
                "text": text, "rich_blocks": blocks,
            }],
        }
        if positions:
            stage["coordinates"] = [int(positions[0][0]), int(positions[0][1])]
        result.append({"number": number, "step": stage})
    return result


def convert_manifest(manifest: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Convert local, authorized, paginated HTML. Never fetch or invent text."""
    if manifest.get("rights_verified") is not True or manifest.get("reference_verified") is not True:
        raise SourceCaptureError("explicit authorized rights/reference evidence required")
    guides = manifest.get("guides")
    if not isinstance(guides, list) or not guides:
        raise SourceCaptureError("nonempty guides manifest required")
    source_guides: list[dict[str, Any]] = []
    seen_guides: set[str] = set()
    for guide in guides:
        if not isinstance(guide, dict):
            raise SourceCaptureError("invalid guide manifest entry")
        guide_id, title, count = guide.get("guide_id"), guide.get("title"), guide.get("expected_steps")
        pages = guide.get("pages")
        if (not isinstance(guide_id, str) or not guide_id.strip()
                or not isinstance(title, str) or not title.strip()
                or type(count) is not int or count < 1
                or not isinstance(pages, list) or not pages):
            raise SourceCaptureError("guide requires ID, title, expected steps and saved pages")
        if guide_id in seen_guides:
            raise SourceCaptureError(f"duplicate guide ID: {guide_id}")
        seen_guides.add(guide_id)
        assets: dict[str, Path] = {}
        for url, filename in (guide.get("media_files") or {}).items():
            if not url.startswith("https://"):
                raise SourceCaptureError("media URL must be HTTPS")
            assets[url] = _within(root, filename)
        steps: list[dict[str, Any]] = []
        for filename in pages:
            path = _within(root, filename)
            if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                raise SourceCaptureError("missing or oversized saved HTML page")
            html = path.read_text(encoding="utf-8")
            for entry in extract_saved_html(html, assets=assets):
                expected_number = len(steps) + 1
                if entry["number"] != expected_number:
                    raise SourceCaptureError(
                        f"guide {guide_id}: missing/duplicate/reordered step "
                        f"{expected_number}, found {entry['number']}"
                    )
                entry["step"]["capture_id"] = hashlib.sha256(html.encode()).hexdigest()
                steps.append(entry["step"])
        if len(steps) != count:
            raise SourceCaptureError(
                f"guide {guide_id}: incomplete paginated capture: {len(steps)}/{count}"
            )
        candidate = {"guide_id": guide_id, "title": title, "steps": steps}
        # Reuse the exact 95-guide projector; unrenderable source material blocks.
        project_authorized_guide(candidate)
        source_guides.append(candidate)
    is_complete = manifest.get("complete_inventory") is True
    step_count = sum(len(guide["steps"]) for guide in source_guides)
    if is_complete and (len(source_guides) != 95 or step_count != 7705):
        raise SourceCaptureError(
            f"full inventory incomplete: {len(source_guides)}/95 guides, "
            f"{step_count}/7705 steps"
        )
    return {
        "schema_version": 1,
        "rights_verified": True,
        "reference_verified": True,
        "complete": is_complete,
        "guides": source_guides,
    }


def _within(root: Path, filename: Any) -> Path:
    if not isinstance(filename, str) or not filename or "\\" in filename:
        raise SourceCaptureError("invalid local capture path")
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts:
        raise SourceCaptureError("capture path escapes manifest directory")
    target = root / relative
    if any(path.is_symlink() for path in (target, *tuple(target.parents)[:len(relative.parts)])):
        raise SourceCaptureError("linked capture path is not supported")
    return target


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="Offline authorized Ganymede HTML -> full Atlas JSON")
    cli.add_argument("--manifest", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True,
                     help="New explicit .json under artifacts/, never installed data")
    args = cli.parse_args(argv)
    try:
        manifest = _load_strict_json(args.manifest)
        output = args.output.resolve()
        if (args.output.exists() or args.output.suffix != ".json"
                or "artifacts" not in args.output.parts
                or any(x in {".git", "data", "saves", "profiles"} for x in args.output.parts)):
            raise SourceCaptureError("output must be a new artifacts/*.json file")
        result = convert_manifest(manifest, root=args.manifest.parent.resolve())
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": "FULL_SOURCE_CAPTURE_PREVIEW_ONLY",
            "guides": len(result["guides"]),
            "steps": sum(len(g["steps"]) for g in result["guides"]),
            "certified": False,
        }, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        cli.exit(2, f"GUIDE_CAPTURE_BLOCKED: {exc}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
