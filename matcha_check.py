"""
抹茶庫存檢查（診斷版，不使用瀏覽器，速度快）
通知頻道名稱從 GitHub Secret「NTFY_TOPIC」讀取，不要寫在這個檔案裡。

這一版重點：把網頁裡的特殊空白（&nbsp;）和 HTML 符號還原後再找
"Out of stock"，並在測試時回報網頁裡「stock / quantity」附近的原文，
讓我們看清楚庫存資訊到底藏在哪裡。
"""
import os
import re
import html as htmllib
import time
import random
import requests

# 名稱: (商品頁網址, 基準值)    基準值先填 None，測試後再填數字
# 順序 = 檢查優先順序（越前面越先檢查）
BASE = "https://www.marukyu-koyamaen.co.jp/english/shop/products/"
PRODUCTS = {
    "雲鶴 Unkaku":          (BASE + "1141020c1", None),
    "金輪 Kinrin":          (BASE + "1151020c1", None),
    "和光 Wako":            (BASE + "1161020c1", None),
    "又玄 Yugen":           (BASE + "1171020c1", None),
    "五十鈴 Isuzu":         (BASE + "1191040c1", None),
    "青嵐 Aoarashi":        (BASE + "11a1040c1", None),
    "極長安 Kiwami Choan":  (BASE + "1g36020c1", None),
    "長安 Choan":           (BASE + "1121020c1", None),
    "千木の白 Chigi no Shiro": (BASE + "1181040c1", None),
}

# ======== 以下不用改 ========
TOPIC = os.environ.get("NTFY_TOPIC", "")
IS_TEST = os.environ.get("IS_TEST") == "true"

OUT_RE = r"out\s*of\s*stock"
BUY_WORDS = ["add to cart", "add to basket", "カートに入れる", "加入購物車"]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml",
           "Accept-Language": "en-US,en;q=0.9,ja;q=0.8"}
DEBUG_SNIPS = []


def notify(text, url=None):
    if not TOPIC:
        print("沒有設定 NTFY_TOPIC，無法通知")
        return
    headers = {"Priority": "high"}
    if url:
        headers["Click"] = url
    try:
        requests.post(f"https://ntfy.sh/{TOPIC}",
                      data=text.encode("utf-8"), headers=headers, timeout=15)
    except Exception as e:
        print("通知失敗：", e)


def clean(raw):
    """還原 HTML 符號與特殊空白，回傳 (含程式碼的小寫全文, 只留畫面文字)"""
    norm = htmllib.unescape(raw).replace("\xa0", " ").lower()
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", norm, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"about limited availability.*?as soon as possible\.?",
                  " ", text, flags=re.S)
    return norm, text


def snippets(norm, text):
    """測試用：擷取 stock / quantity 附近的原文"""
    out = []
    for m in list(re.finditer(r"stock", text))[:3]:
        out.append("文字:" + text[max(0, m.start() - 50): m.end() + 50])
    for m in list(re.finditer(r"<input[^>]{0,160}(?:quantity|qty)[^>]{0,160}>",
                              norm))[:2]:
        out.append("輸入框:" + m.group(0)[:220])
    for m in list(re.finditer(r"[^<>]{0,60}(?:out\s*of\s*stock|sold\s*out)"
                              r"[^<>]{0,40}", norm))[:2]:
        out.append("原碼:" + m.group(0).strip()[:120])
    return out


def check(url, baseline, first=False):
    """回傳 (狀態, 說明)。狀態 True=有貨, False=缺貨, None=無法判斷"""
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code in (403, 429, 503):
        return None, f"被網站擋下 (HTTP {r.status_code})"
    r.raise_for_status()
    norm, text = clean(r.text)

    n_out = len(re.findall(OUT_RE, text))
    n_out_all = len(re.findall(OUT_RE, norm))
    n_buy = sum(text.count(w) for w in BUY_WORDS)
    n_tw = norm.count("taiwan")
    info = f"缺貨字樣={n_out}個, 購買字樣={n_buy}個"
    if IS_TEST:
        info += f" | H{r.status_code} L{len(r.text)} 含程式碼缺貨={n_out_all} 台灣={n_tw}"
        if first:
            DEBUG_SNIPS.extend(snippets(norm, text))

    if len(text) < 200:
        return None, "頁面幾乎沒有內容（可能被擋）；" + info
    if baseline is not None:
        if n_out < baseline:
            return True, f"缺貨字樣減少了！{info}（基準{baseline}）"
        return False, f"全部缺貨；{info}（基準{baseline}）"
    if n_buy > 0:
        return True, "（未設基準，暫以有購買字樣判斷）" + info
    if n_out > 0:
        return False, "（未設基準）" + info
    return None, "看不出庫存狀態；" + info


def main():
    lines = []
    for i, (name, (url, baseline)) in enumerate(PRODUCTS.items()):
        if i > 0:
            time.sleep(random.uniform(2, 5))
        try:
            status, why = check(url, baseline, first=(i == 0))
        except Exception as e:
            status, why = None, f"讀取失敗 ({str(e)[:80]})"
        label = {True: "有貨！", False: "缺貨", None: "無法判斷"}[status]
        print(f"{name}: {label} - {why}")
        lines.append(f"{name}: {label}\n  {why}")
        if status is True:
            notify(f"🍵 有貨了！{name}\n趕快下單：{url}", url)
    if IS_TEST:
        notify("測試結果 ✅（診斷版）\n" + "\n".join(lines))
        if DEBUG_SNIPS:
            notify("第1款網頁原文片段：\n" + "\n".join(DEBUG_SNIPS))
        else:
            notify("第1款網頁原文片段：找不到 stock 或數量輸入框相關文字")


if __name__ == "__main__":
    main()
