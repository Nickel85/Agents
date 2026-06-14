"""Fixture LLM provider used by Njord runtime validation."""

from __future__ import annotations

import argparse
import json
import sys
import time


parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("echo", "sleep"), default="echo")
parser.add_argument("--system", default="")
args = parser.parse_args()

prompt = sys.stdin.read()
if args.mode == "sleep":
    time.sleep(2)

content = "saw emoji" if "🐶" in prompt else "saw prompt"
print(
    json.dumps(
        {
            "ok": True,
            "profile": "fixture",
            "response": {"content": content},
        }
    )
)
