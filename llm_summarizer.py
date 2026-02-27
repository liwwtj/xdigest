"""
LLM 总结模块
调用 Anthropic Messages API 对推文进行智能总结
"""

import os
import anthropic
import re
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


class LLMSummarizer:
    """LLM 总结器"""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = "claude-haiku-4-5-20251001", **kwargs):
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN"),
            base_url=base_url or os.environ.get("ANTHROPIC_BASE_URL"),
        )
        self.model = model
    
    def create_prompt(self, tweets: List[Dict]) -> str:
        """构建提示词"""
        # 按用户分组推文
        tweets_by_user = {}
        for tweet in tweets:
            username = tweet['username']
            if username not in tweets_by_user:
                tweets_by_user[username] = []
            tweets_by_user[username].append(tweet)

        # 构建推文内容
        tweets_text = ""
        for username, user_tweets in tweets_by_user.items():
            tweets_text += f"\n\n=== @{username} ===\n"
            for i, tweet in enumerate(user_tweets, 1):
                created_at = tweet.get('created_at', '')
                thread_tag = "[🧵Thread] " if tweet.get('is_thread') else ""
                tweets_text += f"{i}. {thread_tag}[{created_at}] {tweet['text']}\n"
                tweets_text += f"   (❤️ {tweet['likes']} | 🔄 {tweet['retweets']} | 🔗 {tweet['url']})\n"

        prompt = f"""# 角色
你是一位专业的信息策展人，擅长从 Twitter/X 动态中提炼**有价值的信息**，按话题归类并突出重要内容。

# 原始推文
{tweets_text}

# 输出要求

## 📰 X 简报 - {{日期}}

### 🔥 今日重点
最重要的 5-8 条信息，每条包含：
- **[标题]** (@来源)
  - 核心内容（一两句话说清楚）
  - 原文链接

### 按话题归类

对剩余内容按话题归类，话题名称根据实际内容动态生成（如：科技、商业、AI、政治、文化、生活、观点争鸣等），每个话题下列出要点：
- **[要点]** (@来源) - 一句话概括 [链接]

### 💬 有趣的声音
值得一读的个人观点、吐槽、预测（保留原文精华）

---
**规则：**
1. 只输出有**具体信息**的内容，拒绝空洞概括
2. 数字、名称、链接必须来自原文，禁止编造
3. 无内容的分类直接省略
4. 中文输出，专有名词保留英文
5. **同一账号的多条相似推文合并为一条，避免逐条罗列**
6. 纯转发、广告、无实质内容的推文直接忽略
7. 标记为 [🧵Thread] 的内容是同一作者的连续自回复，应作为整体理解和总结，不要拆开
"""
        return prompt
    
    def summarize(self, tweets: List[Dict], max_tokens: int = 8000) -> str:
        """调用 Anthropic Messages API 进行总结，支持自动续写"""
        if not tweets:
            return "❌ 没有获取到任何推文，无法生成报告。"

        logger.info(f"🤖 调用 LLM 进行分析... (共 {len(tweets)} 条推文)")

        try:
            prompt = self.create_prompt(tweets)
            system_prompt = "你是专业的信息策展人。从推文中提炼有价值的信息，按话题归类，突出重点。只提取具体事实，拒绝空洞概括。"

            messages = [
                {"role": "user", "content": prompt}
            ]

            full_summary = ""
            max_continuations = 2

            for i in range(max_continuations + 1):
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=messages,
                    temperature=0.3
                )

                content = response.content[0].text
                stop_reason = response.stop_reason

                # 清理思考标签内容
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                content = content.strip()

                # 检测重复内容
                if full_summary and len(content) > 200:
                    if content[:200] in full_summary:
                        logger.warning("⚠️ 检测到重复内容，停止续写")
                        break

                full_summary += content

                if stop_reason == "max_tokens":
                    logger.info(f"⚠️ 响应被截断，正在续写... ({i+1}/{max_continuations})")
                    last_context = content[-100:] if len(content) > 100 else content
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"你的回复被截断了，请从「{last_context}」之后继续输出，不要重复已输出的内容。"})
                else:
                    break

            logger.info(f"✅ LLM 分析完成 (生成 {len(full_summary)} 字符)")
            return full_summary

        except anthropic.APIError as e:
            error_msg = f"Anthropic API 请求失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return f"❌ 生成报告失败: {error_msg}"
        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return f"❌ 生成报告失败: {error_msg}"
    
    def create_fallback_summary(self, tweets: List[Dict]) -> str:
        """
        创建备用简单总结（当LLM调用失败时）
        
        Args:
            tweets: 推文列表
            
        Returns:
            简单的文本总结
        """
        summary = "# AI资讯简报\n\n"
        summary += f"本次共获取 {len(tweets)} 条推文\n\n"
        
        # 按用户分组
        tweets_by_user = {}
        for tweet in tweets:
            username = tweet['username']
            if username not in tweets_by_user:
                tweets_by_user[username] = []
            tweets_by_user[username].append(tweet)
        
        for username, user_tweets in tweets_by_user.items():
            summary += f"\n## @{username}\n"
            for tweet in user_tweets[:3]:  # 每个用户最多显示3条
                summary += f"- {tweet['text'][:200]}\n"
                summary += f"  🔗 {tweet['url']}\n\n"
        
        return summary


def test_summarizer():
    """测试函数"""
    # 模拟推文数据
    test_tweets = [
        {
            'username': 'sama',
            'text': 'Excited to announce GPT-5 is coming soon!',
            'created_at': '2024-01-01',
            'likes': 10000,
            'retweets': 5000,
            'url': 'https://twitter.com/sama/status/123'
        },
        {
            'username': 'karpathy',
            'text': 'Just released a new tutorial on transformers',
            'created_at': '2024-01-01',
            'likes': 3000,
            'retweets': 1000,
            'url': 'https://twitter.com/karpathy/status/456'
        }
    ]
    
    summarizer = LLMSummarizer(
        api_key="your-api-key",
        model="claude-sonnet-4-20250514"
    )
    
    summary = summarizer.summarize(test_tweets)
    print(summary)


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    test_summarizer()
