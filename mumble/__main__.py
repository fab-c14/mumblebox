import argparse
from pathlib import Path

from mumble.box import morning, nap, undo
from mumble.ollama import OllamaModel


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mumblebox",
        description="Rewrite the notes you are avoiding. The model stays on this machine.",
    )
    parser.add_argument("command", choices=("nap", "morning", "undo"))
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--model", default="gemma2:2b")
    parser.add_argument("--limit", default=3, type=int)
    args = parser.parse_args(argv)
    root = args.root

    if args.command == "morning":
        print(morning(root))
        return 0
    if args.command == "undo":
        restored = undo(root)
        if restored:
            print("Put back: " + ", ".join(restored))
        else:
            print("Nothing to put back.")
        return 0

    result = nap(root, OllamaModel(model=args.model), limit=args.limit)
    for name in result["ready"]:
        print(f"ready   {name}")
    for name in result["asleep"]:
        print(f"asleep  {name}")
    for name in result["skipped"]:
        print(f"skipped {name}")
    for name in result["left"]:
        print(f"later   {name}")
    print()
    print(morning(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
