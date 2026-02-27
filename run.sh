#!/bin/bash
# 运行脚本
cd "$(dirname "$0")"
source venv/bin/activate
python3 main.py "$@"
