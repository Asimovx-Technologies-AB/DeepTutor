import asyncio
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.rag.graph_rag import graph_rag

async def main():
    print("Testing query_stream with out-of-scope query 'messi'...")
    tokens = ""
    async for evt_line in graph_rag.query_stream(
        topic_id="general",
        question="messi",
        session_messages=[
            {"role": "user", "content": "Explain Naive Bayes"},
            {"role": "assistant", "content": "Explanation of Naive Bayes: Naive Bayes is a classifier..."}
        ]
    ):
        if evt_line.startswith("data: "):
            try:
                data = json.loads(evt_line[6:])
                if data.get("type") == "token":
                    tokens += data.get("data", "")
            except Exception:
                pass

    print("\n--- Streamed Response ---")
    print(tokens)
    print("-------------------------\n")

if __name__ == "__main__":
    asyncio.run(main())
