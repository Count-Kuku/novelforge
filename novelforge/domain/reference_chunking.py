"""Pure structure-aware splitting rules for long reference material."""
from __future__ import annotations

from hashlib import sha256
import re


CHAPTER_TITLE_PATTERN = re.compile(
    r"^(?:第[零〇一二两三四五六七八九十百千万0-9]+[章节卷回幕篇部集]|chapter\s+\d+|prologue|epilogue|序章|楔子|尾声|番外)",
    re.IGNORECASE,
)
SCENE_BREAK_PATTERN = re.compile(r"^\s*(?:\*\s*\*\s*\*|-{3,}|—{3,}|={3,}|※{1,3})\s*$", re.MULTILINE)
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[。！？!?；;…])(?=[^。！？!?；;…])")

STRUCTURED_SOURCE_LIMITS = {
    "external_character_sheet": 3600,
    "external_location_sheet": 3600,
    "external_organization_sheet": 3600,
    "external_timeline_note": 3000,
    "external_canon_event": 3000,
    "external_world_rule": 3200,
    "external_artifact_note": 3200,
}


def _normalize_newlines(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _hard_split_sentence(sentence: str, max_chars: int) -> list[str]:
    clean = sentence.strip()
    if not clean:
        return []
    if len(clean) <= max_chars:
        return [clean]
    pieces: list[str] = []
    cursor = 0
    while cursor < len(clean):
        end = min(cursor + max_chars, len(clean))
        if end < len(clean):
            window = clean[cursor:end]
            candidates = [window.rfind(mark) for mark in ("，", ",", "、", "：", ":")]
            boundary = max(candidates)
            if boundary >= max_chars // 2:
                end = cursor + boundary + 1
        piece = clean[cursor:end].strip()
        if piece:
            pieces.append(piece)
        cursor = max(end, cursor + 1)
    return pieces


def _atomic_blocks(text: str, max_chars: int) -> list[str]:
    blocks: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", text):
        clean = paragraph.strip()
        if not clean:
            continue
        if len(clean) <= max_chars:
            blocks.append(clean)
            continue
        sentences = [item.strip() for item in SENTENCE_BOUNDARY_PATTERN.split(clean) if item.strip()]
        if len(sentences) <= 1:
            blocks.extend(_hard_split_sentence(clean, max_chars))
            continue
        for sentence in sentences:
            blocks.extend(_hard_split_sentence(sentence, max_chars))
    return blocks


def split_text_by_boundaries(text: str, max_chars: int, *, overlap_chars: int = 0) -> list[str]:
    """Split on paragraphs/sentences and optionally carry a bounded tail forward."""

    max_chars = max(int(max_chars or 0), 200)
    blocks = _atomic_blocks(_normalize_newlines(text), max_chars)
    if not blocks:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for block in blocks:
        added = len(block) + (2 if current else 0)
        if current and current_length + added > max_chars:
            combined = "\n\n".join(current).strip()
            if combined:
                chunks.append(combined)
            carry_text = combined[-min(int(overlap_chars or 0), max_chars):].strip() if overlap_chars > 0 else ""
            # Overlap is optional context, never permission to exceed the
            # advertised hard chunk limit.
            current = [carry_text] if carry_text and len(carry_text) + 2 + len(block) <= max_chars else []
            current_length = len(carry_text) if current else 0
        current.append(block)
        current_length = len("\n\n".join(current))
    if current:
        combined = "\n\n".join(current).strip()
        if combined and (not chunks or combined != chunks[-1]):
            chunks.append(combined)
    return chunks


def _structural_sections(source_title: str, text: str) -> list[dict]:
    markdown_headings: list[tuple[int, int, int, str]] = []
    fence = ""
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        stripped = content.lstrip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            marker = fence_match.group(1)[0]
            if not fence:
                fence = marker
            elif fence == marker:
                fence = ""
            offset += len(line)
            continue
        if not fence:
            match = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*$", content)
            if match:
                markdown_headings.append((offset, offset + len(content), len(match.group(1)), match.group(2).strip()))
        offset += len(line)
    if markdown_headings:
        sections: list[dict] = []
        heading_stack: list[tuple[int, str]] = []
        preface = text[: markdown_headings[0][0]].strip()
        if preface:
            sections.append({"title": f"{source_title} 序言/简介", "content": preface, "heading_path": [source_title], "start": 0})
        for index, (start, heading_end, level, title) in enumerate(markdown_headings):
            heading_stack = [(item_level, item_title) for item_level, item_title in heading_stack if item_level < level]
            heading_stack.append((level, title))
            end = markdown_headings[index + 1][0] if index + 1 < len(markdown_headings) else len(text)
            body = text[heading_end:end].strip()
            if body:
                sections.append({
                    "title": title,
                    "content": body,
                    "heading_path": [item_title for _, item_title in heading_stack],
                    "start": heading_end,
                    "end": end,
                    "split_method": "结构标题",
                })
        if sections:
            return sections

    lines = text.splitlines(keepends=True)
    starts: list[tuple[int, int, str]] = []
    cursor = 0
    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if CHAPTER_TITLE_PATTERN.match(stripped):
            starts.append((line_index, cursor, stripped))
        cursor += len(line)
    if starts:
        sections = []
        first_line, first_offset, _ = starts[0]
        preface = "".join(lines[:first_line]).strip()
        if preface:
            sections.append({"title": f"{source_title} 序言/简介", "content": preface, "heading_path": [source_title], "start": 0, "end": first_offset})
        for index, (line_index, start_offset, title) in enumerate(starts):
            end_line = starts[index + 1][0] if index + 1 < len(starts) else len(lines)
            end_offset = starts[index + 1][1] if index + 1 < len(starts) else len(text)
            body = "".join(lines[line_index:end_line]).strip()
            if body:
                sections.append({
                    "title": title,
                    "content": body,
                    "heading_path": [title],
                    "start": start_offset,
                    "end": end_offset,
                    "split_method": "章节标题",
                })
        return sections
    return [{"title": source_title, "content": text, "heading_path": [source_title], "start": 0, "end": len(text), "split_method": "段落语义"}]


def infer_content_kind(source_type: str, title: str = "") -> str:
    source_type = str(source_type or "").lower()
    title = str(title or "").lower()
    if "timeline" in source_type or any(word in title for word in ("时间线", "年表", "大事记")):
        return "timeline"
    if "character" in source_type or "角色" in title:
        return "character"
    if "relationship" in source_type or "关系" in title:
        return "relationship"
    if "world_rule" in source_type or "规则" in title or "设定" in title:
        return "world_rule"
    if "style" in source_type or "文风" in title:
        return "style"
    return "narrative"


def split_reference_text(
    source_title: str,
    raw_text: str,
    *,
    max_chars: int = 6000,
    source_type: str = "external_source",
) -> list[dict]:
    """Create extraction segments with stable structure and precise source offsets."""

    text = _normalize_newlines(raw_text)
    if not text:
        return []
    max_chars = min(max(int(max_chars or 6000), 200), 20_000)
    max_chars = min(max_chars, STRUCTURED_SOURCE_LIMITS.get(str(source_type or ""), max_chars))
    sections = _structural_sections(source_title, text)
    segments: list[dict] = []
    search_cursor = 0
    for section_index, section in enumerate(sections, start=1):
        section_text = str(section.get("content") or "").strip()
        if not section_text:
            continue
        scene_parts = [item.strip() for item in SCENE_BREAK_PATTERN.split(section_text) if item.strip()]
        if not scene_parts:
            scene_parts = [section_text]
        part_number = 0
        for scene_index, scene_text in enumerate(scene_parts, start=1):
            pieces = split_text_by_boundaries(scene_text, max_chars)
            total_parts = sum(len(split_text_by_boundaries(value, max_chars)) for value in scene_parts)
            for piece in pieces:
                part_number += 1
                located_at = text.find(piece, search_cursor)
                if located_at < 0:
                    located_at = text.find(piece)
                if located_at < 0:
                    located_at = int(section.get("start") or 0)
                end_offset = min(located_at + len(piece), len(text))
                search_cursor = max(search_cursor, end_offset)
                base_title = str(section.get("title") or source_title).strip()
                suffix = ""
                if total_parts > 1:
                    suffix = f"（{part_number}/{total_parts}）"
                segments.append({
                    "title": f"{base_title}{suffix}",
                    "content": piece,
                    "split_method": str(section.get("split_method") or "段落语义") + ("+场景" if len(scene_parts) > 1 else ""),
                    "chapter_index": section_index,
                    "scene_index": scene_index,
                    "part_index": part_number,
                    "heading_path": list(section.get("heading_path") or [base_title]),
                    "parent_title": base_title,
                    "content_kind": infer_content_kind(source_type, base_title),
                    "start_offset": located_at,
                    "end_offset": end_offset,
                    "char_count": len(piece),
                    "content_hash": sha256(piece.encode("utf-8")).hexdigest(),
                })
    for index, segment in enumerate(segments, start=1):
        segment["index"] = index
        segment["previous_index"] = index - 1 if index > 1 else None
        segment["next_index"] = index + 1 if index < len(segments) else None
    return segments
