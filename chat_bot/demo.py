"""End-to-end demo of the chat_bot package — no server, no front-end.

    cd chat_bot && python demo.py

Shows: RAG index build, public answers, a TM login by key, the two TM questions,
session persistence, and whether a local Llama is active (else rule-based).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chat_core import llm_available
from chat_core.router import handle_message
from chat_rag.seed_sim_data import main as seed


def _section(title):
    print("\n" + "=" * 64 + f"\n{title}\n" + "=" * 64)


def main():
    _section("0. (Re)generate simulated data + RAG indexes")
    seed()

    _section("LLM status")
    print("Local Llama (Ollama) available:", llm_available(),
          "→", "answers via Llama" if llm_available() else "answers via rule-based fallback")

    _section("1. PUBLIC mode")
    for q in ["What FIT classes are available?",
              "Any mini split classes in Nashville?",
              "Show me open airflow classes"]:
        print(f"\nQ: {q}\n{handle_message('demo-public', q)}")

    _section("2. TM mode (login with key, then ask)")
    print(handle_message("demo-tm", "", tm_key="NASH-DEMO-KEY"))
    for q in ["Show my dealers and their training history.",
              "Which dealers are behind on Level 1 in my territory?"]:
        print(f"\nQ: {q}\n{handle_message('demo-tm', q)}")

    _section("3. Bad key falls back to public")
    print(handle_message("demo-bad", "hi", tm_key="WRONG-KEY"))


if __name__ == "__main__":
    main()
