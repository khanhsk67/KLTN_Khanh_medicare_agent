# -*- coding: utf-8 -*-
"""
Script kiểm tra agents theo 3 cấp độ:

  Level 1 — Import check     : không cần service nào
  Level 2 — Prompts + schema : không cần service nào
  Level 3 — Chatbot agent    : chỉ cần GOOGLE_API_KEY
  Level 4 — Full pipeline    : cần GOOGLE_API_KEY + PostgreSQL + Qdrant

Chạy:
  cd medical-rag/backend
  python scripts/test_agents.py          # chạy Level 1 + 2 + 3
  python scripts/test_agents.py --all    # chạy tất cả Level (cần services)
"""
import argparse
import asyncio
import sys
import traceback
from pathlib import Path

# Đảm bảo import được từ backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"
HEAD = "\033[93m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {PASS} {msg}")


def fail(msg: str, exc: Exception | None = None) -> None:
    print(f"  {FAIL} {msg}")
    if exc:
        print(f"         {exc}")


def heading(title: str) -> None:
    print(f"\n{HEAD}{'='*60}{RESET}")
    print(f"{HEAD}  {title}{RESET}")
    print(f"{HEAD}{'='*60}{RESET}")


# ---------------------------------------------------------------------------
# LEVEL 1 — Import check
# ---------------------------------------------------------------------------

def test_level1_imports() -> bool:
    heading("LEVEL 1 — Import check (không cần service)")
    passed = True

    modules = [
        ("app.core.config",               "settings"),
        ("app.core.prompts",              "IMAGE_ANALYSIS_PROMPT"),
        ("app.models.schemas",            "AgentState, ChatRequest, ChatResponse"),
        ("app.agents.image_medical_agent","analyze_image"),
        ("app.agents.rule_medical_agent", "retrieve_medical_rules"),
        ("app.agents.chatbot_agent",      "generate_response"),
        ("app.agents.orchestrator",       "run_medical_graph"),
        ("app.agents.treatment_analysis_agent", "analyze_treatment_history"),
        ("app.agents",                    "run_medical_graph, analyze_treatment_history"),
    ]

    for module, names in modules:
        try:
            mod = __import__(module, fromlist=names.split(","))
            for name in names.split(","):
                name = name.strip()
                if not hasattr(mod, name):
                    raise ImportError(f"'{name}' không tồn tại trong {module}")
            ok(f"import {module} ({names})")
        except Exception as exc:
            fail(f"import {module}", exc)
            passed = False

    return passed


# ---------------------------------------------------------------------------
# LEVEL 2 — Prompts & schema shape
# ---------------------------------------------------------------------------

def test_level2_prompts_and_schema() -> bool:
    heading("LEVEL 2 — Prompts & AgentState schema")
    passed = True

    # 2a. Kiểm tra 4 prompts không rỗng
    try:
        from app.core.prompts import (
            CHATBOT_RESPONSE_PROMPT,
            IMAGE_ANALYSIS_PROMPT,
            RULE_MEDICAL_SYSTEM_PROMPT,
            TREATMENT_ANALYSIS_PROMPT,
        )
        # 3 prompts yêu cầu output JSON, 1 prompt yêu cầu output Markdown
        checks = [
            ("IMAGE_ANALYSIS_PROMPT",      IMAGE_ANALYSIS_PROMPT,      "json"),
            ("RULE_MEDICAL_SYSTEM_PROMPT",  RULE_MEDICAL_SYSTEM_PROMPT, "json"),
            ("CHATBOT_RESPONSE_PROMPT",     CHATBOT_RESPONSE_PROMPT,    "markdown"),
            ("TREATMENT_ANALYSIS_PROMPT",   TREATMENT_ANALYSIS_PROMPT,  "json"),
        ]
        for name, val, expected_format in checks:
            assert len(val) > 50, f"{name} quá ngắn"
            if expected_format == "json":
                assert "JSON" in val, f"{name} thiếu hướng dẫn JSON"
            else:
                assert "Markdown" in val, f"{name} thiếu hướng dẫn Markdown"
            ok(f"{name} ({len(val)} chars, output={expected_format})")
    except Exception as exc:
        fail("Prompts", exc)
        passed = False

    # 2b. AgentState có đủ fields mới
    try:
        from app.models.schemas import AgentState
        required_keys = {
            "user_id", "session_id", "user_message",
            "image_base64", "image_mime_type", "image_analysis_result",
            "retrieved_chunks", "rag_context", "sources",
            "response", "message_id", "urgency_level", "treatment_data",
            "error",
        }
        annotations = AgentState.__annotations__
        missing = required_keys - set(annotations.keys())
        if missing:
            raise KeyError(f"AgentState thiếu fields: {missing}")
        ok(f"AgentState có đủ {len(annotations)} fields")
    except Exception as exc:
        fail("AgentState schema", exc)
        passed = False

    # 2c. ChatResponse shape
    try:
        from app.models.schemas import ChatResponse
        import uuid
        from datetime import datetime, timezone
        cr = ChatResponse(
            session_id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            content="test",
            sources=[],
            urgency_level=None,
            created_at=datetime.now(timezone.utc),
        )
        assert cr.role == "assistant"
        ok("ChatResponse tạo thành công")
    except Exception as exc:
        fail("ChatResponse", exc)
        passed = False

    return passed


# ---------------------------------------------------------------------------
# LEVEL 3 — Chatbot agent (chỉ cần GOOGLE_API_KEY)
# ---------------------------------------------------------------------------

async def test_level3_chatbot_agent() -> bool:
    heading("LEVEL 3 — Chatbot agent (cần GOOGLE_API_KEY)")
    passed = True

    try:
        from app.agents.chatbot_agent import generate_response
        from app.models.schemas import AgentState

        state: AgentState = {
            "user_id": "test-user",
            "session_id": None,
            "user_message": "Tôi bị đau đầu và sốt nhẹ, tôi nên làm gì?",
            "image_base64": None,
            "image_mime_type": "image/jpeg",
            "image_analysis_result": None,
            "retrieved_chunks": [],
            "rag_context": (
                "Đau đầu và sốt nhẹ thường gặp trong nhiều bệnh thông thường "
                "như cảm cúm, viêm mũi họng. Nghỉ ngơi, uống nhiều nước và "
                "theo dõi nhiệt độ. Nếu sốt trên 39°C hoặc kéo dài > 3 ngày, cần khám bác sĩ."
            ),
            "sources": [],
            "response": "",
            "message_id": None,
            "urgency_level": "routine",
            "treatment_data": {
                "symptoms": ["đau đầu", "sốt nhẹ"],
                "possible_conditions": ["Cảm cúm", "Viêm mũi họng"],
                "severity": "mild",
                "body_parts": ["đầu"],
                "recommended_specialty": "Nội khoa",
                "urgency": "routine",
                "immediate_actions": ["Nghỉ ngơi", "Uống nhiều nước"],
                "medications_mentioned": [],
                "lifestyle_advice": ["Theo dõi nhiệt độ"],
            },
            "error": None,
            "iterations": 0,
        }

        result = await generate_response(state)
        response = result.get("response", "")

        assert len(response) > 50, "Response quá ngắn"
        ok(f"Chatbot response OK ({len(response)} chars)")

        # In preview
        preview = response[:200].replace("\n", " ")
        print(f"\n  {INFO} Preview:\n  {preview}...\n")

    except Exception as exc:
        fail("Chatbot agent", exc)
        traceback.print_exc()
        passed = False

    return passed


# ---------------------------------------------------------------------------
# LEVEL 4 — Full pipeline (cần PostgreSQL + Qdrant + GOOGLE_API_KEY)
# ---------------------------------------------------------------------------

async def test_level4_full_pipeline() -> bool:
    heading("LEVEL 4 — Full pipeline (cần tất cả services)")
    passed = True

    # 4a. Qdrant connection
    try:
        from app.services.vector_store import qdrant_service
        collections = qdrant_service.client.get_collections()
        ok(f"Qdrant connected — {len(collections.collections)} collections")
    except Exception as exc:
        fail("Qdrant connection", exc)
        passed = False

    # 4b. PostgreSQL connection
    try:
        from sqlalchemy import text
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        ok("PostgreSQL connected")
    except Exception as exc:
        fail("PostgreSQL connection", exc)
        passed = False

    # 4c. Image agent với ảnh test (1x1 pixel JPEG)
    try:
        import base64
        # Ảnh JPEG 1x1 pixel trắng (smallest valid JPEG)
        tiny_jpeg_b64 = (
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
            "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
            "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
            "MjL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAA"
            "AAAAAAAAAAAAAP/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA"
            "/9oADAMBAAIRAxEAPwCwABmX/9k="
        )
        from app.agents.image_medical_agent import analyze_image
        from app.models.schemas import AgentState

        state: AgentState = {
            "user_id": "test",
            "session_id": None,
            "user_message": "test",
            "image_base64": tiny_jpeg_b64,
            "image_mime_type": "image/jpeg",
            "image_analysis_result": None,
            "retrieved_chunks": [],
            "rag_context": "",
            "sources": [],
            "response": "",
            "message_id": None,
            "urgency_level": None,
            "treatment_data": None,
            "error": None,
            "iterations": 0,
        }
        result = await analyze_image(state)
        img_result = result.get("image_analysis_result")
        assert img_result is not None, "image_analysis_result là None"
        ok(f"Image agent OK — severity={img_result.get('severity')}")
    except Exception as exc:
        fail("Image agent", exc)
        passed = False

    # 4d. RAG search
    try:
        from app.services.vector_store import qdrant_service
        chunks = await qdrant_service.search("đau đầu sốt", top_k=3)
        ok(f"RAG search OK — {len(chunks)} chunks trả về")
        if not chunks:
            print(f"  {INFO} Qdrant collection rỗng — cần chạy scripts/ingest_pdf.py trước")
    except Exception as exc:
        fail("RAG search", exc)
        passed = False

    return passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(run_all: bool) -> None:
    results: dict[str, bool] = {}

    results["Level 1 (imports)"] = test_level1_imports()
    results["Level 2 (prompts/schema)"] = test_level2_prompts_and_schema()

    # Level 3 cần GOOGLE_API_KEY
    try:
        results["Level 3 (chatbot agent)"] = await test_level3_chatbot_agent()
    except Exception as exc:
        results["Level 3 (chatbot agent)"] = False
        print(f"  {FAIL} Level 3 exception: {exc}")

    if run_all:
        try:
            results["Level 4 (full pipeline)"] = await test_level4_full_pipeline()
        except Exception as exc:
            results["Level 4 (full pipeline)"] = False
            print(f"  {FAIL} Level 4 exception: {exc}")

    # Summary
    heading("SUMMARY")
    all_passed = True
    for name, status in results.items():
        icon = PASS if status else FAIL
        print(f"  {icon} {name}")
        if not status:
            all_passed = False

    print()
    if all_passed:
        print(f"  {PASS} Tất cả tests PASSED\n")
    else:
        print(f"  {FAIL} Có tests FAILED — xem chi tiết ở trên\n")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kiểm tra AI agents")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Chạy Level 4 (cần PostgreSQL + Qdrant đang chạy)",
    )
    args = parser.parse_args()
    asyncio.run(main(run_all=args.all))
