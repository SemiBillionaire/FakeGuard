"""
@brief Prototype runner cho LangGraph voi cac node that.
@details Cho phep chay tung moc: extract, retrieve, judge, web hoac full de debug dan.

Yeu cau tuy theo stage:
  - extract: GROQ_API_KEY
  - retrieve: GROQ_API_KEY + database/embedding config
  - judge: GROQ_API_KEY + database/embedding config
  - web/full: GROQ_API_KEY + database/embedding config + TAVILY_API_KEY neu can search web

Chay vi du:
  cd backend
  python -X utf8 test_graph_with_real_services.py --stage extract
  python -X utf8 test_graph_with_real_services.py --stage full --text "Daniil Medvedev giành chức vô địch ATP Monte Carlo 2026."
"""

import argparse
import asyncio
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.graph import build_graph


SAMPLE_TEXT = """
Lebron James thông báo giải nghệ sau trận thua OKC ở game 4 playoff mùa giải 2026.
"""

INTERRUPT_BY_STAGE = {
    "extract": ["extract"],
    "retrieve": ["retrieve_internal"],
    "judge": ["judge_internal"],
    "web": ["judge_after_web"],
    "full": None,
}


def build_initial_state(text: str) -> dict[str, Any]:
    """
    @brief Tao AgentState ban dau cho prototype graph.
    """
    return {
        "messages": [],
        "user_input": text,
        "article_text": None,
        "summary": None,
        "category": None,
        "global_entities": [],
        "sub_claims": [],
        "current_idx": 0,
        "web_evidence": [],
        "kb_evidence": [],
        "final_verdict": None,
        "confidence": None,
        "explanation": None,
        "sources": [],
        "llm_calls": 0,
        "tavily_calls": 0,
    }


def parse_args() -> argparse.Namespace:
    """
    @brief Parse CLI args cho prototype runner.
    """
    parser = argparse.ArgumentParser(description="Run real LangGraph prototype by stage.")
    parser.add_argument(
        "--stage",
        choices=sorted(INTERRUPT_BY_STAGE.keys()),
        default="extract",
        help="Moc graph can chay. Mac dinh: extract.",
    )
    parser.add_argument("--text", help="Doan van can kiem chung.")
    parser.add_argument("--file", help="File text dau vao, uu tien hon --text neu co.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="In toan bo state JSON thay vi ban tom tat ngan.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="In them sub-claims va evidence rut gon de debug.",
    )
    return parser.parse_args()


def read_input_text(args: argparse.Namespace) -> str:
    """
    @brief Lay input tu --file, --text hoac sample mac dinh.
    """
    if args.file:
        return Path(args.file).read_text(encoding="utf-8").strip()
    if args.text:
        return args.text.strip()
    return SAMPLE_TEXT.strip()


def print_result(result: dict[str, Any], stage: str, debug: bool = False) -> None:
    """
    @brief In output gon cho prototype, chi mo rong chi tiet khi --debug.
    """
    print("=" * 72)
    print(f"KẾT QUẢ KIỂM CHỨNG - {stage.upper()}")
    print("=" * 72)
    print(f"Tóm tắt: {result.get('summary') or 'N/A'}")
    print(f"Kết luận: {result.get('final_verdict') or 'N/A'}")
    print(f"Độ tin cậy: {result.get('confidence') if result.get('confidence') is not None else 'N/A'}")
    print(f"Phân loại: {result.get('category') or 'N/A'}")
    print(f"Số API đã dùng: LLM={result.get('llm_calls', 0)}, Tavily={result.get('tavily_calls', 0)}")

    if result.get("explanation"):
        print("\nGiải thích:")
        print(result["explanation"])

    print("\nCác luận điểm:")
    for idx, claim in enumerate(result.get("sub_claims", []), 1):
        verdict = claim.get("verdict") or "N/A"
        confidence = claim.get("confidence")
        confidence_text = confidence if confidence is not None else "N/A"
        print(f"{idx}. [{verdict} | {confidence_text}] {claim.get('claim')}")
        if claim.get("reasoning"):
            print(f"   Lý do: {claim.get('reasoning')}")

        if debug:
            print(f"   Entities: {claim.get('entities', [])} | Time refs: {claim.get('time_refs', [])}")
            evidence = (claim.get("evidence") or []) or (claim.get("web_evidence") or [])[:2] or (claim.get("kb_evidence") or [])[:2]
            for source in evidence[:2]:
                print(f"   Nguồn phụ: {source.get('title', '')} | {source.get('url', '')}")

    sources = result.get("sources") or []
    print("\nBài báo liên quan:")
    if sources:
        for source in sources:
            print(f"- {source.get('title')} | {source.get('url')}")
    else:
        print("- Chưa có nguồn được chọn.")


def format_error(exc: Exception) -> str:
    """
    @brief Rút gọn lỗi runtime để terminal prototype không hiện stack trace dài.
    """
    message = str(exc).replace("\n", " ").strip()
    if "rate_limit" in message.lower() or "rate limit" in message.lower():
        marker = "Please try again in"
        if marker in message:
            retry_after = message.split(marker, 1)[1].split(".", 1)[0].strip()
            return f"Rate limit từ LLM API. Thử lại sau khoảng {retry_after}."
        return "Rate limit từ LLM API. Thử lại sau hoặc đổi model/key."
    return f"{type(exc).__name__}: {message[:300]}"


async def main() -> None:
    """
    @brief Chay graph that theo stage da chon va in output.
    """
    args = parse_args()
    text = read_input_text(args)

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("Thieu GROQ_API_KEY trong backend/.env")

    graph = build_graph(interrupt_after=INTERRUPT_BY_STAGE[args.stage])
    try:
        if args.debug:
            result = await graph.ainvoke(build_initial_state(text))
        else:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = await graph.ainvoke(build_initial_state(text))
    except Exception as exc:
        if args.debug:
            raise
        print("=" * 72)
        print("KHÔNG CHẠY ĐƯỢC PROTOTYPE")
        print("=" * 72)
        print(format_error(exc))
        raise SystemExit(1) from None

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_result(result, args.stage, debug=args.debug)


if __name__ == "__main__":
    asyncio.run(main())
