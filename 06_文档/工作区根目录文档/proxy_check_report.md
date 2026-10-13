# 北美线站点可访问性测试报告(经 Clash 代理)

测试时间: 2026/9/18 14:01:40 (北京时间)

- 代理: `http://127.0.0.1:7877` (Clash 混合端口,HTTP CONNECT 隧道)
- 方式: Node.js v24.19.0 内置 net/tls/https 手工建隧道,超时 40s,失败重试 2 次,并发 5,跟随重定向
- 出口 IP: `{"ip":"209.126.8.142"}`

| # | 线路 | 站点 | URL | 结论 | HTTP | 耗时 | 跳转后最终地址 | 页面标题 |
|---|------|------|-----|------|------|------|----------------|----------|
| 1 | 北美线-加拿大 | Amazon | https://www.amazon.ca/ | O 可访问 | 202 | 1.30s |  |  |
| 2 | 北美线-加拿大 | Brick | https://www.thebrick.com/ | O 可访问 | 200 | 4.98s |  | Furniture Store, Mattresses & Appliances - The Brick |
| 3 | 北美线-加拿大 | Costco | https://www.costco.ca/ | O 可访问 | 200 | 4.27s |  | Welcome to Costco Wholesale |
| 4 | 北美线-加拿大 | Leon's | https://www.leons.ca/ | O 可访问 | 200 | 4.09s |  | Leon&#39;s - Canada&#39;s Leading Furniture Store |
| 5 | 北美线-加拿大 | Walmart | https://www.walmart.ca/en | O 可访问 | 200 | 3.35s |  | Online Shopping Canada: Everyday Low Prices at Walmart.ca! |
| 6 | 北美线-美国 | Amazon | https://www.amazon.com | O 可访问 | 202 | 1.99s |  |  |
| 7 | 北美线-美国 | Costco | https://www.costco.com | O 可访问 | 200 | 5.19s |  | Welcome to Costco Wholesale |
| 8 | 北美线-美国 | Walmart | https://www.walmart.com | O 可访问 | 200 | 2.89s |  | Walmart \| Save Money. Live better. |
| 9 | 北美线-墨西哥 | Amazon | https://www.amazon.com.mx/ | O 可访问 | 202 | 1.53s |  |  |
| 10 | 北美线-墨西哥 | Liverpool | https://www.liverpool.com.mx/tienda/home | O 可访问 | 200 | 5.14s |  | Liverpool \| Fashion Fest \| Hasta 15% de descuento |
| 11 | 北美线-墨西哥 | Sams | https://www.sams.com.mx/ | △ 200 但疑似风控页 | 200 | 3.56s | https://www.sams.com.mx/blocked?url=Lw==&uuid=379ff13c-b326-11f1-a8e1-53e13382022c&vid=&g=b | Verify Your Identity |
| 12 | 北美线-墨西哥 | Walmart | https://www.walmart.com.mx/search?q=TV | △ 200 但疑似风控页 | 200 | 2.80s | https://www.walmart.com.mx/blocked?url=L3NlYXJjaD9xPVRW&uuid=38607d09-b326-11f1-8b09-cba0aa54a576&vid=&g=b | Verifica tu identidad |
| 13 | 北美线-加拿大 | BestBuy | https://www.bestbuy.ca/en-ca | △ 被拒 403 | 403 | 1.41s |  | Access Denied |
| 14 | 北美线-加拿大 | Canadian Tire | https://www.canadiantire.ca/en.html | △ 被拒 403 | 403 | 1.18s |  | Access Denied |
| 15 | 北美线-加拿大 | Visions | https://www.visions.ca/ | △ 被拒 403 | 403 | 1.25s |  | Just a moment... |
| 16 | 北美线-墨西哥 | Palacio | https://www.elpalaciodehierro.com/buscar?q=tv | △ 被拒 403 | 403 | 1.34s |  | Just a moment... |
| 17 | 北美线-美国 | Best Buy | https://www.bestbuy.com | X 失败 | ERR | - |  |  |
| 18 | 北美线-墨西哥 | Coppel | https://www.coppel.com/sd/TV | X 失败 | ERR | - |  |  |

## 明细

### 北美线-加拿大 / Amazon
- URL: https://www.amazon.ca/
- 结论: O 可访问
- HTTP: 202 Accepted   耗时: 1297ms   字节: 2007
- 响应头: server=CloudFront; content-type=text/html; charset=UTF-8; content-length=2007; x-amzn-waf-action=challenge

### 北美线-加拿大 / Brick
- URL: https://www.thebrick.com/
- 结论: O 可访问
- HTTP: 200 OK   耗时: 4979ms   字节: 420604
- 标题: Furniture Store, Mattresses & Appliances - The Brick
- 响应头: server=cloudflare; content-type=text/html; charset=utf-8

### 北美线-加拿大 / Costco
- URL: https://www.costco.ca/
- 结论: O 可访问
- HTTP: 200 OK   耗时: 4274ms   字节: 409594
- 标题: Welcome to Costco Wholesale
- 响应头: content-type=text/html; charset=utf-8; content-length=2874891

### 北美线-加拿大 / Leon's
- URL: https://www.leons.ca/
- 结论: O 可访问
- HTTP: 200 OK   耗时: 4095ms   字节: 420329
- 标题: Leon&#39;s - Canada&#39;s Leading Furniture Store
- 响应头: server=cloudflare; content-type=text/html; charset=utf-8

### 北美线-加拿大 / Walmart
- URL: https://www.walmart.ca/en
- 结论: O 可访问
- HTTP: 200 OK   耗时: 3354ms   字节: 304062
- 标题: Online Shopping Canada: Everyday Low Prices at Walmart.ca!
- 响应头: content-type=text/html; charset=utf-8

### 北美线-美国 / Amazon
- URL: https://www.amazon.com
- 结论: O 可访问
- HTTP: 202 Accepted   耗时: 1993ms   字节: 2007
- 响应头: server=CloudFront; content-type=text/html; charset=UTF-8; content-length=2007; x-amzn-waf-action=challenge

### 北美线-美国 / Costco
- URL: https://www.costco.com
- 结论: O 可访问
- HTTP: 200 OK   耗时: 5189ms   字节: 417321
- 标题: Welcome to Costco Wholesale
- 响应头: server=istio-envoy; content-type=text/html; charset=utf-8

### 北美线-美国 / Walmart
- URL: https://www.walmart.com
- 结论: O 可访问
- HTTP: 200 OK   耗时: 2890ms   字节: 398891
- 标题: Walmart | Save Money. Live better.
- 响应头: content-type=text/html; charset=utf-8

### 北美线-墨西哥 / Amazon
- URL: https://www.amazon.com.mx/
- 结论: O 可访问
- HTTP: 202 Accepted   耗时: 1530ms   字节: 2007
- 响应头: server=CloudFront; content-type=text/html; charset=UTF-8; content-length=2007; x-amzn-waf-action=challenge

### 北美线-墨西哥 / Liverpool
- URL: https://www.liverpool.com.mx/tienda/home
- 结论: O 可访问
- HTTP: 200 OK   耗时: 5141ms   字节: 418179
- 标题: Liverpool | Fashion Fest | Hasta 15% de descuento
- 响应头: content-type=text/html; charset=utf-8

### 北美线-墨西哥 / Sams
- URL: https://www.sams.com.mx/
- 结论: △ 200 但疑似风控页
- HTTP: 200 OK   耗时: 3557ms   字节: 11426
- 最终地址: https://www.sams.com.mx/blocked?url=Lw==&uuid=379ff13c-b326-11f1-a8e1-53e13382022c&vid=&g=b
- 重定向链: 307 https://www.sams.com.mx/  ->  200 https://www.sams.com.mx/blocked?url=Lw==&uuid=379ff13c-b326-11f1-a8e1-53e13382022c&vid=&g=b
- 标题: Verify Your Identity
- 响应头: content-type=text/html; charset=utf-8; content-length=11430

### 北美线-墨西哥 / Walmart
- URL: https://www.walmart.com.mx/search?q=TV
- 结论: △ 200 但疑似风控页
- HTTP: 200 OK   耗时: 2798ms   字节: 13595
- 最终地址: https://www.walmart.com.mx/blocked?url=L3NlYXJjaD9xPVRW&uuid=38607d09-b326-11f1-8b09-cba0aa54a576&vid=&g=b
- 重定向链: 307 https://www.walmart.com.mx/search?q=TV  ->  200 https://www.walmart.com.mx/blocked?url=L3NlYXJjaD9xPVRW&uuid=38607d09-b326-11f1-8b09-cba0aa54a576&vid=&g=b
- 标题: Verifica tu identidad
- 响应头: content-type=text/html; charset=utf-8; content-length=13599

### 北美线-加拿大 / BestBuy
- URL: https://www.bestbuy.ca/en-ca
- 结论: △ 被拒 403
- HTTP: 403 Forbidden   耗时: 1408ms   字节: 377
- 标题: Access Denied
- 响应头: content-type=text/html; content-length=377

### 北美线-加拿大 / Canadian Tire
- URL: https://www.canadiantire.ca/en.html
- 结论: △ 被拒 403
- HTTP: 403 Forbidden   耗时: 1180ms   字节: 384
- 标题: Access Denied
- 响应头: server=AkamaiGHost; content-type=text/html; content-length=384

### 北美线-加拿大 / Visions
- URL: https://www.visions.ca/
- 结论: △ 被拒 403
- HTTP: 403 Forbidden   耗时: 1246ms   字节: 5754
- 标题: Just a moment...
- 响应头: server=cloudflare; content-type=text/html; charset=UTF-8; content-length=5754; cf-mitigated=challenge

### 北美线-墨西哥 / Palacio
- URL: https://www.elpalaciodehierro.com/buscar?q=tv
- 结论: △ 被拒 403
- HTTP: 403 Forbidden   耗时: 1341ms   字节: 5813
- 标题: Just a moment...
- 响应头: server=cloudflare; content-type=text/html; charset=UTF-8; content-length=5813; cf-mitigated=challenge

### 北美线-美国 / Best Buy
- URL: https://www.bestbuy.com
- 结论: X 失败
- HTTP: 无响应   耗时: -   字节: 0
- 错误: `请求超时 > 40000ms`

### 北美线-墨西哥 / Coppel
- URL: https://www.coppel.com/sd/TV
- 结论: X 失败
- HTTP: 无响应   耗时: -   字节: 0
- 错误: `请求超时 > 40000ms`
