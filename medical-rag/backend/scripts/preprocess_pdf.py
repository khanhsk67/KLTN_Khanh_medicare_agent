# -*- coding: utf-8 -*-
"""
Preprocess PDF y tế → JSONL chunks có metadata.

Đặc thù file "Huong-dan-Chan-doan-va-dieu-tri-cac-benh-da-lieu-2023.pdf":
- Trang 1-7  : Bìa, chữ ký số, mục lục, danh mục viết tắt → SKIP
- Trang 8-455: 6 chương nội dung (Chương 1..6, mỗi chương nhiều bệnh) → KEEP
- Trang 456+ : Tài liệu tham khảo → SKIP

Output:
    data/processed/derma_chunks.jsonl
    Mỗi line là 1 JSON object:
    {
      "id": "<sha256-32hex>",
      "content": "...",
      "source_file": "...",
      "page_number": N,
      "chapter": "Chương X: ...",
      "disease": "BỆNH XYZ",
      "chunk_index": K
    }

Cách dùng:
    cd medical-rag/backend
    python scripts/preprocess_pdf.py \
        --pdf data/pdfs/Huong-dan-Chan-doan-va-dieu-tri-cac-benh-da-lieu-2023.pdf \
        --output data/processed/derma_chunks.jsonl \
        --skip-start 7 --skip-end-marker "TÀI LIỆU THAM KHẢO"
"""
import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Add backend/ to sys.path để import được app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1000           # ký tự — phù hợp cho 1 đoạn bệnh có triệu chứng + điều trị
CHUNK_OVERLAP = 150         # giữ ngữ cảnh giữa các chunk liền nhau
MIN_CHUNK_CHARS = 100       # bỏ chunk quá ngắn (thường là rác)
MIN_ALPHA_RATIO = 0.55      # bỏ trang có < 55% là chữ cái (thường là sơ đồ/bảng vỡ)

# Pattern nhận diện
RE_PAGE_HEADER = re.compile(r"^\s*\d+\s*\n", re.MULTILINE)
RE_SIGNATURE_LINE = re.compile(r"^syt_\w+_vt_.*?\d{2}/\d{2}/\d{4}.*?$", re.MULTILINE)
RE_SIGNATURE_BLOCK = re.compile(
    r"(Ký bởi:.*?\+07:00|Cơ quan:.*?BỘ Y TẾ|Ngày ký:.*?\+07:00)",
    re.DOTALL,
)
RE_CHAPTER = re.compile(r"^Chương\s+(\d+)\s*:\s*(.+?)$", re.MULTILINE)
# Tên bệnh: dòng TOÀN CHỮ HOA tiếng Việt (cho phép space, dấu gạch, dấu phẩy).
# Pattern này match rộng — sau đó validate bằng cách check next 300 chars
# có chứa "1. ĐẠI CƯƠNG" hoặc "(<english_name>)" hay không.
VN_UPPER = (
    r"A-ZÀÁẢÃẠÂẤẦẨẪẬĂẮẰẲẴẶĐÈÉẺẼẸÊẾỀỂỄỆ"
    r"ÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ"
)
RE_DISEASE_HEADING = re.compile(
    rf"^\s*([{VN_UPPER}][{VN_UPPER}\s\-–,/]{{4,}})\s*$",
    re.MULTILINE,
)
# Marker xác nhận đây thực sự là heading bệnh (xuất hiện sau heading)
RE_DISEASE_CONFIRM = re.compile(
    r"(1\.\s*ĐẠI\s+CƯƠNG|\([A-Za-z][A-Za-z\s\-]+\))",
)
RE_MULTI_WS = re.compile(r"[ \t]+")
RE_MULTI_NL = re.compile(r"\n{3,}")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PageBlock:
    """Đại diện cho text của 1 trang sau khi clean."""
    page_number: int
    text: str
    chapter: str = ""
    disease: str = ""


@dataclass
class Chunk:
    id: str
    content: str
    source_file: str
    page_number: int
    chapter: str
    disease: str
    chunk_index: int


# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------
def hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def alpha_ratio(text: str) -> float:
    """Tỷ lệ ký tự chữ cái trong text. Trang sơ đồ/bảng vỡ có ratio thấp."""
    if not text:
        return 0.0
    alpha = sum(1 for c in text if c.isalpha())
    return alpha / len(text)


def clean_page_text(text: str) -> str:
    """
    Làm sạch text 1 trang:
    - Xóa số trang ở đầu trang
    - Xóa dòng chữ ký số
    - Gộp multiple whitespace
    - Gộp multiple newline (>2 → 2)
    - Strip
    """
    if not text:
        return ""
    # Xóa chữ ký số (dòng + block)
    text = RE_SIGNATURE_LINE.sub("", text)
    text = RE_SIGNATURE_BLOCK.sub("", text)
    # Xóa các con số đứng riêng 1 dòng ngắn (ngày ký 06, 12, 4416...)
    text = re.sub(r"^\d{2,4}\s*$", "", text, flags=re.MULTILINE)
    # Xóa số trang đầu
    text = RE_PAGE_HEADER.sub("", text, count=1)
    # Bình thường hoá whitespace
    text = RE_MULTI_WS.sub(" ", text)
    text = RE_MULTI_NL.sub("\n\n", text)
    return text.strip()


def find_chapter(text: str) -> str:
    """Tìm tiêu đề Chương trong text (nếu có)."""
    m = RE_CHAPTER.search(text)
    if m:
        return f"Chương {m.group(1)}: {m.group(2).strip()}"
    return ""


def find_disease(text: str) -> str:
    """
    Tìm tên bệnh: dòng TOÀN HOA + ngay sau đó có "1. ĐẠI CƯƠNG" hoặc "(English)".
    Iterate qua mọi match — match cuối cùng được dùng (vì trang có thể có 2 bệnh).
    """
    last_disease = ""
    for m in RE_DISEASE_HEADING.finditer(text):
        candidate = m.group(1).strip()
        candidate = re.sub(r"\s+", " ", candidate)

        # Bỏ candidate quá dài (chắc chắn không phải tên bệnh)
        if len(candidate) > 80:
            continue
        # Bỏ candidate có quá nhiều dấu phẩy (list bệnh trong câu mô tả)
        if candidate.count(",") > 3:
            continue
        # Bỏ candidate trông giống mục đầu trang hoặc số
        if any(w in candidate for w in ["MỤC LỤC", "DANH MỤC", "PHỤ LỤC"]):
            continue

        # Validate: trong 400 ký tự sau heading phải có ĐẠI CƯƠNG hoặc (English)
        end_idx = m.end()
        window = text[end_idx: end_idx + 400]
        if RE_DISEASE_CONFIRM.search(window):
            last_disease = candidate

    return last_disease


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def extract_pages(
    pdf_path: str,
    skip_start: int = 7,
    skip_end_marker: str = "TÀI LIỆU THAM KHẢO",
) -> list[PageBlock]:
    """
    Đọc PDF, skip phần đầu (bìa+TOC+abbr) và phần cuối (references),
    trả về list PageBlock đã clean + có metadata chapter/disease (carry-over).
    """
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    print(f"[Preprocess] Total pages: {total}")

    # Tìm trang bắt đầu references
    end_page = total
    for i in range(total):
        page_text = reader.pages[i].extract_text() or ""
        if skip_end_marker in page_text:
            end_page = i
            print(f"[Preprocess] Found '{skip_end_marker}' at page {i+1} → cắt từ trang {end_page+1}")
            break

    print(f"[Preprocess] Sẽ xử lý trang {skip_start+1} → {end_page} ({end_page - skip_start} trang)")

    pages: list[PageBlock] = []
    current_chapter = ""
    current_disease = ""
    skipped_low_alpha = 0
    skipped_short = 0

    for i in range(skip_start, end_page):
        raw = reader.pages[i].extract_text() or ""
        cleaned = clean_page_text(raw)

        # Bỏ trang quá ngắn
        if len(cleaned) < 100:
            skipped_short += 1
            continue

        # Bỏ trang có quá ít chữ cái (sơ đồ, bảng vỡ)
        if alpha_ratio(cleaned) < MIN_ALPHA_RATIO:
            skipped_low_alpha += 1
            continue

        # Update chapter/disease carry-over
        ch = find_chapter(cleaned)
        if ch:
            current_chapter = ch
        ds = find_disease(cleaned)
        if ds:
            current_disease = ds

        pages.append(
            PageBlock(
                page_number=i + 1,
                text=cleaned,
                chapter=current_chapter,
                disease=current_disease,
            )
        )

    print(f"[Preprocess] Trang giữ lại: {len(pages)}")
    print(f"[Preprocess] Bỏ do quá ngắn (<100 char): {skipped_short}")
    print(f"[Preprocess] Bỏ do alpha_ratio thấp (sơ đồ/bảng vỡ): {skipped_low_alpha}")
    return pages


def chunk_pages(
    pages: list[PageBlock],
    source_file: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    Chunk theo từng "phân đoạn bệnh" — gộp các trang có cùng disease,
    rồi split bằng RecursiveCharacterTextSplitter để giữ ngữ cảnh.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # Gộp theo disease (consecutive pages với cùng disease → 1 segment)
    segments: list[tuple[list[PageBlock], str, str]] = []
    cur_pages: list[PageBlock] = []
    cur_disease = None
    cur_chapter = None

    for p in pages:
        if p.disease != cur_disease and cur_pages:
            segments.append((cur_pages, cur_chapter or "", cur_disease or ""))
            cur_pages = []
        cur_pages.append(p)
        cur_disease = p.disease
        cur_chapter = p.chapter

    if cur_pages:
        segments.append((cur_pages, cur_chapter or "", cur_disease or ""))

    print(f"[Chunk] Số 'segment bệnh': {len(segments)}")

    chunks: list[Chunk] = []
    seen_ids: set[str] = set()
    global_idx = 0

    for seg_pages, chapter, disease in segments:
        # Gộp text các trang trong cùng segment
        full_text = "\n\n".join(p.text for p in seg_pages)
        page_start = seg_pages[0].page_number

        parts = splitter.split_text(full_text)

        for local_idx, part in enumerate(parts):
            content = part.strip()
            if len(content) < MIN_CHUNK_CHARS:
                continue

            cid = hash_content(content)
            if cid in seen_ids:
                continue
            seen_ids.add(cid)

            chunks.append(
                Chunk(
                    id=cid,
                    content=content,
                    source_file=source_file,
                    page_number=page_start,
                    chapter=chapter,
                    disease=disease,
                    chunk_index=global_idx,
                )
            )
            global_idx += 1

    print(f"[Chunk] Tổng chunks tạo ra: {len(chunks)}")
    return chunks


def save_jsonl(chunks: list[Chunk], output_path: str) -> None:
    """Ghi chunks ra file JSONL (1 chunk / line, UTF-8)."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    print(f"[Save] Đã ghi {len(chunks)} chunks → {output_path}")


def print_stats(chunks: list[Chunk]) -> None:
    """In thống kê để user review trước khi ingest."""
    if not chunks:
        return
    diseases = {}
    chapters = {}
    for c in chunks:
        diseases[c.disease] = diseases.get(c.disease, 0) + 1
        chapters[c.chapter] = chapters.get(c.chapter, 0) + 1

    print("\n" + "=" * 60)
    print("THỐNG KÊ CHUNKS")
    print("=" * 60)
    print(f"Tổng chunks  : {len(chunks)}")
    print(f"Số chương    : {len([c for c in chapters if c])}")
    print(f"Số bệnh phát hiện: {len([d for d in diseases if d])}")
    avg_len = sum(len(c.content) for c in chunks) // len(chunks)
    print(f"Độ dài chunk TB: {avg_len} chars")

    print("\nChunks theo chương:")
    for ch, n in sorted(chapters.items(), key=lambda x: -x[1]):
        label = ch if ch else "(không xác định)"
        print(f"  {n:4d}  {label[:80]}")

    print("\nTop 10 bệnh có nhiều chunks nhất:")
    for d, n in sorted(diseases.items(), key=lambda x: -x[1])[:10]:
        label = d if d else "(không xác định)"
        print(f"  {n:4d}  {label}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preprocess PDF y tế → JSONL chunks")
    parser.add_argument("--pdf", required=True, help="Đường dẫn file PDF")
    parser.add_argument(
        "--output",
        default="data/processed/derma_chunks.jsonl",
        help="File JSONL đầu ra",
    )
    parser.add_argument(
        "--skip-start",
        type=int,
        default=7,
        help="Số trang đầu cần bỏ (mặc định 7 = bìa+TOC+abbr)",
    )
    parser.add_argument(
        "--skip-end-marker",
        default="TÀI LIỆU THAM KHẢO",
        help="Chuỗi đánh dấu bắt đầu phần references",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=CHUNK_OVERLAP,
    )
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        print(f"ERROR: file không tồn tại: {args.pdf}")
        sys.exit(1)

    source_file = os.path.basename(args.pdf)

    pages = extract_pages(
        args.pdf,
        skip_start=args.skip_start,
        skip_end_marker=args.skip_end_marker,
    )

    chunks = chunk_pages(
        pages,
        source_file=source_file,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    save_jsonl(chunks, args.output)
    print_stats(chunks)
    print("\n✅ Hoàn tất. Review file JSONL trước khi chạy ingest.")
