# 版本：v27.0 (極致省錢版：加入 HTML 過濾器、縮減輸入字數至 800 字、精簡 AI 輸出字數)
import os          
import feedparser  
import time
import datetime    
from calendar import timegm 
import smtplib
import requests    
import json
import re # 引入正則表達式套件，用來清除 HTML 標籤
from email.mime.text import MIMEText           
from email.mime.multipart import MIMEMultipart 

# 偽裝成瀏覽器以順利抓取 RSS
feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 讀取環境變數
API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAILS_STR = os.getenv("RECEIVER_EMAIL", "") 

def clean_html_tags(text):
    """清除文字中的 HTML 標籤與多餘空白，替 API 呼叫「脫水減肥」節省 Token 成本"""
    if not text:
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', text)
    return cleantext.strip()

def get_custom_weather(lat, lon, loc_name, is_evening): 
    """取得特定座標的天氣預報資訊，區分早晚報顯示今日或明日天氣"""
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
    """🛡️ 幽靈空包彈過濾器：檢查是否為沒有實質內容的假新聞"""
    if len(summary) < 20: 
        return False
    if title.count('-') >= 1:
        parts = title.split('-')
        if parts[0].strip() == parts[1].strip():
            return False
    return True

def fetch_top_international_news():
    """抓取五大外媒的新聞，限制在 8 篇以內"""
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
                summary = clean_html_tags(entry.get('summary', '')) # 抓取時先脫水
                if not is_valid_news(title, summary): continue
                    
                published_tuple = getattr(entry, 'published_parsed', None)
                if published_tuple:
                    entry_time = timegm(published_tuple)
                    if (current_time - entry_time) > (24 * 3600): continue 
                
                entry.custom_source = source_name
                # 重新把乾淨的摘要塞回去
                entry.summary = summary
                all_news.append(entry)
                count += 1
                if count >= 3: break
        except:
            continue
    return all_news[:8]

def fetch_car_news():
    """抓取最新汽車動態，限制在 3 篇以內"""
    google_car_url = "https://news.google.com/rss/search?q=新車+改款+上市+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(google_car_url)
    car_news = []
    for entry in feed.entries: 
        title = entry.get('title', '')
        summary = clean_html_tags(entry.get('summary', '')) # 抓取時先脫水
        if not is_valid_news(title, summary): continue
            
        entry.custom_source = getattr(entry, 'source', {}).get('title', '汽車媒體')
        entry.summary = summary
        car_news.append(entry)
        if len(car_news) >= 3: 
            break
    return car_news

def ai_analyze_news(title, summary, is_car=False):
    """呼叫 Gemini 模型進行新聞翻譯與重點摘要"""
    base_prompt = f"""
    請以專業分析師的角度分析這則新聞：
    標題：{title}
    簡介：{summary}

    要求：
    1. 將標題翻譯為專業的「繁體中文」。
    2. 撰寫 100~150 字的精煉摘要。
    """
    car_special = "\n3. 特別指令：請務必掃描內文，並在摘要最後標示出是否有提及「通風座椅」等內裝配備資訊。" if is_car else ""
    format_prompt = """
    請直接輸出結果，不要使用 Markdown 粗體，輸出格式如下：
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
                if response.status_code == 429:
                    time.sleep(60)
                    continue
                return title, f"API 錯誤：{data.get('error', {}).get('message', '未知')}"

            result = data['candidates'][0]['content']['parts'][0]['text'].strip()
            result = result.replace('**', '') 
            if '|||' in result:
                zh_title, analysis = result.split('|||', 1)
                return zh_title.strip(), analysis.strip()
            return title, result
        except Exception as e:
            time.sleep(15)
    return title, "摘要生成失敗"

def build_elegant_html(weather_info, intl_list, car_list, edition_name):
    """將天氣資訊與新聞清單組裝成排版優美的 HTML 格式信件"""
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
            <h2 style="color: #8e44ad; border-left: 6px solid #8e44ad; padding-left: 15px; margin-top: 10px;">🚗 汽車產業動態 (Top 3)</h2>
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
    """主程式：負責協調新聞抓取、AI 分析與寄送 Email 的流程"""
    tw_tz = datetime.timezone(datetime.timedelta(hours=8))
    now_tw = datetime.datetime.now(tw_tz)
    is_evening = now_tw.hour >= 12
    edition_name = "晚報" if is_evening else "早報"
    
    intl_raw = fetch_top_international_news()
    car_raw = fetch_car_news()
    
    car_results = []
    for news in car_raw:
        # 💰 省錢關鍵：字數進一步縮減至 800 字
        zh_t, ana = ai_analyze_news(news.title, news.summary[:800], is_car=True)
        car_results.append({'title': zh_t, 'analysis': ana.replace('\n', '<br>'), 'source': news.custom_source, 'link': news.link})
        # 🚀 VIP 通道：享受付費版的 2 秒光速執行
        time.sleep(2) 
        
    intl_results = []
    for news in intl_raw:
        # 💰 省錢關鍵：字數進一步縮減至 800 字
        zh_t, ana = ai_analyze_news(news.title, news.summary[:800], is_car=False)
        intl_results.append({'title': zh_t, 'analysis': ana.replace('\n', '<br>'), 'source': news.custom_source, 'link': news.link})
        # 🚀 VIP 通道：享受付費版的 2 秒光速執行
        time.sleep(2) 

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
                print(f"✅ 成功寄送至：{sub['email']}")
        except Exception as e:
            print(f"❌ 寄送失敗：{e}")

if __name__ == "__main__":
    main()
