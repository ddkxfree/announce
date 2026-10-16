#!/bin/bash
awk '$2 == "ERROR"' /app/logs/server.log | wc -l > /app/answer.txt
