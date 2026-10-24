import argparse
from pathlib import Path

from mumble.box import morning, nap, undo
from mumble.desk import serve
from mumble.ollama import OllamaModel


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mumblebox",
        description="Three different replies for the message you will not send. The model stays on this machine.",
    )
    parser.add_argument("command", choices=("desk", "nap", "morning", "undo"))
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--model", default="gemma2:2b")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args(argv)

    if args.command == "desk":
        serve(port=args.port, model=args.model)
        return 0
    if args.command == "morning":
        print(morning(args.root))
        return 0
    if args.command == "undo":
        restored = undo(args.root)
        if restored:
            print("Put back: " + ", ".join(restored))
        else:
            print("Nothing to put back.")
        return 0

    result = nap(args.root, OllamaModel(model=args.model))
    if result.get("error"):
        print(f"skipped {result['skipped'][0]}  {result['error']}")
    for name in result["ready"]:
        print(f"ready   {name}")
    for name in result["asleep"]:
        print(f"asleep  {name}")
    for name in result["left"]:
        print(f"later   {name}")
    print()
    print(morning(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
