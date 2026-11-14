"""
抹茶庫存 - 偵察版（只在手動按 Run workflow 時執行，只開第 1 款商品頁一次）
目的：找出「庫存數字」和「Taiwan 選項」到底是從哪裡載入的。
結果會分成 3 則通知傳到手機。
通知頻道名稱從 GitHub Secret「NTFY_TOPIC」讀取。
"""
import os
import re
import html as htmllib
import requests
from playwright.sync_api import sync_playwright

URL = "https://www.marukyu-koyamaen.co.jp/english/shop/products/1141020c1"
TOPIC = os.environ.get("NTFY_TOPIC", "")
IS_TEST = os.environ.get("IS_TEST") == "true"
OUT_RE = r"out\s*of\s*stock"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
           "Accept-Language": "en-US,en;q=0.9"}


def notify(text):
    if not TOPIC:
        print("沒有設定 NTFY_TOPIC")
        return
    data = text.encode("utf-8")[:3800].decode("utf-8", errors="ignore")
    try:
        requests.post(f"https://ntfy.sh/{TOPIC}", data=data.encode("utf-8"),
                      headers={"Priority": "high"}, timeout=15)
    except Exception as e:
        print("通知失敗：", e)


def static_scan():
    """不開瀏覽器，直接掃描網頁原始碼裡的線索"""
    r = requests.get(URL, headers=HEADERS, timeout=20)
    raw = htmllib.unescape(r.text)
    low = raw.lower()
    msg = [f"【1/3 原始碼掃描】H{r.status_code} 長度{len(raw)}"]
    hints = [k for k in ["wp-content", "woocommerce", "shopify", "__next",
                         "nuxt", "react", "vue", "jquery", "alpine", "stripe"]
             if k in low]
    msg.append("框架線索：" + (",".join(hints) or "無"))
    srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)', raw)[:8]
    msg.append("script檔：\n" + "\n".join(s[-70:] for s in srcs))
    calls = re.findall(r"(?:fetch\(|axios\.\w+\(|\$\.(?:ajax|get|post|getJSON)\("
                       r"|\.open\(['\"](?:GET|POST)['\"],)\s*[^;)]{0,100}", raw)[:6]
    msg.append("程式內的網路呼叫：\n" + ("\n".join(c[:110] for c in calls) or "無"))
    paths = sorted(set(re.findall(
        r"""["'](/[A-Za-z0-9_\-/\.]*(?:api|ajax|json|stock|inventory|shipping|"""
        r"""country|cart)[A-Za-z0-9_\-/\.\?=&%]*)["']""", raw)))[:10]
    msg.append("可疑路徑：\n" + ("\n".join(paths) or "無"))
    notify("\n".join(msg))


def browser_scan():
    """用瀏覽器開一次頁面，記錄它在背景叫了哪些資料"""
    xhrs = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"])
        ctx = b.new_context(user_agent=UA, locale="en-US",
                            viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        def on_resp(resp):
            try:
                if resp.request.resource_type in ("xhr", "fetch"):
                    xhrs.append(resp)
            except Exception:
                pass

        page.on("response", on_resp)
        resp = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        status = resp.status if resp else 0
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

        text = page.inner_text("body").replace("\xa0", " ").lower()
        n_out = len(re.findall(OUT_RE, text))
        n_tw = text.count("taiwan")
        snips = [text[max(0, m.start() - 40): m.end() + 40]
                 for m in list(re.finditer(r"stock", text))[:3]]
        try:
            inputs = page.eval_on_selector_all(
                "input, select",
                "els => els.slice(0,14).map(e => [e.tagName, e.name||'', "
                "e.type||'', e.max||'', e.value||''].join('/'))")
        except Exception:
            inputs = []
        notify(f"【2/3 瀏覽器看到的畫面】H{status} 文字長{len(text)} "
               f"缺貨字樣={n_out} 台灣={n_tw}\n輸入欄：{inputs}\n"
               f"stock附近：{snips}")

        lines = []
        for r in xhrs[:10]:
            try:
                body = r.text()
            except Exception:
                body = ""
            has = "stock" in body.lower() or "taiwan" in body.lower()
            lines.append(f"{r.status} {r.url[-95:]}\n   含stock/taiwan={'是' if has else '否'}"
                         f" 開頭:{body[:70].strip()!r}")
        notify(f"【3/3 背景資料請求】共{len(xhrs)}個\n" +
               ("\n".join(lines) or "沒有任何背景請求"))
        b.close()


def main():
    if not IS_TEST:
        print("偵察版：只有手動執行才會運作")
        return
    for fn in (static_scan, browser_scan):
        try:
            fn()
        except Exception as e:
            notify(f"{fn.__name__} 失敗：{str(e)[:300]}")


if __name__ == "__main__":
    main()
