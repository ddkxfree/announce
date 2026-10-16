#!/bin/bash
set -u
f=/app/greeting.txt
if [ ! -f "$f" ]; then
  echo "FAIL: $f does not exist"
  exit 1
fi
# tolerate a single trailing newline, nothing else
content=$(cat "$f")
if [ "$content" != "Hello, harness!" ]; then
  echo "FAIL: unexpected content: $(head -c 200 "$f" | od -c | head -5)"
  exit 1
fi
if [ "$(wc -l < "$f")" -gt 1 ]; then
  echo "FAIL: file has more than one line"
  exit 1
fi
echo "PASS"
