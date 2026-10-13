"""Amazon 可行性最小探测：只发少量请求，判断反爬响应与目标字段可取性。

不做批量抓取，仅用于可行性评估：
1) 搜索页是否可达 / 是否触发机器人校验
2) 商品详情页是否可达
3) 型号（Product details）与评价（reviews）元素是否存在
"""
from __future__ import annotations

import sys
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BOT_MARKERS = ("robot check", "enter the characters you see below", "sorry! something went wrong",
               "api-services-support@amazon.com", "captcha", "not a robot")

SEARCH = "https://www.amazon.ca/s?k=hisense+tv"


def check_bot(title: str, body: str) -> str:
    low = (title + " " + body[:6000]).lower()
    hits = [m for m in BOT_MARKERS if m in low]
    return ", ".join(hits)


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, locale="en-CA",
                            viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()

        # ---- 1) 搜索页 ----
        print("=== 1) 搜索页 ===")
        try:
            r = pg.goto(SEARCH, wait_until="domcontentloaded", timeout=40000)
            status = r.status if r else None
            title = (pg.title() or "").strip()
            body = pg.content()
            bot = check_bot(title, body)
            print(f"HTTP={status}  标题={title[:70]!r}")
            print(f"机器人校验={bot or '无'}")
            cards = pg.locator('div[data-asin]:not([data-asin=""])')
            n = cards.count()
            print(f"检索结果卡片数={n}")
            first_url = None
            asins = []
            for i in range(min(n, 30)):
                a = cards.nth(i).get_attribute("data-asin") or ""
                if a.strip():
                    asins.append(a.strip())
            print(f"提取到 ASIN 数={len(asins)}  样例={asins[:5]}")
            if asins:
                first_url = f"https://www.amazon.ca/dp/{asins[0]}"
            print(f"首个商品链接={(first_url or '未取到')[:110]}")
        except Exception as e:
            print(f"搜索页失败：{type(e).__name__}: {str(e).splitlines()[0][:120]}")
            first_url = None

        # ---- 2) 商品详情页 ----
        if first_url:
            print("\n=== 2) 商品详情页 ===")
            pg2 = ctx.new_page()
            try:
                r2 = pg2.goto(first_url, wait_until="domcontentloaded", timeout=40000)
                status2 = r2.status if r2 else None
                title2 = (pg2.title() or "").strip()
                body2 = pg2.content()
                bot2 = check_bot(title2, body2)
                print(f"HTTP={status2}  标题={title2[:70]!r}")
                print(f"机器人校验={bot2 or '无'}")

                def has(sel: str) -> int:
                    try:
                        return pg2.locator(sel).count()
                    except Exception:
                        return -1

                print("\n-- 目标字段可取性 --")
                print(f"商品标题 #productTitle            : {has('#productTitle')}")
                print(f"技术规格表 #productDetails_techSpec_section_1: {has('#productDetails_techSpec_section_1')}")
                print(f"详情要点 #detailBullets_feature_div : {has('#detailBullets_feature_div')}")
                print(f"型号关键字(Item model number)出现 : {'是' if 'item model number' in body2.lower() else '否'}")
                print(f"评分 #acrCustomerReviewText        : {has('#acrCustomerReviewText')}")
                print(f"评价条目 [data-hook=review]        : {has('[data-hook=\"review\"]')}")
                print(f"评价区 #reviewsMedley              : {has('#reviewsMedley')}")

                t = pg2.locator("#productTitle").first
                if t.count():
                    print(f"\n实际标题文本: {(t.inner_text() or '').strip()[:80]!r}")
                # 型号：从详情要点里定位 Item model number
                try:
                    db = pg2.locator("#detailBullets_feature_div").first.inner_text()
                    for line in db.splitlines():
                        if "model number" in line.lower():
                            print(f"实际型号行  : {line.strip()[:80]!r}")
                            break
                except Exception:
                    pass
            except Exception as e:
                print(f"详情页失败：{type(e).__name__}: {str(e).splitlines()[0][:120]}")
            finally:
                pg2.close()

        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
