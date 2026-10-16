#!/bin/bash
sed -i 's|return total / (len(values) - 1)|return total / len(values)|' /app/stats.py
