"""
Twitter AI Digest - 主程序
每天自动抓取 AI 大佬推文并生成邮件摘要
"""

import asyncio
import argparse
import yaml
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from twitter_fetcher import TwitterFetcher
from llm_summarizer import LLMSummarizer
from email_sender import EmailSender

# 测试用推文数据
TEST_TWEETS = [
    {
        'username': 'OpenAI',
        'text': 'Introducing GPT-5.5 with enhanced reasoning capabilities. Now available for all Plus users. Key improvements: 2x faster inference, 50% reduction in hallucinations, native image generation.',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'likes': 15000,
        'retweets': 5000,
        'url': 'https://twitter.com/OpenAI/status/123456789'
    },
    {
        'username': 'AnthropicAI',
        'text': 'Claude 4 is here! Extended context window to 500K tokens, improved coding abilities, and new computer use features. Free tier users now get 50 messages/day.',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'likes': 8000,
        'retweets': 3000,
        'url': 'https://twitter.com/AnthropicAI/status/987654321'
    },
    {
        'username': 'karpathy',
        'text': 'Just released a new tutorial on building RAG systems from scratch. Covers chunking strategies, embedding selection, and reranking. GitHub link in bio.',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'likes': 5000,
        'retweets': 1500,
        'url': 'https://twitter.com/karpathy/status/111222333'
    },
    {
        'username': 'GoogleDeepMind',
        'text': 'AlphaFold 4 now predicts protein-drug interactions with 95% accuracy. Open sourcing the model weights next week. Paper: arxiv.org/abs/2026.12345',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'likes': 12000,
        'retweets': 4000,
        'url': 'https://twitter.com/GoogleDeepMind/status/444555666'
    },
    {
        'username': 'sama',
        'text': 'Excited to announce OpenAI Startup Fund is now $500M. Looking for founders building with AI in healthcare, education, and climate. Apply at openai.com/fund',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'likes': 20000,
        'retweets': 6000,
        'url': 'https://twitter.com/sama/status/777888999'
    }
]


class TwitterAIDigest:
    """Twitter AI 资讯日报生成器"""

    def __init__(self, config_path: str = "config.yaml", test_mode: bool = False, dry_run: bool = False):
        self.config = self._load_config(config_path)
        self.test_mode = test_mode
        self.dry_run = dry_run
        self._setup_logging()
        self._setup_components()
    
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"❌ 加载配置文件失败: {e}")
            raise

    async def _load_accounts(self) -> List[str]:
        """加载账号列表（优先自动获取关注列表）"""
        username = self.config.get('twitter', {}).get('username')
        if username:
            self.logger.info(f"📋 从 @{username} 的关注列表自动获取账号...")
            try:
                accounts = await self.fetcher.get_following(username)
                self.logger.info(f"✅ 获取到 {len(accounts)} 个关注账号")
                return accounts
            except Exception as e:
                self.logger.warning(f"⚠️ 自动获取关注列表失败: {e}，回退到账号文件")

        if 'accounts_file' in self.config:
            accounts_file = Path(self.config['accounts_file'])
            try:
                with open(accounts_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    return data
                return []
            except Exception as e:
                self.logger.error(f"❌ 加载账号文件失败: {e}")
                return []
        return self.config.get('accounts', [])

    def _setup_logging(self):
        """配置日志"""
        log_config = self.config.get('monitoring', {})
        
        if log_config.get('enable_logging', True):
            # 创建日志目录
            log_file = log_config.get('log_file', 'logs/digest.log')
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            
            # 配置日志
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file, encoding='utf-8'),
                    logging.StreamHandler()
                ]
            )
        
        self.logger = logging.getLogger(__name__)
    
    def _setup_components(self):
        """初始化各个组件"""
        # Twitter 抓取器
        twitter_config = self.config.get('twitter', {})
        self.fetcher = TwitterFetcher(
            request_delay=twitter_config.get('request_delay', 2),
            proxy=twitter_config.get('proxy'),
            max_tweet_age_hours=twitter_config.get('max_tweet_age_hours', 9),
            enable_thread_merging=twitter_config.get('enable_thread_merging', True),
            max_thread_fetches=twitter_config.get('max_thread_fetches', 3)
        )

        # LLM 总结器
        llm_config = self.config.get('llm', {})
        self.summarizer = LLMSummarizer(
            api_key=llm_config.get('api_key'),
            base_url=llm_config.get('base_url'),
            model=llm_config.get('model', 'claude-haiku-4-5-20251001')
        )
        
        # 邮件发送器
        email_config = self.config.get('email', {})
        
        if email_config.get('provider') == 'smtp':
            smtp_config = {
                'server': email_config.get('smtp_server'),
                'port': email_config.get('smtp_port'),
                'username': email_config.get('smtp_username'),
                'password': email_config.get('smtp_password')
            }
        else:
            smtp_config = None
        
        self.email_sender = EmailSender(
            provider=email_config.get('provider', 'resend'),
            resend_api_key=email_config.get('resend_api_key'),
            smtp_config=smtp_config,
            from_email=email_config.get('from_email'),
            to_email=email_config.get('to_email')
        )
    
    async def run(self):
        """运行主程序"""
        self.logger.info("=" * 60)
        self.logger.info("🚀 Twitter AI Digest 启动")
        if self.test_mode:
            self.logger.info("🧪 测试模式：使用模拟推文，执行完整流程")
        self.logger.info(f"⏰ 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)

        try:
            if self.test_mode:
                # 测试模式：使用模拟数据
                tweets = TEST_TWEETS
                stats = {
                    'total_accounts': len(set(t['username'] for t in tweets)),
                    'successful_accounts': len(set(t['username'] for t in tweets)),
                    'failed_accounts': 0,
                    'total_tweets': len(tweets),
                    'errors': []
                }
                self.logger.info(f"\n📥 步骤 1/3: 使用测试推文 ({len(tweets)} 条)")
            else:
                # 正常模式：抓取真实推文
                # 1. 初始化 Twitter 抓取器
                self.logger.info("\n📡 步骤 1/4: 初始化 Twitter Guest Client")
                if not await self.fetcher.init():
                    self.logger.error("❌ 初始化失败，程序退出")
                    return

                # 2. 抓取推文
                self.logger.info("\n📥 步骤 2/4: 抓取 AI 大佬推文")
                accounts = await self._load_accounts()
                tweets_per_account = self.config['twitter'].get('tweets_per_account', 5)

                self.logger.info(f"   - 账号数量: {len(accounts)}")
                self.logger.info(f"   - 每账号推文数: {tweets_per_account}")

                tweets = await self.fetcher.fetch_multiple_accounts(
                    accounts,
                    tweets_per_account
                )

                stats = self.fetcher.get_stats()

            if not tweets:
                self.logger.warning("⚠️  没有获取到任何推文，跳过后续步骤")
                if not self.test_mode:
                    self._save_stats(stats)
                return

            # LLM 总结
            step_num = "2/3" if self.test_mode else "3/4"
            self.logger.info(f"\n🤖 步骤 {step_num}: AI 智能分析")
            summary = self.summarizer.summarize(
                tweets,
                max_tokens=self.config['llm'].get('max_tokens', 2000)
            )

            # 保存摘要到文件
            self._save_summary(summary)

            if self.dry_run:
                self.logger.info("\n📝 === 摘要预览 ===\n")
                print(summary)
                self.logger.info("\n📝 === 预览结束 ===")
            else:
                # 发送邮件
                step_num = "3/3" if self.test_mode else "4/4"
                self.logger.info(f"\n📧 步骤 {step_num}: 发送邮件")
                subject = f"{self.config['email'].get('subject_prefix', 'AI资讯日报')} - {datetime.now().strftime('%Y年%m月%d日')}"

                success = self.email_sender.send(
                    subject=subject,
                    content=summary,
                    stats=stats
                )

                if success:
                    self.logger.info("✅ 邮件发送成功!")
                else:
                    self.logger.error("❌ 邮件发送失败")

            if not self.test_mode:
                self._save_stats(stats)

            self.logger.info("\n" + "=" * 60)
            self.logger.info("✨ 任务完成!")
            self.logger.info("=" * 60)

        except Exception as e:
            self.logger.error(f"❌ 程序运行出错: {e}", exc_info=True)
    
    def _save_stats(self, stats: Dict):
        """保存统计信息"""
        if not self.config.get('monitoring', {}).get('enable_stats', True):
            return
        
        try:
            stats_file = self.config['monitoring'].get('stats_file', 'logs/stats.json')
            Path(stats_file).parent.mkdir(parents=True, exist_ok=True)
            
            # 读取现有统计
            if Path(stats_file).exists():
                with open(stats_file, 'r', encoding='utf-8') as f:
                    all_stats = json.load(f)
            else:
                all_stats = []
            
            # 添加本次统计
            stats_entry = {
                'timestamp': datetime.now().isoformat(),
                **stats
            }
            all_stats.append(stats_entry)
            
            # 只保留最近30天的记录
            all_stats = all_stats[-30:]
            
            # 保存
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(all_stats, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"📊 统计信息已保存: {stats_file}")
            
        except Exception as e:
            self.logger.warning(f"保存统计信息失败: {e}")
    
    def _save_summary(self, summary: str):
        """保存摘要到文件"""
        try:
            # 创建输出目录
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            
            # 保存摘要
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f"digest_{timestamp}.md"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(summary)
            
            self.logger.info(f"💾 摘要已保存: {output_file}")
            
        except Exception as e:
            self.logger.warning(f"保存摘要失败: {e}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Twitter AI Digest - AI资讯日报生成器')
    parser.add_argument('--test', action='store_true', help='测试模式：使用模拟推文，执行完整流程（含邮件发送）')
    parser.add_argument('--dry-run', action='store_true', help='只打印摘要，不发送邮件')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    args = parser.parse_args()

    digest = TwitterAIDigest(config_path=args.config, test_mode=args.test, dry_run=args.dry_run)
    await digest.run()


if __name__ == "__main__":
    asyncio.run(main())
