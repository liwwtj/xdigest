"""
邮件发送模块
支持 Resend 和 SMTP 两种方式
"""

import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EmailSender:
    """邮件发送器"""
    
    def __init__(
        self,
        provider: str = "resend",
        resend_api_key: str = None,
        smtp_config: dict = None,
        from_email: str = None,
        to_email: str = None
    ):
        """
        初始化邮件发送器
        
        Args:
            provider: 邮件服务商 ("resend" 或 "smtp")
            resend_api_key: Resend API密钥
            smtp_config: SMTP配置 {server, port, username, password}
            from_email: 发件人邮箱
            to_email: 收件人邮箱
        """
        self.provider = provider
        self.resend_api_key = resend_api_key
        self.smtp_config = smtp_config
        self.from_email = from_email
        self.to_email = to_email
    
    def send_via_resend(self, subject: str, content: str, content_type: str = "text") -> bool:
        """
        通过 Resend 发送邮件
        
        Args:
            subject: 邮件主题
            content: 邮件内容
            content_type: 内容类型 ("text" 或 "html")
            
        Returns:
            是否发送成功
        """
        try:
            logger.info("📧 通过 Resend 发送邮件...")
            
            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {self.resend_api_key}",
                "Content-Type": "application/json"
            }
            
            # 构建邮件内容
            if content_type == "html":
                email_content = {"html": content}
            else:
                # 将 Markdown 转换为简单 HTML
                html_content = self._markdown_to_html(content)
                email_content = {"html": html_content}
            
            payload = {
                "from": self.from_email,
                "to": [self.to_email],
                "subject": subject,
                **email_content
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ 邮件发送成功! (ID: {result.get('id', 'N/A')})")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Resend 发送失败: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 未知错误: {e}")
            return False
    
    def send_via_smtp(self, subject: str, content: str) -> bool:
        """
        通过 SMTP 发送邮件
        
        Args:
            subject: 邮件主题
            content: 邮件内容
            
        Returns:
            是否发送成功
        """
        try:
            logger.info("📧 通过 SMTP 发送邮件...")
            
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            
            # 转换为 HTML
            html_content = self._markdown_to_html(content)
            
            # 添加纯文本和HTML版本
            text_part = MIMEText(content, 'plain', 'utf-8')
            html_part = MIMEText(html_content, 'html', 'utf-8')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # 发送邮件
            with smtplib.SMTP(
                self.smtp_config['server'],
                self.smtp_config['port']
            ) as server:
                server.starttls()
                server.login(
                    self.smtp_config['username'],
                    self.smtp_config['password']
                )
                server.send_message(msg)
            
            logger.info("✅ 邮件发送成功!")
            return True
            
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP 发送失败: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 未知错误: {e}")
            return False
    
    def send(self, subject: str, content: str, stats: dict = None) -> bool:
        """
        发送邮件（根据配置选择方式）
        
        Args:
            subject: 邮件主题
            content: 邮件内容
            stats: 统计信息（可选）
            
        Returns:
            是否发送成功
        """
        # 添加统计信息到邮件
        if stats:
            stats_text = self._format_stats(stats)
            content = content + "\n\n" + stats_text
        
        # 根据配置选择发送方式
        if self.provider == "resend":
            return self.send_via_resend(subject, content)
        elif self.provider == "smtp":
            return self.send_via_smtp(subject, content)
        else:
            logger.error(f"❌ 不支持的邮件服务商: {self.provider}")
            return False
    
    def _markdown_to_html(self, markdown_text: str) -> str:
        """
        简单的 Markdown 转 HTML

        Args:
            markdown_text: Markdown 文本

        Returns:
            HTML 文本
        """
        import re

        html = markdown_text

        # 处理表格
        def convert_table(match):
            table_text = match.group(0)
            lines = table_text.strip().split('\n')
            if len(lines) < 2:
                return table_text
            table_html = '<table style="border-collapse:collapse;margin:15px 0;width:100%;">'
            header_cells = [c.strip() for c in lines[0].split('|') if c.strip()]
            table_html += '<thead><tr>'
            for cell in header_cells:
                table_html += f'<th style="background:#f5f5f5;padding:10px;border:1px solid #ddd;text-align:left;">{cell}</th>'
            table_html += '</tr></thead><tbody>'
            for line in lines[2:]:
                cells = [c.strip() for c in line.split('|') if c.strip()]
                if cells:
                    table_html += '<tr>'
                    for cell in cells:
                        table_html += f'<td style="padding:10px;border:1px solid #ddd;">{cell}</td>'
                    table_html += '</tr>'
            table_html += '</tbody></table>'
            return table_html

        # 匹配表格
        html = re.sub(r'(\|[^\n]+\|\n)+', convert_table, html)

        # 替换标题
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # 替换粗体
        html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
        
        # 替换链接
        html = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', html)
        
        # 替换列表项
        html = re.sub(r'^\- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'(<li>.*</li>\n?)+', r'<ul>\g<0></ul>', html)
        
        # 替换换行
        html = html.replace('\n\n', '<br><br>')
        html = html.replace('\n', '<br>')
        
        # 添加基本样式
        styled_html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                h1, h2, h3 {{
                    color: #2c3e50;
                    margin-top: 24px;
                }}
                a {{
                    color: #3498db;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                ul {{
                    padding-left: 20px;
                }}
                .stats {{
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                    margin-top: 30px;
                    font-size: 0.9em;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            {html}
        </body>
        </html>
        """
        
        return styled_html
    
    def _format_stats(self, stats: dict) -> str:
        """
        格式化统计信息
        
        Args:
            stats: 统计数据
            
        Returns:
            格式化的统计文本
        """
        stats_text = "\n---\n\n## 📊 本次抓取统计\n\n"
        stats_text += f"- 总账号数: {stats.get('total_accounts', 0)}\n"
        stats_text += f"- 成功抓取: {stats.get('successful_accounts', 0)}\n"
        stats_text += f"- 失败账号: {stats.get('failed_accounts', 0)}\n"
        stats_text += f"- 总推文数: {stats.get('total_tweets', 0)}\n"
        
        if stats.get('total_accounts', 0) > 0:
            success_rate = stats.get('successful_accounts', 0) / stats.get('total_accounts', 1) * 100
            stats_text += f"- 成功率: {success_rate:.1f}%\n"
        
        if stats.get('errors'):
            stats_text += f"\n失败账号:\n"
            for error in stats.get('errors', [])[:5]:  # 最多显示5个错误
                stats_text += f"- {error}\n"
        
        stats_text += f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return stats_text


def test_email_sender():
    """测试函数"""
    # 使用 Resend
    sender = EmailSender(
        provider="resend",
        resend_api_key="your-resend-api-key",
        from_email="digest@yourdomain.com",
        to_email="your@email.com"
    )
    
    test_content = """
# AI资讯日报测试

## 🔥 今日热点
- OpenAI 发布 GPT-5
- Google 推出新模型

## 📊 统计信息
- 共抓取 10 条推文
"""
    
    sender.send(
        subject="AI资讯日报 - 测试",
        content=test_content
    )


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    test_email_sender()
