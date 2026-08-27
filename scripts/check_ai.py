#!/usr/bin/env python3
"""Check the Gemini key and list the vision models it can use."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai  # noqa: E402


def main():
    if not ai.available():
        print("GEMINI_API_KEY is not set.")
        print("Get a free key at https://aistudio.google.com/apikey, then:")
        print('  export GEMINI_API_KEY="..."')
        return 1

    print(f"Key found. Configured model: {ai.MODEL}\n")

    try:
        models = ai.list_models()
    except Exception as exc:
        print(f"Could not list models: {exc}")
        return 1

    usable = [
        m for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    names = [m["name"].removeprefix("models/") for m in usable]

    print("Models this key can call:")
    for name in sorted(names):
        marker = "  <- currently configured" if name == ai.MODEL else ""
        print(f"  {name}{marker}")

    if ai.MODEL not in names:
        print(f"\nWARNING: '{ai.MODEL}' is not in that list.")
        print("Pick one above and set it:  export GEMINI_MODEL='<name>'")
        return 1

    print("\nRunning a live test call...")
    try:
        result = ai._call([{"text": 'Reply with exactly {"ok": true}'}])
        print(f"OK — model responded: {result}")
    except Exception as exc:
        print(f"Test call failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
