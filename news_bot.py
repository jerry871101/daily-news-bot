# 版本：v13.0 (雲端專用版：移除本機排程，改讀取環境變數密碼)
import os          # 用來讀取雲端保險箱密碼的套件
import feedparser  
import time        
import smtplib     
from email.mime.text import MIMEText           
from email.mime.multipart import MIMEMultipart 
from google import genai 

# =====================================================================
# ☁️ 雲端設定區：改為從 GitHub Secrets (保險箱) 讀取，程式碼不再暴露密碼！
# =====================================================================
API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")
# =====================================================================

client = genai.Client(api_key=API_KEY) 

def fetch_international_news():  
    news_list = []
    rss_sources = [
        ("http://feeds.bbci.co.uk/news/rss.xml", "BBC"),
        ("https://moxie.foxnews.com/google-publisher/world.xml", "Fox News"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362", "CNBC"),
        ("https://feeds.a.dj.com/rss/RSSWorldNews.xml", "華爾街日報 (WSJ)"),
        ("http://feeds.reuters.com/reuters/worldNews", "路透社 (Reuters)")
    ]
    for url, source_name in rss_sources:
        feed = feedparser.parse(url)
        for entry in feed.entries[:2]:
            entry.custom_source = source_name 
            news_list.append(entry)
    return news_list

def fetch_domestic_news():  
    news_list = []
    google_tech_url = "https://news.google.com/rss/search?q=科技產業+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    tech_feed = feedparser.parse(google_tech_url)
    for entry in tech_feed.entries[:3]:
        entry.custom_source = getattr(entry, 'source', {}).get('title', '台灣科技媒體') if hasattr(entry, 'source') else '台灣科技媒體'
        news_list.append(entry)
    
    google_biz_url = "https://news.google.com/rss/search?q=財經+經濟+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    biz_feed = feedparser.parse(google_biz_url)
    for entry in biz_feed.entries[:2]:
        entry.custom_source = getattr(entry, 'source', {}).get('title', '台灣財經媒體') if hasattr(entry, 'source') else '台灣財經媒體'
        news_list.append(entry)
    return news_list

def process_news_with_api(news_title, news_summary):  
    prompt = f"""請分析以下新聞：
    新聞標題：{news_title}
    新聞簡介：{news_summary}

    請完成兩件事：
    1. 將標題翻譯成流暢的「繁體中文」。
    2. 寫出 150~300 字的詳細摘要。若有列點說明，請務必明確換行分段。請勿使用任何 Markdown 語法（例如 ** 或 #）。

    請直接輸出結果，不要包含任何問候語，並嚴格按照以下格式輸出，中間使用三個垂直線 ||| 隔開：
    [繁體中文標題]|||[詳細摘要內容]
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        result = response.text.strip()
        
        if '|||' in result:
            zh_title, summary = result.split('|||', 1)
        else:
            zh_title = news_title 
            summary = result
        return zh_title.strip(), summary.strip()
    except Exception as e:
        return news_title, "無法生成摘要，請檢查 API 狀態或網路連線。"

def build_html_email(intl_news, domestic_news):  
    html_content = """
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: auto;">
        <h2 style="color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 10px;">【每日早晨新聞重點分析】</h2>
        <h3 style="color: #2980b9;">🌍 國際熱門頭條新聞 (WSJ/路透/BBC/Fox/CNBC 焦點 10 則)</h3>
    """
    
    for i, news in enumerate(intl_news, 1):
        content_summary = news.get('summary', '無提供內文簡介')
        zh_title, ai_analysis = process_news_with_api(news.title, content_summary)
        formatted_analysis = ai_analysis.replace('\n', '<br>')
        
        html_content += f"""
        <div style="margin-bottom: 25px;">
            <h4 style="margin: 0 0 5px 0; color: #1abc9c; font-size: 18px;">{i}. {zh_title}</h4>
            <div style="color: #7f8c8d; font-size: 13px; margin-bottom: 8px;">📰 資料來源：{news.custom_source}</div>
            <div style="background-color: #f8f9fa; padding: 15px; border-left: 5px solid #1abc9c; border-radius: 5px; margin-bottom: 10px;">
                <strong>💡 AI 分析：</strong><br>{formatted_analysis}
            </div>
            <a href="{news.link}" style="color: #3498db; text-decoration: none; font-size: 14px;">🔗 點此閱讀原文</a>
        </div>
        """
        time.sleep(3) 
        
    html_content += """
        <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">
        <h3 style="color: #e67e22;">🏠 國內熱門新聞 (科技 60% / 財經 40%)</h3>
    """
    for i, news in enumerate(domestic_news, 1):
        content_summary = news.get('summary', '無提供內文簡介')
        zh_title, ai_analysis = process_news_with_api(news.title, content_summary)
        formatted_analysis = ai_analysis.replace('\n', '<br>')
        
        html_content += f"""
        <div style="margin-bottom: 25px;">
            <h4 style="margin: 0 0 5px 0; color: #f39c12; font-size: 18px;">{i}. {zh_title}</h4>
            <div style="color: #7f8c8d; font-size: 13px; margin-bottom: 8px;">📰 資料來源：{news.custom_source}</div>
            <div style="background-color: #f8f9fa; padding: 15px; border-left: 5px solid #f39c12; border-radius: 5px; margin-bottom: 10px;">
                <strong>💡 AI 分析：</strong><br>{formatted_analysis}
            </div>
            <a href="{news.link}" style="color: #3498db; text-decoration: none; font-size: 14px;">🔗 點此閱讀原文</a>
        </div>
        """
        time.sleep(3)
    html_content += "</body></html>"
    return html_content

def send_email_job(html_content):  
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"📰 您的專屬每日熱門頭條分析 ({time.strftime('%Y-%m-%d')})"
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() 
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"[{time.strftime('%H:%M:%S')}] ✅ Email 寄送成功！")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ❌ Email 寄送失敗，錯誤訊息：{e}")

def daily_news_routine():  
    print("開始抓取新聞並由 AI 進行分析排版...")
    intl_news = fetch_international_news()
    domestic_news = fetch_domestic_news()
    final_html = build_html_email(intl_news, domestic_news)
    send_email_job(final_html)

if __name__ == "__main__":
    daily_news_routine()