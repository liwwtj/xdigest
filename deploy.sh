#!/bin/bash
# VPS 部署脚本

set -e

echo "🚀 开始部署 Twitter AI Digest..."

# 1. 安装系统依赖
echo "📦 安装系统依赖..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# 2. 创建项目目录
PROJECT_DIR="$HOME/twitter_ai_digest"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 3. 创建虚拟环境
echo "🐍 创建虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# 4. 安装依赖
echo "📥 安装 Python 依赖..."
pip install --no-cache-dir pyyaml requests twikit

# 5. 设置定时任务 (每天早上8点运行)
echo "⏰ 配置定时任务..."
CRON_CMD="0 8 * * * cd $PROJECT_DIR && ./run.sh >> logs/cron.log 2>&1"
(crontab -l 2>/dev/null | grep -v "twitter_ai_digest"; echo "$CRON_CMD") | crontab -

echo "✅ 部署完成!"
echo ""
echo "📋 后续步骤:"
echo "1. 编辑 config.yaml 配置 LLM API 和邮箱"
echo "2. 上传 cookies.json (Twitter登录凭证)"
echo "3. 测试: ./run.sh --test"
echo "4. 查看日志: tail -f logs/digest.log"
