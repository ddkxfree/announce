#!/bin/bash
set -u
expected=$(awk '$2 == "ERROR"' /app/logs/server.log | wc -l)
if [ ! -f /app/answer.txt ]; then
  echo "FAIL: /app/answer.txt does not exist"
  exit 1
fi
actual=$(tr -d '[:space:]' < /app/answer.txt)
if [ "$actual" != "$expected" ]; then
  echo "FAIL: expected $expected, got '$actual'"
  exit 1
fi
echo "PASS"
