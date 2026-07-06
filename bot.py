import os
import time
import random
import hashlib
import json
import requests
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

# ==========================================
# ১. Environment Variables
# ==========================================
BOT_MONGO_URI = os.environ.get("BOT_MONGO_URI", "")
BOT_MONGO_DB_NAME = os.environ.get("BOT_MONGO_DB_NAME", "facebook_bot_db")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "")
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://boosting-service-agency.onrender.com").rstrip("/")

# 🟢 FIX 2: OpenRouter Setup (Multiple Lifetime Free Models Fallback)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_MODELS = [
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-7b-instruct:free",
    "huggingfaceh4/zephyr-7b-beta:free",
    "openchat/openchat-7b:free"
]

FB_GROUP_IDS_PROFILE_RAW = os.environ.get("FB_GROUP_IDS_PROFILE", "")
FB_GROUP_IDS_PAGE_RAW = os.environ.get("FB_GROUP_IDS_PAGE", "")

ACCOUNTS = []
for i in range(1, 6):
    c_user = os.environ.get(f"FB_C_USER_{i}")
    xs = os.environ.get(f"FB_XS_{i}")
    if c_user and xs and len(c_user) > 5 and len(xs) > 10 and c_user.strip() != "value":
        ACCOUNTS.append({"id": f"Account_{i}", "c_user": c_user, "xs": xs})

# ==========================================
# ২. Database Initialization
# ==========================================
bot_db, seen_posts_col = None, None
if MongoClient and BOT_MONGO_URI:
    try:
        bot_client = MongoClient(BOT_MONGO_URI, serverSelectionTimeoutMS=8000)
        bot_db = bot_client[BOT_MONGO_DB_NAME]
        seen_posts_col = bot_db["seen_posts"]
    except Exception: pass

# ==========================================
# ৩. OpenRouter AI & Helpers (Multiple Fallbacks)
# ==========================================
def generate_json_with_fallback(prompt):
    if not OPENROUTER_API_KEY: 
        send_telegram("⚠️ Debug Error: No OPENROUTER_API_KEY found for Hunter Bot! Please add it to GitHub Secrets.")
        return None
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}", 
        "Content-Type": "application/json"
    }
    
    system_prompt = 'You are a JSON assistant. You must output strictly valid JSON only in this format: {"status": "OK" or "IGNORE", "comment": "your comment", "inbox": "your inbox msg"}. Do not add any markdown formatting.'
    
    last_error = ""
    for model in OR_MODELS:
        data = {
            "model": model, 
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            res = requests.post(url, headers=headers, json=data, timeout=20)
            if res.status_code == 200:
                content = res.json()['choices'][0]['message']['content'].strip()
                if "```json" in content: content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content: content = content.split("```")[1].split("```")[0].strip()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    continue # JSON Parse fail hole porer model e try korbe
            else:
                last_error = res.text
                continue
        except Exception as e: 
            last_error = str(e)
            continue
            
    send_telegram(f"⚠️ OpenRouter Error: All models failed! Last Error: {last_error[:200]}")
    return None

def now_utc(): return datetime.now(timezone.utc)

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": message[:3900]}, timeout=10)
    except: pass

def human_like_mouse_move(page):
    try:
        page.mouse.move(random.randint(100, 1000), random.randint(100, 700), steps=random.randint(10, 30))
        time.sleep(random.uniform(0.5, 1.5))
    except: pass

# ==========================================
# ৪. ENGINE: Playwright Group Hunter
# ==========================================
def monitor_facebook_group(account):
    profile_groups = [g.strip() for g in FB_GROUP_IDS_PROFILE_RAW.split(",") if g.strip()]
    page_groups = [g.strip() for g in FB_GROUP_IDS_PAGE_RAW.split(",") if g.strip()]
    targets = [{"url": f"https://www.facebook.com/groups/{g}/", "mode": "profile"} for g in profile_groups]
    if account['id'] == "Account_1" and FB_PAGE_ID:
        for g in page_groups: targets.append({"url": f"https://www.facebook.com/groups/{g}/?av={FB_PAGE_ID}", "mode": "page"})

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, 
            args=[
                '--disable-dev-shm-usage', '--no-sandbox', '--disable-setuid-sandbox', 
                '--disable-blink-features=AutomationControlled', '--disable-gpu'
            ]
        ) 
        context = browser.new_context(viewport={'width': 800, 'height': 600}, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36')
        
        context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "media", "font", "script", "other"] else route.continue_())
        
        context.add_cookies([{"name": "c_user", "value": account['c_user'], "domain": ".facebook.com", "path": "/"}, {"name": "xs", "value": account['xs'], "domain": ".facebook.com", "path": "/"}])
        page = context.new_page()
        
        keywords = ["lagbe", "dorkar", "proyojon", "kinbo", "nibo", "chai", "follower", "dollar", "buy", "service", "boost", "ads", "লাগবে", "দরকার", "কিনবো", "চাই", "ফলোয়ার", "ডলার", "বুস্ট"]

        for target in targets:
            url, current_mode = target["url"], target["mode"]
            try:
                page.goto(url, timeout=60000) 
                time.sleep(random.uniform(3.5, 5.5))
                page.mouse.wheel(0, 500)
                time.sleep(random.uniform(2.5, 4.0))

                posts = page.locator('div[role="feed"] > div, div[data-pagelet*="FeedUnit"]').all()
                for post in posts[:3]: 
                    text = post.inner_text().lower()
                    if not any(w in text for w in keywords): continue

                    post_signature = f"{current_mode}_{hashlib.md5(text[:100].encode('utf-8')).hexdigest()}"
                    already_commented = is_first_comment = False
                    
                    if seen_posts_col is not None:
                        doc = seen_posts_col.find_one({"_id": post_signature})
                        if doc:
                            if current_mode == "page" or account['id'] in doc.get("commenters", []): already_commented = True
                            else: is_first_comment = False
                    
                    if already_commented: continue 

                    prompt = f"""Nicher facebook post poro. Follower, watchtime, boost kinte chaile "status" e "OK" likhbe. Irrelevant hole "IGNORE". Comment e inbox check korte bolbe. Post: '{text}'"""
                    ai_data = generate_json_with_fallback(prompt)
                    if not ai_data or ai_data.get("status") == "IGNORE": continue 
                        
                    if is_first_comment:
                        send_telegram(f"🔥 New Buyer Found!\n👤 Bot: {account['id']}\n💬 Post: {text[:150]}...\n🔗 Group Link: {url}")
                        
                    try:
                        human_like_mouse_move(page)
                        c_box = post.locator('div[aria-label*="comment"], div[role="textbox"]').first
                        c_box.scroll_into_view_if_needed()
                        time.sleep(1)
                        c_box.click()
                        time.sleep(1)
                        page.keyboard.type(ai_data.get('comment', ''), delay=50) 
                        page.keyboard.press("Enter")
                        time.sleep(3) 
                    except: pass

                    if current_mode == "profile":
                        try:
                            a_link = post.locator('a[role="link"][tabindex="0"]').first
                            if a_link.is_visible():
                                a_link.click()
                                time.sleep(4)
                                try:
                                    add_btn = page.locator('div[aria-label="Add friend"], div[aria-label="Add Friend"]').first
                                    if add_btn.is_visible(): add_btn.click()
                                except: pass
                                time.sleep(2)
                                try:
                                    msg_btn = page.locator('div[aria-label="Message"]').first
                                    if msg_btn.is_visible():
                                        msg_btn.click()
                                        time.sleep(3)
                                        page.keyboard.type(ai_data.get('inbox', ''), delay=50)
                                        page.keyboard.press("Enter")
                                        page.keyboard.press("Escape")
                                except: pass
                                page.go_back()
                                time.sleep(4)
                        except: page.go_back()
                    
                    if seen_posts_col is not None:
                        if is_first_comment: seen_posts_col.insert_one({"_id": post_signature, "commenters": [account['id']], "created_at": now_utc()})
                        else: seen_posts_col.update_one({"_id": post_signature}, {"$push": {"commenters": account['id']}})
                    break 
            except: pass
        browser.close()

# ==========================================
# ৫. Main Execution for GitHub Actions
# ==========================================
if __name__ == "__main__":
    send_telegram("🚀 GitHub Actions: BSA Hunter Bot Scan Started!")
    if ACCOUNTS:
        for account in ACCOUNTS:
            try: 
                monitor_facebook_group(account)
            except Exception: pass
            time.sleep(random.randint(15, 30))
    send_telegram("✅ GitHub Actions: Scan Complete. Bot going to sleep until next schedule.")
