# Twitter AI Digest

抓取 AI 领域 Twitter 大佬推文，通过 LLM 生成中文日报摘要，邮件发送。

## 快速开始

### 1. 本地安装

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

编辑 `config.yaml`：

```yaml
llm:
  api_key: "your-anthropic-api-key"
  base_url: "https://api.anthropic.com"  # 或自定义代理地址
  model: "claude-haiku-4-5-20251001"

email:
  provider: "smtp"
  from_email: "your@qq.com"
  to_email: "your@qq.com"
  smtp_server: "smtp.qq.com"
  smtp_port: 587
  smtp_username: "your@qq.com"
  smtp_password: "your-authorization-code"  # QQ邮箱授权码

twitter:
  tweets_per_account: 5
  max_tweet_age_days: 7
  proxy: ""  # VPS不需要代理
```

### 3. 配置 Twitter Cookies

从浏览器导出 Twitter 登录 cookies 到 `cookies.json`

### 4. 运行

```bash
# 正常运行（抓取真实推文）
./run.sh

# 测试模式（使用模拟推文，测试完整流程）
./run.sh --test
```

## VPS 部署 (Debian)

需要 Python 3.10+（twikit 依赖）

```bash
# 1. 安装 pyenv
curl https://pyenv.run | bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
source ~/.bashrc

# 2. 安装 Python 3.10
pyenv install 3.10.13

# 3. 上传项目文件
scp -r twitter_ai_digest user@vps:~/

# 4. 在 VPS 上配置
cd ~/twitter_ai_digest
pyenv local 3.10.13
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. 测试
./run.sh --test
```

## 定时任务

```bash
crontab -e
# 每天早上 8 点运行 (UTC 时间，北京时间 16:00)
0 8 * * * cd /home/youruser/twitter_ai_digest && ./venv/bin/python main.py >> logs/cron.log 2>&1
```

## 文件结构

```
├── main.py              # 主程序入口
├── twitter_fetcher.py   # Twitter 推文抓取
├── llm_summarizer.py    # LLM 摘要生成
├── email_sender.py      # 邮件发送
├── config.yaml          # 配置文件
├── accounts.yaml        # 监控的 Twitter 账号列表
├── cookies.json         # Twitter 登录凭证（需自行从浏览器导出，不含在仓库中）
├── run.sh               # 运行脚本
├── logs/                # 日志目录
└── output/              # 生成的摘要文件
```

## License

MIT
