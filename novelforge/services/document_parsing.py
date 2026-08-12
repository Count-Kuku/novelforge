"""Safe, structure-preserving parsers for imported reference documents."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from io import BytesIO
import mimetypes
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Iterable
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 192 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_PDF_PAGES = 2_000
SUPPORTED_DOCUMENT_EXTENSIONS = {".txt", ".md", ".markdown", ".docx", ".epub", ".pdf"}


class DocumentParsingError(ValueError):
    """Raised when an uploaded document cannot be parsed safely."""


@dataclass(slots=True)
class ParsedSection:
    title: str
    text: str
    level: int = 1
    order: int = 0
    content_kind: str = "section"
    location: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ParsedDocument:
    filename: str
    title: str
    media_type: str
    parser_name: str
    parser_version: str = "1"
    sections: list[ParsedSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        parts: list[str] = []
        for section in self.sections:
            body = str(section.text or "").strip()
            if not body:
                continue
            title = str(section.title or "").strip()
            if title and title != str(self.title or "").strip():
                level = min(max(int(section.level or 1), 1), 6)
                parts.append(f"{'#' * level} {title}\n\n{body}")
            else:
                parts.append(body)
        return "\n\n".join(parts).strip()

    def to_dict(self, *, include_text: bool = False, include_section_text: bool = False) -> dict:
        sections: list[dict] = []
        for section in self.sections:
            payload = section.to_dict()
            payload["char_count"] = len(str(payload.get("text") or ""))
            if not include_section_text:
                payload.pop("text", None)
            sections.append(payload)
        payload = {
            "filename": self.filename,
            "title": self.title,
            "media_type": self.media_type,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            # Parser metadata is stored with every source revision.  Keep the
            # default representation compact instead of duplicating the full
            # document body that is already present in source segments.
            "sections": sections,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }
        if include_text:
            payload["text"] = self.text
        return payload


def decode_text_bytes(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ("utf-16", "utf-8-sig", "utf-8", "gb18030")
    elif data and data.count(b"\x00") / len(data) >= 0.1:
        even_nulls = data[0::2].count(0)
        odd_nulls = data[1::2].count(0)
        encodings = (
            ("utf-16-le", "utf-16-be")
            if odd_nulls >= even_nulls
            else ("utf-16-be", "utf-16-le")
        ) + ("utf-8-sig", "utf-8", "gb18030")
    else:
        encodings = ("utf-8-sig", "utf-8", "gb18030", "utf-16", "utf-16-le", "utf-16-be")
    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.strip("\ufeff\x00\r\n\t "):
            return text.replace("\x00", ""), encoding
    return data.decode("utf-8", errors="ignore").replace("\x00", ""), "utf-8-ignore"


def _validate_document_size(filename: str, data: bytes) -> None:
    if not data:
        raise DocumentParsingError(f"文件为空：{filename}")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentParsingError(f"文件超过 {MAX_DOCUMENT_BYTES // (1024 * 1024)}MB 安全上限：{filename}")


def _validate_zip_archive(archive: ZipFile, filename: str) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise DocumentParsingError(f"压缩文档包含过多文件：{filename}")
    total_size = 0
    for info in infos:
        member = PurePosixPath(str(info.filename).replace("\\", "/"))
        if member.is_absolute() or ".." in member.parts:
            raise DocumentParsingError(f"压缩文档包含不安全路径：{info.filename}")
        if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
            raise DocumentParsingError(f"压缩文档成员过大：{info.filename}")
        total_size += int(info.file_size or 0)
        if total_size > MAX_ARCHIVE_TOTAL_BYTES:
            raise DocumentParsingError(f"压缩文档解压后超过安全上限：{filename}")


def _read_zip_member(archive: ZipFile, name: str) -> bytes:
    normalized = str(PurePosixPath(name))
    try:
        info = archive.getinfo(normalized)
    except KeyError as exc:
        raise DocumentParsingError(f"文档缺少必要内容：{normalized}") from exc
    if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
        raise DocumentParsingError(f"文档成员过大：{normalized}")
    return archive.read(info)


def _resolve_archive_member(base: PurePosixPath, reference: str) -> str:
    """Resolve an EPUB/OPF reference without allowing escape from the archive root."""

    decoded = unquote(str(reference or "").split("#", 1)[0].split("?", 1)[0]).replace("\\", "/")
    candidate = PurePosixPath(decoded)
    if candidate.is_absolute():
        raise DocumentParsingError(f"文档引用了不安全的绝对路径：{reference}")
    parts: list[str] = []
    for part in (*base.parts, *candidate.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise DocumentParsingError(f"文档引用越过了压缩包根目录：{reference}")
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise DocumentParsingError(f"文档引用路径为空：{reference}")
    return "/".join(parts)


def _sections_from_markdown(text: str, *, fallback_title: str) -> list[ParsedSection]:
    headings: list[tuple[int, int, int, str]] = []
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
                headings.append((offset, offset + len(content), len(match.group(1)), match.group(2).strip()))
        offset += len(line)
    if not headings:
        return [ParsedSection(title=fallback_title, text=text.strip(), level=1, order=1)] if text.strip() else []
    sections: list[ParsedSection] = []
    preface = text[: headings[0][0]].strip()
    if preface:
        sections.append(ParsedSection(title=fallback_title, text=preface, level=1, order=1, content_kind="preface"))
    for index, (start, heading_end, level, title) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        body = text[heading_end:end].strip()
        if body:
            sections.append(ParsedSection(
                title=title,
                text=body,
                level=level,
                order=len(sections) + 1,
                location={"char_start": start, "char_end": end},
            ))
    return sections


def _parse_plain_text(filename: str, data: bytes) -> ParsedDocument:
    text, encoding = decode_text_bytes(data)
    title = Path(filename).stem or "未命名资料"
    suffix = Path(filename).suffix.lower()
    sections = _sections_from_markdown(text, fallback_title=title) if suffix in {".md", ".markdown"} else [
        ParsedSection(title=title, text=text.strip(), level=1, order=1)
    ]
    return ParsedDocument(
        filename=filename,
        title=title,
        media_type="text/markdown" if suffix in {".md", ".markdown"} else "text/plain",
        parser_name="markdown" if suffix in {".md", ".markdown"} else "plain_text",
        sections=[section for section in sections if section.text.strip()],
        metadata={"encoding": encoding},
    )


_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DC_NS = "http://purl.org/dc/elements/1.1/"


def _word_text(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        local = node.tag.rsplit("}", 1)[-1]
        if local == "t" and node.text:
            parts.append(node.text)
        elif local == "tab":
            parts.append("\t")
        elif local in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _docx_style_names(archive: ZipFile) -> dict[str, str]:
    try:
        root = ET.fromstring(_read_zip_member(archive, "word/styles.xml"))
    except (DocumentParsingError, ET.ParseError):
        return {}
    result: dict[str, str] = {}
    for style in root.findall(f".//{{{_WORD_NS}}}style"):
        style_id = style.attrib.get(f"{{{_WORD_NS}}}styleId", "")
        name_node = style.find(f"{{{_WORD_NS}}}name")
        style_name = name_node.attrib.get(f"{{{_WORD_NS}}}val", "") if name_node is not None else ""
        if style_id:
            result[style_id] = style_name or style_id
    return result


def _docx_heading_level(paragraph: ET.Element, style_names: dict[str, str]) -> int | None:
    p_style = paragraph.find(f"./{{{_WORD_NS}}}pPr/{{{_WORD_NS}}}pStyle")
    if p_style is None:
        return None
    style_id = p_style.attrib.get(f"{{{_WORD_NS}}}val", "")
    style_name = style_names.get(style_id, style_id)
    match = re.search(r"(?:heading|标题)\s*([1-6])", style_name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _docx_title(archive: ZipFile, filename: str) -> str:
    try:
        root = ET.fromstring(_read_zip_member(archive, "docProps/core.xml"))
        title = root.findtext(f".//{{{_DC_NS}}}title", default="").strip()
        if title:
            return title
    except (DocumentParsingError, ET.ParseError):
        pass
    return Path(filename).stem or "未命名资料"


def _parse_docx(filename: str, data: bytes) -> ParsedDocument:
    try:
        with ZipFile(BytesIO(data)) as archive:
            _validate_zip_archive(archive, filename)
            root = ET.fromstring(_read_zip_member(archive, "word/document.xml"))
            style_names = _docx_style_names(archive)
            title = _docx_title(archive, filename)
            body = root.find(f".//{{{_WORD_NS}}}body")
            if body is None:
                raise DocumentParsingError("DOCX 缺少正文。")
            sections: list[ParsedSection] = []
            current_title = title
            current_level = 1
            current_lines: list[str] = []

            def flush() -> None:
                text = "\n\n".join(line for line in current_lines if line.strip()).strip()
                if text:
                    sections.append(ParsedSection(
                        title=current_title,
                        text=text,
                        level=current_level,
                        order=len(sections) + 1,
                        location={"docx_block_end": len(sections) + len(current_lines)},
                    ))

            for block in list(body):
                local = block.tag.rsplit("}", 1)[-1]
                if local == "p":
                    text = _word_text(block)
                    if not text:
                        continue
                    heading_level = _docx_heading_level(block, style_names)
                    if heading_level is not None:
                        flush()
                        current_title = text
                        current_level = heading_level
                        current_lines = []
                    else:
                        current_lines.append(text)
                elif local == "tbl":
                    rows: list[str] = []
                    for row in block.findall(f".//{{{_WORD_NS}}}tr"):
                        cells = [_word_text(cell) for cell in row.findall(f"./{{{_WORD_NS}}}tc")]
                        if any(cells):
                            rows.append(" | ".join(cells))
                    if rows:
                        current_lines.append("\n".join(rows))
            flush()
    except BadZipFile as exc:
        raise DocumentParsingError(f"DOCX 文件损坏或格式不正确：{filename}") from exc
    except ET.ParseError as exc:
        raise DocumentParsingError(f"DOCX XML 无法解析：{filename}") from exc

    return ParsedDocument(
        filename=filename,
        title=title,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        parser_name="docx_openxml",
        sections=sections,
        warnings=[] if sections else ["DOCX 中没有提取到可读正文。"],
        metadata={"heading_styles_detected": bool(style_names)},
    )


class _HTMLSectionParser(HTMLParser):
    BLOCK_TAGS = {"p", "li", "blockquote", "pre", "td", "th", "div"}
    SKIP_TAGS = {"script", "style", "svg", "nav"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[tuple[str, int, str]] = []
        self.current_title = ""
        self.current_level = 1
        self.current_blocks: list[str] = []
        self.buffer: list[str] = []
        self.active_tag = ""
        self.skip_depth = 0

    def _flush_buffer(self) -> None:
        text = re.sub(r"[ \t]+", " ", "".join(self.buffer)).strip()
        self.buffer = []
        if not text:
            return
        if re.fullmatch(r"h[1-6]", self.active_tag):
            self._flush_section()
            self.current_title = text
            self.current_level = int(self.active_tag[1])
        else:
            self.current_blocks.append(text)

    def _flush_section(self) -> None:
        text = "\n\n".join(self.current_blocks).strip()
        if text:
            self.sections.append((self.current_title, self.current_level, text))
        self.current_blocks = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if re.fullmatch(r"h[1-6]", tag) or tag in self.BLOCK_TAGS:
            self._flush_buffer()
            self.active_tag = tag
        elif tag == "br":
            self.buffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == self.active_tag:
            self._flush_buffer()
            self.active_tag = ""

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush_buffer()
        self._flush_section()


def _parse_epub_xhtml(data: bytes, fallback_title: str) -> list[ParsedSection]:
    text, _ = decode_text_bytes(data)
    parser = _HTMLSectionParser()
    parser.feed(text)
    parser.close()
    sections = []
    for title, level, body in parser.sections:
        sections.append(ParsedSection(
            title=title or fallback_title,
            text=body,
            level=level,
            order=len(sections) + 1,
            content_kind="epub_section",
        ))
    return sections


def _parse_epub(filename: str, data: bytes) -> ParsedDocument:
    try:
        with ZipFile(BytesIO(data)) as archive:
            _validate_zip_archive(archive, filename)
            container = ET.fromstring(_read_zip_member(archive, "META-INF/container.xml"))
            rootfile = next((node.attrib.get("full-path", "") for node in container.iter() if node.tag.endswith("rootfile")), "")
            if not rootfile:
                raise DocumentParsingError("EPUB 缺少 OPF 根文件。")
            rootfile = _resolve_archive_member(PurePosixPath(), rootfile)
            opf = ET.fromstring(_read_zip_member(archive, rootfile))
            manifest: dict[str, tuple[str, str]] = {}
            for node in opf.iter():
                if node.tag.endswith("item") and node.attrib.get("id"):
                    manifest[node.attrib["id"]] = (node.attrib.get("href", ""), node.attrib.get("media-type", ""))
            spine_ids = [node.attrib.get("idref", "") for node in opf.iter() if node.tag.endswith("itemref")]
            title = next((str(node.text or "").strip() for node in opf.iter() if node.tag.endswith("title") and str(node.text or "").strip()), Path(filename).stem)
            base = PurePosixPath(rootfile).parent
            sections: list[ParsedSection] = []
            for spine_index, item_id in enumerate(spine_ids, start=1):
                href, media_type = manifest.get(item_id, ("", ""))
                if not href or media_type not in {"application/xhtml+xml", "text/html"}:
                    continue
                member_name = _resolve_archive_member(base, href)
                fallback = PurePosixPath(href).stem or f"章节 {spine_index}"
                for section in _parse_epub_xhtml(_read_zip_member(archive, member_name), fallback):
                    section.order = len(sections) + 1
                    section.location = {"epub_item": member_name, "spine_index": spine_index}
                    sections.append(section)
    except BadZipFile as exc:
        raise DocumentParsingError(f"EPUB 文件损坏或格式不正确：{filename}") from exc
    except ET.ParseError as exc:
        raise DocumentParsingError(f"EPUB XML 无法解析：{filename}") from exc
    return ParsedDocument(
        filename=filename,
        title=title or Path(filename).stem,
        media_type="application/epub+zip",
        parser_name="epub_spine",
        sections=sections,
        warnings=[] if sections else ["EPUB 书脊中没有提取到可读正文。"],
        metadata={"spine_item_count": len(spine_ids)},
    )


def _parse_pdf(filename: str, data: bytes) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentParsingError("解析 PDF 需要安装 requirements.txt 中的 pypdf。") from exc
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")
            except Exception as exc:
                raise DocumentParsingError("暂不支持需要密码的 PDF。") from exc
            if not decrypted:
                raise DocumentParsingError("暂不支持需要密码的 PDF。")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentParsingError(f"PDF 超过 {MAX_PDF_PAGES} 页安全上限。")
        sections: list[ParsedSection] = []
        empty_pages = 0
        for page_index, page in enumerate(reader.pages, start=1):
            text = str(page.extract_text() or "").strip()
            if not text:
                empty_pages += 1
                continue
            sections.append(ParsedSection(
                title=f"第 {page_index} 页",
                text=text,
                level=2,
                order=len(sections) + 1,
                content_kind="pdf_page",
                location={"page": page_index},
            ))
        metadata = getattr(reader, "metadata", None) or {}
        title = str(metadata.get("/Title") or Path(filename).stem).strip()
    except DocumentParsingError:
        raise
    except Exception as exc:
        raise DocumentParsingError(f"PDF 无法解析：{filename}：{exc}") from exc
    warnings = []
    if empty_pages:
        warnings.append(f"{empty_pages} 页没有可提取文本。")
    if reader.pages and empty_pages / len(reader.pages) >= 0.3:
        warnings.append("较多页面没有文本，文件可能是扫描版 PDF；当前不会自动执行 OCR。")
    return ParsedDocument(
        filename=filename,
        title=title,
        media_type="application/pdf",
        parser_name="pypdf",
        sections=sections,
        warnings=warnings,
        metadata={"page_count": len(reader.pages), "empty_page_count": empty_pages},
    )


def get_local_ocr_readiness() -> dict:
    """Report the optional local OCR engine without importing it at startup."""

    executable = shutil.which("tesseract")
    if not executable:
        return {
            "available": False,
            "engine": "tesseract",
            "message": "未找到本地 Tesseract OCR，可关闭 OCR 后继续导入文本层。",
        }
    try:
        import fitz  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image  # noqa: F401
    except ImportError:
        return {
            "available": False,
            "engine": "tesseract",
            "message": "OCR Python 依赖未安装，请重新安装 requirements.txt。",
        }
    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception as exc:
        return {
            "available": False,
            "engine": "tesseract",
            "message": f"Tesseract OCR 无法启动：{exc}",
        }
    return {
        "available": True,
        "engine": "tesseract",
        "version": version,
        "executable": executable,
        "message": "本地 OCR 可用；资料不会上传到第三方 OCR 服务。",
    }


def ocr_pdf_bytes(
    filename: str,
    data: bytes,
    *,
    languages: str = "chi_sim+eng",
    dpi: int = 200,
) -> ParsedDocument:
    """Run explicitly requested local OCR and retain page confidence evidence."""

    clean_filename = Path(str(filename or "document.pdf")).name
    _validate_document_size(clean_filename, data)
    readiness = get_local_ocr_readiness()
    if not readiness.get("available"):
        raise DocumentParsingError(str(readiness.get("message") or "本地 OCR 不可用。"))
    try:
        import fitz  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - guarded by readiness
        raise DocumentParsingError("OCR Python 依赖未安装。") from exc

    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentParsingError(f"PDF 无法打开以执行 OCR：{exc}") from exc
    if pdf.page_count > MAX_PDF_PAGES:
        pdf.close()
        raise DocumentParsingError(f"PDF 超过 {MAX_PDF_PAGES} 页安全上限。")

    sections: list[ParsedSection] = []
    page_confidences: list[dict] = []
    low_confidence_pages: list[int] = []
    zoom = max(int(dpi or 200), 72) / 72.0
    try:
        for page_index in range(pdf.page_count):
            page = pdf.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            try:
                ocr_data = pytesseract.image_to_data(
                    image,
                    lang=languages,
                    output_type=pytesseract.Output.DICT,
                )
            except Exception as exc:
                raise DocumentParsingError(
                    f"第 {page_index + 1} 页 OCR 失败：{exc}"
                ) from exc
            words: list[str] = []
            confidences: list[float] = []
            for text, raw_confidence in zip(
                ocr_data.get("text", []),
                ocr_data.get("conf", []),
            ):
                clean_text = str(text or "").strip()
                try:
                    confidence = float(raw_confidence)
                except (TypeError, ValueError):
                    confidence = -1.0
                if clean_text:
                    words.append(clean_text)
                if clean_text and confidence >= 0:
                    confidences.append(confidence)
            page_text = " ".join(words).strip()
            mean_confidence = (
                round(sum(confidences) / len(confidences), 2)
                if confidences
                else 0.0
            )
            page_number = page_index + 1
            page_confidences.append(
                {
                    "page": page_number,
                    "confidence": mean_confidence,
                    "char_count": len(page_text),
                }
            )
            if mean_confidence < 60:
                low_confidence_pages.append(page_number)
            if page_text:
                sections.append(
                    ParsedSection(
                        title=f"第 {page_number} 页",
                        text=page_text,
                        level=2,
                        order=len(sections) + 1,
                        content_kind="ocr_pdf_page",
                        location={"page": page_number, "ocr_confidence": mean_confidence},
                    )
                )
    finally:
        pdf.close()

    warnings: list[str] = []
    if low_confidence_pages:
        preview = "、".join(str(value) for value in low_confidence_pages[:12])
        warnings.append(f"OCR 置信度低于 60 的页面：{preview}。请在附件状态中抽查。")
    if not sections:
        warnings.append("OCR 没有识别到可用文本。")
    return ParsedDocument(
        filename=clean_filename,
        title=Path(clean_filename).stem or "扫描 PDF",
        media_type="application/pdf",
        parser_name="tesseract_ocr",
        sections=sections,
        warnings=warnings,
        metadata={
            "page_count": len(page_confidences),
            "empty_page_count": len([item for item in page_confidences if not item["char_count"]]),
            "ocr_requested": True,
            "ocr_engine": readiness.get("engine"),
            "ocr_engine_version": readiness.get("version"),
            "ocr_languages": languages,
            "ocr_page_confidences": page_confidences,
        },
    )


def parse_document_bytes(filename: str, data: bytes) -> ParsedDocument:
    """Parse an uploaded document without executing embedded active content."""

    clean_filename = Path(str(filename or "document")).name
    _validate_document_size(clean_filename, data)
    suffix = Path(clean_filename).suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise DocumentParsingError(f"不支持的资料格式：{suffix or '无扩展名'}")
    if suffix in {".txt", ".md", ".markdown"}:
        return _parse_plain_text(clean_filename, data)
    if suffix == ".docx":
        return _parse_docx(clean_filename, data)
    if suffix == ".epub":
        return _parse_epub(clean_filename, data)
    return _parse_pdf(clean_filename, data)


def combine_parsed_documents(documents: Iterable[ParsedDocument]) -> str:
    parts: list[str] = []
    for document in documents:
        document_parts: list[str] = []
        document_title = str(document.title or Path(document.filename).stem).strip()
        for section in document.sections:
            body = str(section.text or "").strip()
            if not body:
                continue
            section_title = str(section.title or "").strip()
            if section_title and section_title != document_title:
                level = min(max(int(section.level or 1) + 1, 2), 6)
                document_parts.append(f"{'#' * level} {section_title}\n\n{body}")
            else:
                document_parts.append(body)
        if not document_parts:
            continue
        parts.append(f"# {document_title}\n\n" + "\n\n".join(document_parts))
    return "\n\n".join(parts).strip()


def document_media_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    explicit = {
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".epub": "application/epub+zip",
    }
    return explicit.get(suffix) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
