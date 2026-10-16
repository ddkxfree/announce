import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

rng = random.Random(1234)
messages = {
    "INFO": [
        "request served in {n}ms",
        "user {n} logged in",
        "retry succeeded after ERROR from upstream {n}",
        "cache warmed with {n} entries",
    ],
    "WARN": [
        "slow query took {n}ms",
        "ERROR budget at {n}% for this hour",
        "disk usage at {n}%",
    ],
    "ERROR": [
        "database connection lost (attempt {n})",
        "failed to parse payload {n}",
        "timeout calling payment service after {n}ms",
    ],
}
levels = ["INFO"] * 6 + ["WARN"] * 3 + ["ERROR"] * 2

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
t = datetime(2026, 1, 1, 8, 0, 0)
lines = []
for _ in range(500):
    t += timedelta(seconds=rng.randint(1, 30))
    level = rng.choice(levels)
    msg = rng.choice(messages[level]).format(n=rng.randint(1, 999))
    lines.append(f"{t.isoformat()} {level} {msg}")
out.write_text("\n".join(lines) + "\n")
