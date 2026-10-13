# 北美线 18 站点可访问性测试报告(经 Clash 代理)

测试时间: 2026/9/18 14:24:18 (北京时间)

## 测试环境

| 项目 | 值 |
|------|-----|
| 代理 | Clash Plus 混合端口 `127.0.0.1:7877`(HTTP CONNECT 隧道) |
| 出站模式 | global(全局) |
| 出口 IP | `209.126.8.142` — Contabo Inc., St. Louis, Missouri, US(机房 IP) |
| 客户端 | Node.js v24 内置 net/tls/http2,ALPN 协商 h2,Chrome 131 请求头 |
| 超时/重试 | 45s / 2 次,并发 5 |

## 结果总表

| # | 线路 | 站点 | URL | 结论 | HTTP | 耗时 | 页面标题 |
|---|------|------|-----|------|------|------|----------|
| 1 | 北美线-加拿大 | Brick | https://www.thebrick.com/ | ✅ 正常访问 | 200 | 10.7s | Furniture Store, Mattresses & Appliances - The Brick |
| 2 | 北美线-加拿大 | Canadian Tire | https://www.canadiantire.ca/en.html | ✅ 正常访问 | 200 | 3.6s | Shop Canada’s Top Department Store Online &amp; at 500+ Locations \| Canadian Tire |
| 3 | 北美线-加拿大 | Costco | https://www.costco.ca/ | ✅ 正常访问 | 200 | 33.9s | Welcome to Costco Wholesale |
| 4 | 北美线-加拿大 | Leon's | https://www.leons.ca/ | ✅ 正常访问 | 200 | 4.7s | Leon&#39;s - Canada&#39;s Leading Furniture Store |
| 5 | 北美线-美国 | Costco | https://www.costco.com | ✅ 正常访问 | 200 | 17.2s | Welcome to Costco Wholesale |
| 6 | 北美线-美国 | Walmart | https://www.walmart.com | ✅ 正常访问 | 200 | 4.3s | Walmart \| Save Money. Live better. |
| 7 | 北美线-墨西哥 | Coppel | https://www.coppel.com/sd/TV | ✅ 正常访问 | 200 | 4.7s | Compra placeholder al mejor precio en Coppel.com |
| 8 | 北美线-墨西哥 | Liverpool | https://www.liverpool.com.mx/tienda/home | ✅ 正常访问 | 200 | 40.6s | Liverpool \| Fashion Fest \| Hasta 15% de descuento |
| 9 | 北美线-墨西哥 | Palacio | https://www.elpalaciodehierro.com/buscar?q=tv | ✅ 正常访问 | 200 | 16.8s | Encuentra lo Mejor en tv \| El Palacio de Hierro |
| 10 | 北美线-加拿大 | Walmart | https://www.walmart.ca/en | ⚠️ 疑似空壳/挑战页(可见文本过少) | 200 | 3.4s | Online Shopping Canada: Everyday Low Prices at Walmart.ca! |
| 11 | 北美线-美国 | Best Buy | https://www.bestbuy.com | ⚠️ 疑似空壳/挑战页(可见文本过少) | 200 | 5.0s | Best Buy \| Official Online Store \| Shop Now &amp; Save |
| 12 | 北美线-加拿大 | Amazon | https://www.amazon.ca/ | ⚠️ AWS WAF JS 挑战页 | 202 | 1.2s |  |
| 13 | 北美线-美国 | Amazon | https://www.amazon.com | ⚠️ AWS WAF JS 挑战页 | 202 | 1.2s |  |
| 14 | 北美线-墨西哥 | Amazon | https://www.amazon.com.mx/ | ⚠️ AWS WAF JS 挑战页 | 202 | 1.3s |  |
| 15 | 北美线-加拿大 | Visions | https://www.visions.ca/ | ⚠️ Cloudflare 人机验证页 | 403 | 2.1s | Just a moment... |
| 16 | 北美线-墨西哥 | Sams | https://www.sams.com.mx/ | ⚠️ 风控/身份验证页 | 200 | 3.2s | Verify Your Identity |
| 17 | 北美线-墨西哥 | Walmart | https://www.walmart.com.mx/search?q=TV | ⚠️ 风控/身份验证页 | 200 | 2.6s | Verifica tu identidad |
| 18 | 北美线-加拿大 | BestBuy | https://www.bestbuy.ca/en-ca | ❌ 403 拒绝访问 | 403 | 1.3s | Access Denied |

## 明细

### [O] 北美线-加拿大 / Brick
- URL: https://www.thebrick.com/
- HTTP: 200 | 耗时: 10678ms | ALPN: h2 | 字节: 613952 | 可见文本: 38339
- 标题: Furniture Store, Mattresses & Appliances - The Brick
- 判定: 正常访问
- 可见文本开头: Furniture Store, Mattresses & Appliances - The Brick Skip to Main Content Living Room Mattresses Bedroom Dining Room Appliances Electronics Office Home Decor Small Spaces Outdoor Sale Last Chance Flyer Inspiration Gift R

### [O] 北美线-加拿大 / Canadian Tire
- URL: https://www.canadiantire.ca/en.html
- HTTP: 200 | 耗时: 3622ms | ALPN: h2 | 字节: 454694 | 可见文本: 128298
- 标题: Shop Canada’s Top Department Store Online &amp; at 500+ Locations | Canadian Tire
- 判定: 正常访问
- 可见文本开头: Shop Canada’s Top Department Store Online & at 500+ Locations | Canadian Tire Skip to main content Skip to navigation &lt;b>YOU&#39;RE BROWSING IN VIEW-ONLY MODE DUE TO SCHEDULED MAINTENANCE.&lt;/b>&lt;/p>\r\n&lt;p>Onlin

### [O] 北美线-加拿大 / Costco
- URL: https://www.costco.ca/
- HTTP: 200 | 耗时: 33895ms | ALPN: h2 | 字节: 622556 | 可见文本: 12634
- 标题: Welcome to Costco Wholesale
- 判定: 正常访问
- 可见文本开头: Welcome to Costco Wholesale Skip to Main Content Uber 2 x$50 gift cards — Shop now. Treasure Hunt Offers Ending Sunday What&#x27;s New Online Deals Warehouse Savings Get Email Offers Customer Service CA EN Treasure Hunt 

### [O] 北美线-加拿大 / Leon's
- URL: https://www.leons.ca/
- HTTP: 200 | 耗时: 4739ms | ALPN: h2 | 字节: 552482 | 可见文本: 6047
- 标题: Leon&#39;s - Canada&#39;s Leading Furniture Store
- 判定: 正常访问
- 可见文本开头: Leon&#39;s - Canada&#39;s Leading Furniture Store Skip to Main Content Warning Unsupported Browser Warning Leons.ca may not function properly on Internet Explorer. To get the best experience on our site, please update to

### [O] 北美线-美国 / Costco
- URL: https://www.costco.com
- HTTP: 200 | 耗时: 17180ms | ALPN: h2 | 字节: 622568 | 可见文本: 22616
- 标题: Welcome to Costco Wholesale
- 判定: 正常访问
- 可见文本开头: Welcome to Costco Wholesale Skip to Main Content Uber - Two $50 eGift Cards - $79.99 While Supplies Last Online-Only Treasure Hunt What&#x27;s New Member Favorites Recommendations for You Get Email Offers Customer Servic

### [O] 北美线-美国 / Walmart
- URL: https://www.walmart.com
- HTTP: 200 | 耗时: 4293ms | ALPN: h2 | 字节: 363405 | 可见文本: 1491
- 标题: Walmart | Save Money. Live better.
- 判定: 正常访问
- 可见文本开头: Walmart | Save Money. Live better. Skip to Main Content Pickup or delivery? Cancel Reorder My Items Reorder Lists Registries Sign In Account Sign in or create account Purchase History Walmart+ Subscriptions Language | En

### [O] 北美线-墨西哥 / Coppel
- URL: https://www.coppel.com/sd/TV
- HTTP: 200 | 耗时: 4737ms | ALPN: h2 | 字节: 408300 | 可见文本: 2027
- 标题: Compra placeholder al mejor precio en Coppel.com
- 判定: 正常访问
- 可见文本开头: Compra placeholder al mejor precio en Coppel.com Saltar al contenido principal ¡Anímate a consentirte con las increíbles ofertas!🏷️ Descúbrelas MENÚ Iniciar sesión Crear cuenta Carrito Compra ahora +52 559 500 0001 Elig

### [O] 北美线-墨西哥 / Liverpool
- URL: https://www.liverpool.com.mx/tienda/home
- HTTP: 200 | 耗时: 40569ms | ALPN: h2 | 字节: 625969 | 可见文本: 212759
- 标题: Liverpool | Fashion Fest | Hasta 15% de descuento
- 判定: 正常访问
- 可见文本开头: Liverpool | Fashion Fest | Hasta 15% de descuento Elige una tienda Elige una tienda Servicios Servicios keyboard_arrow_down Viajes y vacaciones chevron_right Tiempo aire Centro de seguros Diseño de interiores chevron_rig

### [O] 北美线-墨西哥 / Palacio
- URL: https://www.elpalaciodehierro.com/buscar?q=tv
- HTTP: 200 | 耗时: 16775ms | ALPN: h2 | 字节: 615131 | 可见文本: 16072
- 标题: Encuentra lo Mejor en tv | El Palacio de Hierro
- 判定: 正常访问
- 可见文本开头: Encuentra lo Mejor en tv | El Palacio de Hierro card-icon Ir al contenido principal Ir al contenido de pie de p&aacute;gina Tarjeta Palacio Servicios Palacio MI PALACIO APP Seguros Palacio Gastronomía Palacio Viajes Pala

### [E] 北美线-加拿大 / Walmart
- URL: https://www.walmart.ca/en
- HTTP: 200 | 耗时: 3440ms | ALPN: h2 | 字节: 304067 | 可见文本: 3854
- 标题: Online Shopping Canada: Everyday Low Prices at Walmart.ca!
- 判定: 疑似空壳/挑战页(可见文本过少)
- 可见文本开头: Online Shopping Canada: Everyday Low Prices at Walmart.ca! Skip to Main Content How do you want your items? Cancel Language English English Français Reorder My Items Reorder Lists Registries Sign In Account Sign in or cr

### [E] 北美线-美国 / Best Buy
- URL: https://www.bestbuy.com
- HTTP: 200 | 耗时: 5015ms | ALPN: h2 | 字节: 430691 | 可见文本: 748
- 标题: Best Buy | Official Online Store | Shop Now &amp; Save
- 判定: 疑似空壳/挑战页(可见文本过少)
- 可见文本开头: Best Buy | Official Online Store | Shop Now & Save $(csi.user.businessName) Main Content . . . . . . . . . . . . . . . . . . . Skip to content Go to Product Search Go to Footer . . Top quality. Even better prices. We ins

### [A] 北美线-加拿大 / Amazon
- URL: https://www.amazon.ca/
- HTTP: 202 | 耗时: 1156ms | ALPN: h2 | 字节: 2007 | 可见文本: 0
- 标题: (空)
- 判定: AWS WAF JS 挑战页

### [A] 北美线-美国 / Amazon
- URL: https://www.amazon.com
- HTTP: 202 | 耗时: 1212ms | ALPN: h2 | 字节: 2007 | 可见文本: 0
- 标题: (空)
- 判定: AWS WAF JS 挑战页

### [A] 北美线-墨西哥 / Amazon
- URL: https://www.amazon.com.mx/
- HTTP: 202 | 耗时: 1262ms | ALPN: h2 | 字节: 2007 | 可见文本: 0
- 标题: (空)
- 判定: AWS WAF JS 挑战页

### [C] 北美线-加拿大 / Visions
- URL: https://www.visions.ca/
- HTTP: 403 | 耗时: 2141ms | ALPN: h2 | 字节: 5925 | 可见文本: 16
- 标题: Just a moment...
- 判定: Cloudflare 人机验证页
- 可见文本开头: Just a moment...

### [B] 北美线-墨西哥 / Sams
- URL: https://www.sams.com.mx/
- 重定向链: 307 https://www.sams.com.mx/ → 200 https://www.sams.com.mx/blocked?url=Lw==&uuid=7bd6c1b3-b329-11f1-ba88-040eedac65d8&vid=&g=b
- HTTP: 200 | 耗时: 3172ms | ALPN: h2 | 字节: 11426 | 可见文本: 106
- 标题: Verify Your Identity
- 判定: 风控/身份验证页
- 可见文本开头: Verify Your Identity Verifica tu identidad Mantén presionado el botón para confirmar que no eres un robot.

### [B] 北美线-墨西哥 / Walmart
- URL: https://www.walmart.com.mx/search?q=TV
- 重定向链: 307 https://www.walmart.com.mx/search?q=TV → 200 https://www.walmart.com.mx/blocked?url=L3NlYXJjaD9xPVRW&uuid=7dc6c186-b329-11f1-961b-6a8ff2df7f40&vid=&g=b
- HTTP: 200 | 耗时: 2552ms | ALPN: h2 | 字节: 13595 | 可见文本: 121
- 标题: Verifica tu identidad
- 判定: 风控/身份验证页
- 可见文本开头: Verifica tu identidad wm-logo-white Verifica tu identidad Mantén presionado el botón para confirmar que no eres un robot.

### [D] 北美线-加拿大 / BestBuy
- URL: https://www.bestbuy.ca/en-ca
- HTTP: 403 | 耗时: 1308ms | ALPN: h2 | 字节: 526 | 可见文本: 297
- 标题: Access Denied
- 判定: 403 拒绝访问
- 可见文本开头: Access Denied Access Denied You don't have permission to access "http&#58;&#47;&#47;www&#46;bestbuy&#46;ca&#47;en&#45;ca" on this server. Reference&#32;&#35;18&#46;d41c2117&#46;1789712606&#46;12f842df https&#58;&#47;&#47
