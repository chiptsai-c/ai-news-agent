"""Measure how fast the local model reads (prompt) and writes (generation) on this machine."""
import sys
import time

import yaml

from agent.llm import LLM

cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
model = sys.argv[1] if len(sys.argv) > 1 else cfg["model"]
llm = LLM(cfg["ollama_url"], model, cfg["num_thread"], cfg["num_ctx"])

print(f"Model: {model}")
t = time.time()
llm.chat("Reply with OK.", "OK?", max_tokens=5)
print(f"Load + warm-up: {time.time() - t:.1f}s")

article = ("OpenAI announced a new model today that improves reasoning benchmarks by 12 percent "
           "while cutting inference cost in half. The company said it will roll out to all users next week. ") * 25
llm.stats = {k: 0 for k in llm.stats}
t = time.time()
out = llm.chat("Summarise the article in 3 bullet points.", article, max_tokens=150)
print(f"Summary call: {time.time() - t:.1f}s  |  {llm.speed()}")
print(out)
