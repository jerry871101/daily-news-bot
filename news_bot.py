# 版本：v15.0 (深度客製化：精準 ETF 追蹤、AI 特定配備掃描、函式中文註解)
import os          
import feedparser  
import time        
import smtplib
import requests    
from email.mime.text import MIMEText           
from email.mime.multipart import MIMEMultipart 
from google import genai 

# 偽裝成一般 Chrome 瀏覽器，防止被 Google 阻擋
feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

client = genai.Client(api_key=API_KEY) 

def get_tamsui_weather(): # 取得淡水區今日即時氣溫與最高降雨機率
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=25.1706&longitude=121.4398&current_weather=true&daily=precipitation_probability_max&timezone=Asia%2FTaipei"
        response = requests.get(url, timeout=10)
        data = response.json()
        current_temp = data['current_weather']['temperature']
        weather_code = data['current_weather']['weathercode']
        rain_chance = data['daily']['precipitation_probability_max'][0] 
        
        weather_desc = {
            0: '☀️ 晴朗', 1: '🌤️ 多雲', 2: '⛅ 陰晴', 3: '☁️ 陰天', 
            45: '🌫️ 起霧', 48: '🌫️ 濃霧', 51: '🌧️ 微雨', 53: '🌧️ 小雨', 
            61: '🌧️ 降雨', 63: '🌧️ 大雨', 80: '🌦️ 陣雨', 95: '⛈️ 雷雨'
        }
        condition = weather_desc.get(weather_code, '☁️ 未知')
        return f"🌡️ 氣溫：{current_temp}°C &nbsp;&nbsp;|&nbsp;&nbsp; {condition} &nbsp;&nbsp;|&nbsp;&nbsp; ☔ 降雨機率：{rain_chance}%"
    except Exception as e:
        return "⚠️ 暫時無法取得天氣資訊"

def fetch_international_news(): # 輪流抽取5大國際媒體RSS，確保產出10則多元國際頭條
    rss_sources = [
        ("http://feeds.bbci.co.uk/news/rss.xml", "BBC"),
        ("https://moxie.foxnews.com/google-publisher/world.xml", "Fox News"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362", "CNBC"),
        ("https://feeds.a.dj.com/rss/RSSWorldNews.xml", "華爾街日報 (WSJ)"),
        ("http://feeds.reuters.com/reuters/worldNews", "路透社 (Reuters)")
    ]
    all_source_entries = []
    for url, source_name in rss_sources:
        try:
            feed = feedparser.parse(url)
            valid_entries = []
            for entry in feed.entries[:5]:
                entry.custom_source = source_name 
                valid_entries.append(entry)
            if valid_entries:
                all_source_entries.append(valid_entries)
        except Exception:
            pass

    final_list = []
    round_idx = 0
    while len(final_list) < 10:
        added_in_this_round = False
        for entries in all_source_entries:
            if round_idx < len(entries):
                final_list.append(entries[round_idx])
                added_in_this_round = True
                if len(final_list) == 10:
                    break
        if not added_in_this_round: 
            break
        round_idx += 1
    return final_list

def fetch_domestic_news(): # 抓取台灣科技新聞與特定ETF/大盤財經動態
    news_list = []
    google_tech_url = "https://news.google.com/rss/search?q=科技產業+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    tech_feed = feedparser.parse(google_tech_url)
    for entry in tech_feed.entries[:3]:
        entry.custom_source = getattr(entry, 'source', {}).get('title', '台灣科技媒體') if hasattr(entry, 'source') else '台灣科技媒體'
        news_list.append(entry)
    
    # 💎 優化：將廣泛的財經改為精準追蹤特定投資標的
    google_biz_url = "https://news.google.com/rss/search?q=0050+OR+VOO+OR+QQQ+OR+美股+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    biz_feed = feedparser.parse(google_biz_url)
    for entry in biz_feed.entries[:2]:
        entry.custom_source = getattr(entry, 'source', {}).get('title', '台灣財經媒體') if hasattr(entry, 'source') else '台灣財經媒體'
        news_list.append(entry)
    return news_list

def fetch_car_news(): # 抓取24小時內最新汽車改款與上市情報
    news_list = []
    google_car_url = "https://news.google.com/rss/search?q=新車+改款+上市+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    car_feed = feedparser.parse(google_car_url)
    for entry in car_feed.entries[:3]: 
        entry.custom_source = getattr(entry, 'source', {}).get('title', '汽車媒體') if hasattr(entry, 'source') else '汽車媒體'
        news_list.append(entry)
    return news_list

def process_news_with_api(news_title, news_summary): # 呼叫 Gemini AI 進行多國語言翻譯與客製化摘要分析
    prompt = f"""請以專業分析師的角度分析以下新聞：
    新聞標題：{news_title}
    新聞簡介：{news_summary}

    請完成：
    1. 將標題翻譯成流暢的「繁體中文」。
    2. 寫出 150~300 字的重點摘要。若有列點說明，請明確換行分段。請勿使用 Markdown 語法（例如 ** 或 #）。
    3. 特別指令：若此篇為「汽車產業」相關新聞，請務必幫我掃描內文，並特別標示出是否有提及「通風座椅」等內裝配備資訊。

    請直接輸出結果，嚴格按照以下格式輸出，中間使用三個垂直線 ||| 隔開：
    [繁體中文標題]|||[詳細摘要內容]
    """
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        result = response.text.strip()
        if '|||' in result:
            zh_title, summary = result.split('|||', 1)
        else:
            zh_title = news_title 
            summary = result
        return zh_title.strip(), summary.strip()
    except Exception:
        return news_title, "無法生成摘要，請檢查 API 狀態或網路連線。"

def build_html_email(weather_info, intl_news, domestic_news, car_news): # 組合所有資訊板塊並套用 HTML 電子報排版
    html_content = f"""
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: auto;">
        
        <div style="background-color: #f0f8ff; border-left: 5px solid #3498db; padding: 15px; margin-bottom: 25px; border-radius: 5px;">
            <h3 style="margin: 0 0 10px 0; color: #2980b9;">📍 今日淡水區天氣預報</h3>
            <div style="font-size: 16px; font-weight: bold; color: #2c3e50;">{weather_info}</div>
        </div>

        <h2 style="color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 10px;">【每日早晨新聞重點分析】</h2>
        <h3 style="color: #8e44ad;">🚗 汽車產業動態 (新車 / 改款 / 上市資訊)</h3>
    """
    for i, news in enumerate(car_news, 1):
        content_summary = news.get('summary', '無提供內文簡介')
        zh_title, ai_analysis = process_news_with_api(news.title, content_summary)
        formatted_analysis = ai_analysis.replace('\n', '<br>')
        html_content += f"""
        <div style="margin-bottom: 25px;">
            <h4 style="margin: 0 0 5px 0; color: #9b59b6; font-size: 18px;">{i}. {zh_title}</h4>
            <div style="color: #7f8c8d; font-size: 13px; margin-bottom: 8px;">📰 資料來源：{news.custom_source}</div>
            <div style="background-color: #f8f9fa; padding: 15px; border-left: 5px solid #9b59b6; border-radius: 5px; margin-bottom: 10px;">
                <strong>💡 AI 分析：</strong><br>{formatted_analysis}
            </div>
            <a href="{news.link}" style="color: #3498db; text-decoration: none; font-size: 14px;">🔗 點此閱讀原文</a>
        </div>
        """
        time.sleep(3)

    html_content += """
        <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">
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

def send_email_job(html_content): # 將最終生成的 HTML 報表透過 SMTP 發送至指定信箱
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

def daily_news_routine(): # 每日自動化主程式：依序執行資料獲取、AI 處理與郵件寄送
    print("開始抓取新聞與天氣，並由 AI 進行分析排版...")
    weather_info = get_tamsui_weather()
    intl_news = fetch_international_news()
    domestic_news = fetch_domestic_news()
    car_news = fetch_car_news()
    
    final_html = build_html_email(weather_info, intl_news, domestic_news, car_news)
    send_email_job(final_html)

if __name__ == "__main__":
    daily_news_routine()
