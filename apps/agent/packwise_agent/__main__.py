from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .http_api import make_server
from .llm import OpenAICompatibleChatClient
from .service import AgentService
from .ftbquests import inspect_quest_book
from .static_inspector import inspect_instance


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "inspect":
        _run_inspect(argv[1:])
        return
    if argv and argv[0] == "inspect-quests":
        _run_inspect_quests(argv[1:])
        return
    if argv and argv[0] == "serve":
        argv = argv[1:]

    parser = argparse.ArgumentParser(description="Run the Packwise lightweight agent service.")
    parser.add_argument("--host", default=os.environ.get("PACKWISE_AGENT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PACKWISE_AGENT_PORT", "8765")))
    parser.add_argument("--model", default=os.environ.get("PACKWISE_LLM_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--enable-llm", action="store_true", help="Call the configured OpenAI-compatible LLM provider.")
    args = parser.parse_args(argv)

    chat_client = OpenAICompatibleChatClient(model=args.model) if args.enable_llm else None
    service = AgentService(model_name=args.model, chat_client=chat_client)
    server = make_server((args.host, args.port), service)
    print(f"Packwise agent listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping Packwise agent")
    finally:
        server.server_close()


def _run_inspect(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Inspect an installed modpack directory without starting Minecraft.")
    parser.add_argument("path")
    parser.add_argument("--output", "-o", help="Write JSON summary to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    summary = inspect_instance(args.path)
    indent = 2 if args.pretty else None
    text = json.dumps(summary, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)


def _run_inspect_quests(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Inspect FTB Quests SNBT without starting Minecraft.")
    parser.add_argument("path", help="Installed instance directory or config/ftbquests/quests directory.")
    parser.add_argument("--output", "-o", help="Write JSON quest skeleton to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    summary = inspect_quest_book(args.path)
    indent = 2 if args.pretty else None
    text = json.dumps(summary, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
