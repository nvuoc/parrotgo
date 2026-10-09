# -*- coding: utf-8 -*-
"""
Script tổng hợp tất cả các file markdown trong dự án ParrotGo thành một file duy nhất: FULL_DOCUMENTATION.md
Bao gồm:
- Toàn bộ 11 tài liệu kiến trúc, đồ thị, nghiệp vụ ở thư mục gốc
- 3 báo cáo kiểm thử, tối ưu và sửa lỗi trong reports/
- Tự động chuẩn hóa anchor link, bảng mục lục liên kết và cấu trúc phân cấp markdown chuẩn.
"""

import os
import re
import sys
import pathlib

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "FULL_DOCUMENTATION.md"

DOCUMENT_SPECS = [
    {
        "file": "README.md",
        "anchor": "readme-md",
        "part_num": "1",
        "title": "TỔNG QUAN DỰ ÁN & HƯỚNG DẪN KHỞI CHẠY",
        "source": "README.md",
        "role": "Giới thiệu tổng quan hệ thống ParrotGo MVP CLI, kiến trúc 8 nodes & 3 conditional edges, cấu trúc mã nguồn và hướng dẫn cài đặt / khởi chạy nhanh.",
        "skip_first_h1": True,
    },
    {
        "file": "system.md",
        "anchor": "system-md",
        "part_num": "2",
        "title": "THIẾT KẾ HỆ THỐNG TỔNG THỂ",
        "source": "system.md",
        "role": "Kiến trúc hệ thống tổng đài thoại thông minh toàn diện: Voice Gateway SIP/VoIP, LiveKit WebRTC, Whisper ASR, TTS, LLM Orchestration và cơ chế Human Handoff.",
        "skip_first_h1": True,
    },
    {
        "file": "architecture.md",
        "anchor": "architecture-md",
        "part_num": "3",
        "title": "KIẾN TRÚC KỸ THUẬT MVP CLI & CONTRACTS",
        "source": "architecture.md",
        "role": "Ranh giới giao tiếp ASR → Core → TTS, cấu trúc cuốc xe (booking slots), bất biến state, điều kiện ready_to_book và schema chuẩn dùng chung.",
        "skip_first_h1": True,
    },
    {
        "file": "langgraph.md",
        "anchor": "langgraph-md",
        "part_num": "4",
        "title": "ĐỒ THỊ ĐIỀU PHỐI LANGGRAPH",
        "source": "langgraph.md",
        "role": "Thiết kế topology 8 nodes và 3 conditional edges của LangGraph, pseudocode chi tiết cho từng node xử lý lượt thoại đặt xe taxi.",
        "skip_first_h1": True,
    },
    {
        "file": "planner.md",
        "anchor": "planner-md",
        "part_num": "5",
        "title": "BỘ ĐIỀU PHỐI PLANNER, REDUCER VÀ LỜI THOẠI",
        "source": "planner.md",
        "role": "Vòng đời slot, quy tắc Reducer không suy diễn, Policy ra quyết định action, và ngân hàng lời thoại chuẩn (Voice Dialog Templates).",
        "skip_first_h1": True,
    },
    {
        "file": "extractor.md",
        "anchor": "extractor-md",
        "part_num": "6",
        "title": "BỘ TRÍCH XUẤT EXTRACTOR & NLU TỪ VĂN BẢN ASR",
        "source": "extractor.md",
        "role": "Đặc tả NLU bóc tách intent, slot, operation; xử lý lỗi ASR, tiếng ồn, từ lóng và ma trận 12 tình huống NLU tiêu biểu.",
        "skip_first_h1": True,
    },
    {
        "file": "map.md",
        "anchor": "map-md",
        "part_num": "7",
        "title": "DỊCH VỤ BẢN ĐỒ MAP SERVICE & ĐỊA DANH",
        "source": "map.md",
        "role": "Tích hợp Vietmap API, chuẩn hóa địa danh, xử lý ngõ hẻm, alias địa phương, điểm đón/trả và ma trận 17 tình huống xử lý địa lý.",
        "skip_first_h1": True,
    },
    {
        "file": "ask.md",
        "anchor": "ask-md",
        "part_num": "8",
        "title": "XỬ LÝ HỎI ĐÁP Q&A, FAQ/RAG VÀ TRA CỨU PHIÊN",
        "source": "ask.md",
        "role": "Xử lý câu hỏi ngoài lề gồm 3 nhóm: FAQ tĩnh qua Chroma RAG, tools động tính giá/quãng đường, và State Inspector tra cứu chuyến đi.",
        "skip_first_h1": True,
    },
    {
        "file": "rag.md",
        "anchor": "rag-md",
        "part_num": "9",
        "title": "CƠ SỞ TRI THỨC NGHIỆP VỤ — ĐẶT XE QUA TỔNG ĐÀI XANH SM",
        "source": "rag.md",
        "role": "Tập tri thức nghiệp vụ dịch vụ đặt xe taxi (loại xe, giá cước, điểm đón/trả, đặt hộ/trước, biểu phí, hành lý thất lạc, khiếu nại).",
        "skip_first_h1": True,
    },
    {
        "file": "database.md",
        "anchor": "database-md",
        "part_num": "10",
        "title": "LƯU TRỮ, QUẢN TRỊ DỮ LIỆU & VECTOR DB",
        "source": "database.md",
        "role": "Kiến trúc lưu trữ 3 tầng: State runtime, Persistent SQLite 6 bảng, Vector DB Chroma và quy trình nạp seed data địa danh / FAQ.",
        "skip_first_h1": True,
    },
    {
        "file": "plan.md",
        "anchor": "plan-md",
        "part_num": "11",
        "title": "KẾ HOẠCH & LỘ TRÌNH TRIỂN KHAI MVP CLI",
        "source": "plan.md",
        "role": "Kế hoạch hành động 4 giai đoạn triển khai mã nguồn, cấu trúc module và bộ tiêu chí nghiệm thu acceptance criteria.",
        "skip_first_h1": True,
    },
    {
        "file": "reports/demo-risk-audit-2026-10-07.md",
        "anchor": "demo-risk-audit-2026-10-07-md",
        "part_num": "12.1",
        "title": "BÁO CÁO RÀ SOÁT RỦI RO DEMO PARROTGO (07/10/2026)",
        "source": "reports/demo-risk-audit-2026-10-07.md",
        "role": "Báo cáo kiểm thử rà soát rủi ro kịch bản demo: địa chỉ, mock fallback, ngữ cảnh NLU, xử lý thời gian tự nhiên.",
        "skip_first_h1": True,
    },
    {
        "file": "reports/demo-optimization-2026-10-08.md",
        "anchor": "demo-optimization-2026-10-08-md",
        "part_num": "12.2",
        "title": "KẾT QUẢ BỔ SUNG DỮ LIỆU & TỐI ƯU DEMO (08/10/2026)",
        "source": "reports/demo-optimization-2026-10-08.md",
        "role": "Kết quả bổ sung dữ liệu địa danh bền vững, nạp FAQ Chroma và tối ưu tỷ lệ pass test suite.",
        "skip_first_h1": False,
    },
    {
        "file": "reports/clarification-ux-fix-2026-10-08.md",
        "anchor": "clarification-ux-fix-2026-10-08-md",
        "part_num": "12.3",
        "title": "SỬA TRẢI NGHIỆM LÀM RÕ ĐỊA ĐIỂM (08/10/2026)",
        "source": "reports/clarification-ux-fix-2026-10-08.md",
        "role": "Tối ưu câu hỏi làm rõ địa điểm ngắn gọn, giảm độ dài đọc thoại và tránh bẫy câu hỏi A/B sai ngữ cảnh.",
        "skip_first_h1": False,
    },
]

LINK_REPLACEMENTS = {
    "./architecture.md": "#architecture-md",
    "./ask.md": "#ask-md",
    "./database.md": "#database-md",
    "./extractor.md": "#extractor-md",
    "./langgraph.md": "#langgraph-md",
    "./map.md": "#map-md",
    "./plan.md": "#plan-md",
    "./planner.md": "#planner-md",
    "./rag.md": "#rag-md",
    "./system.md": "#system-md",
    "./README.md": "#readme-md",
    "../README.md": "#readme-md",
    "reports/demo-optimization-2026-10-08.md": "#demo-optimization-2026-10-08-md",
    "reports/clarification-ux-fix-2026-10-08.md": "#clarification-ux-fix-2026-10-08-md",
    "reports/demo-risk-audit-2026-10-07.md": "#demo-risk-audit-2026-10-07-md",
    "clarification-ux-fix-2026-10-08.md": "#clarification-ux-fix-2026-10-08-md",
    "../map.md#1-ranh-giới-và-nguyên-tắc": "#map-md",
    "../planner.md#5-ngân-hàng-lời-thoại": "#planner-md",
}


def rewrite_links(text: str) -> str:
    for old_link, new_anchor in LINK_REPLACEMENTS.items():
        # Match markdown links: [text](old_link)
        pattern = re.compile(rf'\[([^\]]+)\]\({re.escape(old_link)}\)')
        text = pattern.sub(rf'[\1]({new_anchor})', text)
    return text


def process_section_content(filepath: pathlib.Path, skip_first_h1: bool = True) -> str:
    content = filepath.read_text(encoding="utf-8")
    content = rewrite_links(content)
    lines = content.splitlines()

    new_lines = []
    in_code = False
    first_h1_skipped = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            new_lines.append(line)
            continue

        if not in_code and line.startswith("#"):
            m = re.match(r"^(#+)(\s+.*)$", line)
            if m:
                hashes, rest = m.groups()
                # If this is the very first H1 (# ...), skip it because section header already covers it
                if len(hashes) == 1 and skip_first_h1 and not first_h1_skipped:
                    first_h1_skipped = True
                    continue
                # Shift headings by 1 level: ## -> ###, ### -> ####, etc.
                new_hashes = "#" * (len(hashes) + 1)
                new_lines.append(new_hashes + rest)
                continue

        new_lines.append(line)

    return "\n".join(new_lines).strip()


def extract_subheadings(filepath: pathlib.Path) -> list[str]:
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()
    subheadings = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if not in_code and line.startswith("## "):
            title = line[3:].strip()
            subheadings.append(title)
    return subheadings


def main():
    print(f"Bắt đầu tổng hợp tài liệu từ {len(DOCUMENT_SPECS)} file markdown...")

    output_parts = []

    # Title & Metadata
    output_parts.append(
        """# HỆ THỐNG TỔNG ĐÀI ĐẶT XE THÔNG MINH PARROTGO — TÀI LIỆU TOÀN DIỆN
*(ParrotGo: Smart Voice Taxi Booking System — Full Consolidated Documentation)*

---

> **Dự án:** ParrotGo (Voice AI Agent for Taxi Dispatching)  
> **Ngôn ngữ & Nền tảng:** Python 3.11+, LangGraph, ChromaDB, SQLite, Vietmap API, LiveKit / VoIP Gateway  
> **Mục đích tài liệu:** Tài liệu này hợp nhất toàn bộ tài liệu kiến trúc, đặc tả dữ liệu, đồ thị trạng thái, hướng dẫn vận hành và các báo cáo tối ưu của dự án ParrotGo thành một tài liệu duy nhất, phục vụ việc tra cứu, chuyển giao và lưu trữ kỹ thuật.

---

<a id="mục-lục-toàn-diện"></a>
## MỤC LỤC TOÀN DIỆN (TABLE OF CONTENTS)
"""
    )

    # Overview Table
    output_parts.append("### Bảng tóm tắt các phân hệ tài liệu\n")
    output_parts.append("| Phần | Tên phân hệ tài liệu | File nguồn | Vai trò chính |")
    output_parts.append("| :--- | :--- | :--- | :--- |")
    for spec in DOCUMENT_SPECS:
        part_str = f"Phần {spec['part_num']}"
        output_parts.append(
            f"| [{part_str}](#{spec['anchor']}) | [{spec['title']}](#{spec['anchor']}) | `{spec['source']}` | {spec['role']} |"
        )
    output_parts.append("\n---\n")

    # Detailed TOC with subheadings
    output_parts.append("### Danh mục chi tiết các đề mục\n")
    for spec in DOCUMENT_SPECS:
        fpath = BASE_DIR / spec["file"]
        output_parts.append(f"- **[Phần {spec['part_num']}: {spec['title']}](#{spec['anchor']})** (`{spec['source']}`)")
        subheadings = extract_subheadings(fpath)
        for sub in subheadings:
            output_parts.append(f"  - {sub}")

    output_parts.append("\n---\n")

    # Content for each section
    for idx, spec in enumerate(DOCUMENT_SPECS, 1):
        fpath = BASE_DIR / spec["file"]
        if not fpath.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {fpath}")

        print(f"Đang xử lý [{idx}/{len(DOCUMENT_SPECS)}]: {spec['file']}...")

        processed_body = process_section_content(fpath, skip_first_h1=spec["skip_first_h1"])

        section_text = f"""
---

<a id="{spec['anchor']}"></a>
## PHẦN {spec['part_num']}: {spec['title']}

> **Tập tin nguồn:** [`{spec['source']}`](file:///{str(fpath).replace(os.sep, '/')})  
> **Vai trò:** {spec['role']}

{processed_body}

[⬆ Quay lại mục lục toàn diện](#mục-lục-toàn-diện)
"""
        output_parts.append(section_text)

    # Write output file
    final_content = "\n".join(output_parts)
    OUTPUT_FILE.write_text(final_content, encoding="utf-8")
    print(f"Tổng hợp thành công vào: {OUTPUT_FILE}")
    print(f"Tổng số dòng: {len(final_content.splitlines())}")
    print(f"Dung lượng: {len(final_content.encode('utf-8')):,} bytes")


if __name__ == "__main__":
    main()
