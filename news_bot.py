# 版本：v25.2 (完美定案版：加入「幽靈空包彈」過濾器，確保每篇都有實質內容)
import os          
import feedparser  
import time
import datetime    
from calendar import timegm 
import smtplib
import requests    
import json
from email.mime.text import MIMEText           
from email.mime.multipart import MIMEMultipart 

feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAILS_STR = os.getenv("RECEIVER_EMAIL", "") 

def get_custom_weather(lat, lon, loc_name, is_evening): 
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode&timezone=Asia%2FTaipei"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        weather_desc = {
            0: '☀️ 晴朗', 1: '🌤️ 多雲', 2: '⛅ 陰晴', 3: '☁️ 陰天', 
            45: '🌫️ 起霧', 48: '🌫️ 濃霧', 51: '🌧️ 微雨', 53: '🌧️ 小雨', 
            61: '🌧️ 降雨', 63: '🌧️ 大雨', 80: '🌦️ 陣雨', 95: '⛈️ 雷雨'
        }

        if is_evening:
            max_t = data['daily']['temperature_2m_max'][1]
            min_t = data['daily']['temperature_2m_min'][1]
            rain_chance = data['daily']['precipitation_probability_max'][1]
            condition = weather_desc.get(data['daily']['weathercode'][1], '☁️ 未知')
            return f"🌙 【明日{loc_name}預報】 🌡️ 氣溫：{min_t}~{max_t}°C &nbsp;|&nbsp; {condition} &nbsp;|&nbsp; ☔ 降雨機率：{rain_chance}%"
        else:
            current_temp = data['current_weather']['temperature']
            rain_chance = data['daily']['precipitation_probability_max'][0]
            condition = weather_desc.get(data['current_weather']['weathercode'], '☁️ 未知')
            return f"☀️ 【今日{loc_name}預報】 🌡️ 氣溫：{current_temp}°C &nbsp;|&nbsp; {condition} &nbsp;|&nbsp; ☔ 降雨機率：{rain_chance}%"
    except Exception as e:
        return f"⚠️ 暫時無法取得{loc_name}天氣資訊"

def is_valid_news(title, summary):
    """🛡️ 幽靈空包彈過濾器：檢查是否為真實新聞"""
    if len(summary) < 20: 
        return False # 內容太短，通常是空包彈
    if title.count('-') >= 1:
        parts = title.split('-')
        # 如果標題前後一模一樣 (例如 "AUTO ONLINE - AUTO ONLINE")，代表抓到首頁了
        if parts[0].strip() == parts[1].strip():
            return False
    return True

def fetch_top_international_news():
    rss_sources = [
        ("http://feeds.bbci.co.uk/news/rss.xml", "BBC News"),
        ("http://feeds.reuters.com/reuters/worldNews", "路透社 (Reuters)"),
        ("https://feeds.a.dj.com/rss/RSSWorldNews.xml", "華爾街日報 (WSJ)"),
        ("https://moxie.foxnews.com/google-publisher/world.xml", "Fox News"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362", "CNBC")
    ]
    all_news = []
    current_time = time.time()
    
    for url, source_name in rss_sources:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                title = entry.get('title', '')
                summary = entry.get('summary', '')
                
                if not is_valid_news(title, summary):
                    continue # 如果是空包彈，直接跳過抓下一篇
                    
                published_tuple = getattr(entry, 'published_parsed', None)
                if published_tuple:
                    entry_time = timegm(published_tuple)
                    if (current_time - entry_time) > (24 * 3600): continue 
                
                entry.custom_source = source_name
                all_news.append(entry)
                count += 1
                if count >= 3: break
        except:
            continue
    return all_news[:8]

def fetch_car_news():
    google_car_url = "https://news.google.com/rss/search?q=新車+改款+上市+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(google_car_url)
    car_news = []
    for entry in feed.entries: 
        title = entry.get('title', '')
        summary = entry.get('summary', '')
        
        if not is_valid_news(title, summary):
            continue # 如果是空包彈，直接跳過抓下一篇
            
        entry.custom_source = getattr(entry, 'source', {}).get('title', '汽車媒體')
        car_news.append(entry)
        if len(car_news) >= 5: 
            break
    return car_news

def ai_analyze_news(title, summary, is_car=False):
    base_prompt = f"""
    請以專業分析師的角度分析這則新聞：
    標題：{title}
    簡介：{summary}

    要求：
    1. 將標題翻譯為專業的「繁體中文」。
    2. 撰寫 150~300 字的詳細摘要。
    """
    car_special = "\n3. 特別指令：請務必掃描內文，並在摘要最後標示出是否有提及「通風座椅」等內裝配備資訊。" if is_car else ""
    format_prompt = """
    請直接輸出結果，請絕對不要使用 ** 這種 Markdown 粗體語法，直接輸出以下格式並用 ||| 分隔：
    [中文標題]|||[摘要內容]
    """
    final_prompt = base_prompt + car_special + format_prompt
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": final_prompt}]}]}

    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            data = response.json()
            
            if response.status_code != 200:
                error_msg = data.get('error', {}).get('message', '未知錯誤')
                if response.status_code == 429:
                    time.sleep(60)
                    continue
                else:
                    return title, f"API 錯誤代碼 {response.status_code}：{error_msg}"

            result = data['candidates'][0]['content']['parts'][0]['text'].strip()
            result = result.replace('**', '') 
            
            if '|||' in result:
                zh_title, analysis = result.split('|||', 1)
                return zh_title.strip(), analysis.strip()
            return title, result
            
        except Exception as e:
            if attempt < 2:
                time.sleep(15)
            else:
                return title, f"摘要生成失敗 (網路連線異常)。除錯資訊：{str(e)[:50]}..."

def build_elegant_html(weather_info, intl_list, car_list, edition_name):
    date_str = datetime.datetime.now().strftime("%Y年%m月%d日")
    html = f"""
    <html>
    <body style="font-family: 'Microsoft JhengHei', sans-serif; color: #333; max-width: 850px; margin: auto; line-height: 1.7;">
        <div style="background: linear-gradient(135deg, #2c3e50, #3498db); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 28px;">專屬新聞分析{edition_name}</h1>
            <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">{date_str} | 全球動態與車市追蹤</p>
        </div>
        <div style="background-color: #f0f8ff; padding: 15px; margin-top: 20px; border-left: 5px solid #3498db; border-radius: 5px; font-weight: bold; color: #2c3e50;">
            {weather_info}
        </div>
        <div style="padding: 20px; background-color: #ffffff; border: 1px solid #ddd; border-top: none;">
            <h2 style="color: #8e44ad; border-left: 6px solid #8e44ad; padding-left: 15px; margin-top: 10px;">🚗 汽車產業動態 (Top 5)</h2>
    """
    for i, item in enumerate(car_list, 1):
        html += f"""
            <div style="margin-bottom: 35px; padding-bottom: 20px; border-bottom: 1px dashed #eee;">
                <h3 style="color: #9b59b6; font-size: 20px; margin-bottom: 8px;">{i}. {item['title']}</h3>
                <div style="font-size: 13px; color: #7f8c8d; margin-bottom: 12px;">📍 來源：{item['source']}</div>
                <div style="background-color: #fdfaf6; padding: 18px; border-radius: 8px; border-left: 4px solid #9b59b6;">
                    <strong>【AI 分析】</strong><br>{item['analysis']}
                </div>
                <div style="margin-top: 10px;"><a href="{item['link']}" style="color: #3498db; text-decoration: none; font-size: 14px;">閱讀原始報導 →</a></div>
            </div>
        """
    html += f"""
            <h2 style="color: #1a2a6c; border-left: 6px solid #1a2a6c; padding-left: 15px; margin-top: 50px;">🌍 全球頂尖外媒頭條 (Top 8)</h2>
    """
    for i, item in enumerate(intl_list, 1):
        html += f"""
            <div style="margin-bottom: 35px; padding-bottom: 20px; border-bottom: 1px dashed #eee;">
                <h3 style="color: #c0392b; font-size: 20px; margin-bottom: 8px;">{i}. {item['title']}</h3>
                <div style="font-size: 13px; color: #7f8c8d; margin-bottom: 12px;">📍 來源：{item['source']}</div>
                <div style="background-color: #f9f9f9; padding: 18px; border-radius: 8px; border-left: 4px solid #c0392b;">
                    <strong>【核心摘要】</strong><br>{item['analysis']}
                </div>
                <div style="margin-top: 10px;"><a href="{item['link']}" style="color: #3498db; text-decoration: none; font-size: 14px;">閱讀原始報導 →</a></div>
            </div>
        """
    html += """
        </div>
        <div style="text-align: center; color: #95a5a6; font-size: 12px; padding: 20px;">
            本郵件由 AI 智能助理自動彙整與分析。
        </div>
    </body>
    </html>
    """
    return html

def main():
    tw_tz = datetime.timezone(datetime.timedelta(hours=8))
    now_tw = datetime.datetime.now(tw_tz)
    is_evening = now_tw.hour >= 12
    edition_name = "晚報" if is_evening else "早報"
    
    print(f"🚀 啟動 {edition_name} 彙整任務 (8篇國際 + 5篇汽車)...")
    
    intl_raw = fetch_top_international_news()
    car_raw = fetch_car_news()
    
    car_results = []
    print(f"正在分析 {len(car_raw)} 則汽車新聞...")
    for news in car_raw:
        safe_summary = news.get('summary', '')[:2000]
        zh_t, ana = ai_analyze_news(news.title, safe_summary, is_car=True)
        car_results.append({'title': zh_t, 'analysis': ana.replace('\n', '<br>'), 'source': news.custom_source, 'link': news.link})
        # ⚠️ 請依據您的方案調整秒數：免費版 20，付費版可改 2
        time.sleep(20) 
        
    intl_results = []
    print(f"正在分析 {len(intl_raw)} 則國際新聞...")
    for news in intl_raw:
        safe_summary = news.get('summary', '')[:2000]
        zh_t, ana = ai_analyze_news(news.title, safe_summary, is_car=False)
        intl_results.append({'title': zh_t, 'analysis': ana.replace('\n', '<br>'), 'source': news.custom_source, 'link': news.link})
        # ⚠️ 請依據您的方案調整秒數：免費版 20，付費版可改 2
        time.sleep(20) 

    email_list = [e.strip() for e in RECEIVER_EMAILS_STR.split(",") if e.strip()]
    subscribers = []
    if len(email_list) >= 1: subscribers.append({"email": email_list[0], "loc": "淡水區", "lat": 25.1706, "lon": 121.4398})
    if len(email_list) >= 2: subscribers.append({"email": email_list[1], "loc": "新豐鄉", "lat": 24.8988, "lon": 120.9818})

    for sub in subscribers:
        weather_info = get_custom_weather(sub['lat'], sub['lon'], sub['loc'], is_evening)
        final_html = build_elegant_html(weather_info, intl_results, car_results, edition_name)
        
        msg = MIMEMultipart()
        msg['Subject'] = f"📰 專屬每日分析 - {edition_name} ({now_tw.strftime('%m/%d')})"
        msg['From'] = SENDER_EMAIL
        msg['To'] = sub['email']
        msg.attach(MIMEText(final_html, 'html', 'utf-8'))
        
        try:
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(SENDER_EMAIL, APP_PASSWORD)
                server.send_message(msg)
                print(f"✅ 報告已成功送達：{sub['email']}")
        except Exception as e:
            print(f"❌ 寄送失敗：{e}")

if __name__ == "__main__":
    main()
