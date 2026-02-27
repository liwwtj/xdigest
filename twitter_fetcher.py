"""
Twitter 数据抓取模块
支持 Cookies 登录模式抓取推文
"""

import asyncio
from typing import List, Dict
from pathlib import Path
from datetime import datetime, timedelta, timezone
import logging
from twikit import Client

logger = logging.getLogger(__name__)


class TwitterFetcher:
    """Twitter 推文抓取器"""

    def __init__(self, request_delay: int = 5, proxy: str = None, cookies_file: str = None,
                 retry_on_rate_limit: bool = True, max_retries: int = 3, max_tweet_age_hours: int = 9,
                 enable_thread_merging: bool = True, max_thread_fetches: int = 3):
        self.proxy = proxy
        self.cookies_file = cookies_file or "cookies.json"
        self.client = Client(language='en-US', proxy=proxy) if proxy else Client(language='en-US')
        self.request_delay = request_delay
        self.retry_on_rate_limit = retry_on_rate_limit
        self.max_retries = max_retries
        self.max_tweet_age_hours = max_tweet_age_hours
        self.enable_thread_merging = enable_thread_merging
        self.max_thread_fetches = max_thread_fetches
        self.stats = {
            'total_accounts': 0,
            'successful_accounts': 0,
            'failed_accounts': 0,
            'total_tweets': 0,
            'filtered_old_tweets': 0,
            'threads_detected': 0,
            'errors': []
        }

    async def init(self):
        """初始化 Client（加载 Cookies）"""
        try:
            logger.info("🔧 初始化 Twitter Client...")
            if not Path(self.cookies_file).exists():
                logger.error(f"❌ Cookies 文件不存在: {self.cookies_file}")
                return False
            self.client.load_cookies(self.cookies_file)
            logger.info("✅ Cookies 加载成功")
            return True
        except Exception as e:
            logger.error(f"❌ Client 初始化失败: {e}")
            return False

    async def get_following(self, username: str) -> List[str]:
        """获取指定用户的关注列表"""
        user = await self.client.get_user_by_screen_name(username)
        following = await self.client.get_user_following(user.id, count=200)
        return [u.screen_name for u in following]

    async def get_user_tweets(self, username: str, count: int = 5) -> List[Dict]:
        """获取指定用户的最新推文（带重试机制和时间过滤）"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(hours=self.max_tweet_age_hours)

        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"📡 抓取 @{username} 的推文...")
                user = await self.client.get_user_by_screen_name(username)
                tweets = await user.get_tweets('Tweets', count=count)

                results = []
                filtered_count = 0
                for tweet in tweets:
                    if hasattr(tweet, 'retweeted_tweet') and tweet.retweeted_tweet:
                        continue

                    # 解析时间
                    tweet_time = None
                    if hasattr(tweet, 'created_at') and tweet.created_at:
                        raw_time = tweet.created_at
                        # 处理不同类型
                        if isinstance(raw_time, datetime):
                            tweet_time = raw_time if raw_time.tzinfo else raw_time.replace(tzinfo=timezone.utc)
                        elif isinstance(raw_time, str):
                            try:
                                # Twitter API 返回格式: "Wed Oct 10 20:19:24 +0000 2018"
                                tweet_time = datetime.strptime(raw_time, "%a %b %d %H:%M:%S %z %Y")
                            except ValueError:
                                try:
                                    # 备用格式: "2026-01-30 12:34:56" (假定 UTC)
                                    tweet_time = datetime.strptime(raw_time[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                                except ValueError:
                                    tweet_time = None

                        # 时间过滤
                        if tweet_time and tweet_time < cutoff_date:
                            filtered_count += 1
                            continue

                    # 格式化时间为北京时间显示
                    if tweet_time:
                        beijing_time = tweet_time.astimezone(timezone(timedelta(hours=8)))
                        created_at_str = beijing_time.strftime("%Y-%m-%d %H:%M")
                    else:
                        created_at_str = ''

                    tweet_data = {
                        'username': username,
                        'text': tweet.text,
                        'created_at': created_at_str,
                        'likes': tweet.favorite_count if hasattr(tweet, 'favorite_count') else 0,
                        'retweets': tweet.retweet_count if hasattr(tweet, 'retweet_count') else 0,
                        'url': f'https://twitter.com/{username}/status/{tweet.id}'
                    }
                    results.append(tweet_data)

                if filtered_count > 0:
                    logger.info(f"   过滤了 {filtered_count} 条超过 {self.max_tweet_age_hours} 小时的旧推文")
                    self.stats['filtered_old_tweets'] += filtered_count

                # Thread 检测与合并
                if self.enable_thread_merging and results:
                    results = await self._merge_threads(username, results, tweets)

                logger.info(f"✅ @{username}: 成功获取 {len(results)} 条推文")
                self.stats['successful_accounts'] += 1
                self.stats['total_tweets'] += len(results)
                return results

            except Exception as e:
                error_msg = str(e)
                is_rate_limit = '429' in error_msg or 'Rate limit' in error_msg

                if is_rate_limit and self.retry_on_rate_limit and attempt < self.max_retries:
                    wait_time = (attempt + 1) * 30  # 30s, 60s, 90s
                    logger.warning(f"⚠️ @{username} 触发速率限制，等待 {wait_time}s 后重试 ({attempt+1}/{self.max_retries})...")
                    await asyncio.sleep(wait_time)
                    continue

                logger.warning(f"⚠️ 抓取失败 - @{username}: {error_msg}")
                self.stats['failed_accounts'] += 1
                self.stats['errors'].append(f"@{username}: {error_msg}")
                return []

        return []

    async def _merge_threads(self, username: str, results: List[Dict], raw_tweets) -> List[Dict]:
        """检测自回复 thread 并合并为单条推文"""
        # 建立 tweet id -> raw tweet 的映射
        tweet_map = {}
        for tweet in raw_tweets:
            tweet_map[tweet.id] = tweet

        # 找出自回复推文（reply_to 的 user 是自己）
        self_replies = set()
        reply_to_parent = {}  # child_id -> parent_id
        for tweet in raw_tweets:
            if not hasattr(tweet, 'in_reply_to_tweet_id') or not tweet.in_reply_to_tweet_id:
                continue
            # 检查是否是自回复
            reply_to_user = None
            if hasattr(tweet, '_data') and isinstance(tweet._data, dict):
                legacy = tweet._data.get('legacy', {})
                reply_to_user = legacy.get('in_reply_to_user_id_str')
            if not reply_to_user and hasattr(tweet, 'user') and tweet.user:
                # fallback: 如果 parent 在本批次中且同一用户
                parent_id = tweet.in_reply_to_tweet_id
                if parent_id in tweet_map and tweet_map[parent_id].user.id == tweet.user.id:
                    reply_to_user = tweet.user.id
            if reply_to_user and hasattr(tweet, 'user') and tweet.user and str(reply_to_user) == str(tweet.user.id):
                self_replies.add(tweet.id)
                reply_to_parent[tweet.id] = tweet.in_reply_to_tweet_id

        if not self_replies:
            return results

        # 找到 thread 的根推文 ID
        root_ids = set()
        for child_id, parent_id in reply_to_parent.items():
            # 沿着 parent 链往上找根
            root = parent_id
            visited = {child_id}
            while root in reply_to_parent and root not in visited:
                visited.add(root)
                root = reply_to_parent[root]
            root_ids.add(root)

        logger.info(f"🧵 @{username}: 检测到 {len(root_ids)} 个 thread")

        # 通过 API 获取完整 thread
        thread_texts = {}  # root_id -> [texts]
        thread_fetches = 0
        for root_id in root_ids:
            if thread_fetches >= self.max_thread_fetches:
                logger.info(f"   已达到最大 thread 请求数 ({self.max_thread_fetches})，跳过剩余")
                break
            try:
                root_tweet = await self.client.get_tweet_by_id(root_id)
                thread_fetches += 1
                await asyncio.sleep(self.request_delay)

                if hasattr(root_tweet, 'thread') and root_tweet.thread:
                    texts = [t.text for t in root_tweet.thread if hasattr(t, 'text')]
                    if texts:
                        thread_texts[root_id] = texts
                        self.stats['threads_detected'] += 1
                        logger.info(f"   🧵 获取到 thread ({len(texts)} 条推文)")
                        continue

                # fallback: 用本批次中已有的推文拼接
                self._fallback_thread_from_batch(root_id, tweet_map, reply_to_parent, thread_texts)

            except Exception as e:
                logger.warning(f"   ⚠️ 获取 thread {root_id} 失败: {e}，使用本地 fallback")
                self._fallback_thread_from_batch(root_id, tweet_map, reply_to_parent, thread_texts)

        if not thread_texts:
            return results

        # 合并 thread 到 results
        merged_ids = set()
        for root_id, texts in thread_texts.items():
            # 收集属于这个 thread 的所有 tweet id
            chain_ids = {root_id}
            for child_id, parent_id in reply_to_parent.items():
                r = parent_id
                visited = {child_id}
                while r in reply_to_parent and r not in visited:
                    visited.add(r)
                    r = reply_to_parent[r]
                if r == root_id:
                    chain_ids.add(child_id)
            merged_ids.update(chain_ids)

        # 重建 results：替换 thread 推文为合并版本
        new_results = []
        used_roots = set()
        for tweet_data in results:
            tweet_id = tweet_data['url'].split('/')[-1]  # 从 url 提取 id
            if tweet_id in merged_ids:
                # 找到对应的 root
                root = tweet_id
                visited = set()
                while root in reply_to_parent and root not in visited:
                    visited.add(root)
                    root = reply_to_parent[root]
                if root in thread_texts and root not in used_roots:
                    used_roots.add(root)
                    merged_text = "\n---\n".join(thread_texts[root])
                    merged_data = dict(tweet_data)
                    merged_data['text'] = merged_text
                    merged_data['is_thread'] = True
                    merged_data['thread_length'] = len(thread_texts[root])
                    # 使用 root 推文的 url
                    merged_data['url'] = f'https://twitter.com/{username}/status/{root}'
                    new_results.append(merged_data)
                # 跳过 thread 中的其他推文
                continue
            else:
                new_results.append(tweet_data)

        return new_results

    def _fallback_thread_from_batch(self, root_id, tweet_map, reply_to_parent, thread_texts):
        """从当前批次中拼接 thread（fallback）"""
        chain = []
        # 收集 root + 所有指向 root 的 children
        if root_id in tweet_map:
            chain.append((root_id, tweet_map[root_id]))
        for child_id, parent_id in reply_to_parent.items():
            r = parent_id
            visited = {child_id}
            while r in reply_to_parent and r not in visited:
                visited.add(r)
                r = reply_to_parent[r]
            if r == root_id and child_id in tweet_map:
                chain.append((child_id, tweet_map[child_id]))

        if len(chain) > 1:
            # 按时间排序
            chain.sort(key=lambda x: x[1].created_at if hasattr(x[1], 'created_at') and x[1].created_at else '')
            texts = [t.text for _, t in chain if hasattr(t, 'text')]
            if texts:
                thread_texts[root_id] = texts
                self.stats['threads_detected'] += 1

    async def fetch_multiple_accounts(self, usernames: List[str], tweets_per_account: int = 5,
                                      concurrency: int = 2) -> List[Dict]:
        """批量抓取多个账号的推文（并发）"""
        self.stats['total_accounts'] = len(usernames)
        semaphore = asyncio.Semaphore(concurrency)
        results = [None] * len(usernames)

        logger.info(f"🚀 开始批量抓取 {len(usernames)} 个账号 (并发数: {concurrency})...")

        async def _fetch(index, username):
            async with semaphore:
                logger.info(f"[{index+1}/{len(usernames)}] 抓取 @{username}...")
                tweets = await self.get_user_tweets(username, tweets_per_account)
                results[index] = tweets
                await asyncio.sleep(self.request_delay)

        await asyncio.gather(*[_fetch(i, u) for i, u in enumerate(usernames)])

        all_tweets = []
        for tweets in results:
            if tweets:
                all_tweets.extend(tweets)

        logger.info(f"📊 批量抓取完成!")
        logger.info(f"   - 总账号数: {self.stats['total_accounts']}")
        logger.info(f"   - 成功: {self.stats['successful_accounts']}")
        logger.info(f"   - 失败: {self.stats['failed_accounts']}")
        logger.info(f"   - 总推文数: {self.stats['total_tweets']}")
        if self.stats['total_accounts'] > 0:
            logger.info(f"   - 成功率: {self.stats['successful_accounts']/self.stats['total_accounts']*100:.1f}%")

        return all_tweets

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.stats


async def test_fetcher():
    """测试函数"""
    fetcher = TwitterFetcher(proxy="http://127.0.0.1:7890")
    if not await fetcher.init():
        print("初始化失败")
        return

    test_accounts = ['sama', 'karpathy']
    tweets = await fetcher.fetch_multiple_accounts(test_accounts, tweets_per_account=3)

    print(f"\n抓取到 {len(tweets)} 条推文:")
    for tweet in tweets[:5]:
        print(f"\n@{tweet['username']}: {tweet['text'][:100]}...")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(test_fetcher())
