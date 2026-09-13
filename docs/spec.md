# 免费外链位置库 —— 项目方案 v1

> 本文档是交付给 Claude Code 的实施说明。
> **只实施「第一阶段」。第二、三阶段写在这里是为了让实施者理解数据结构为什么这样设计，不要提前动工。**

---

## 一、这个项目到底是什么

**不是**「免费外链网站大全清单」。市面上有一百个，全是死的。

**是**一个由真人每天实操验证、带存活数据的外链位置库。核心资产不是「哪里能发」这个名单，而是：

- 这条位置**现在**还活不活（最后验证时间）
- 发上去的链接 90 天后还在不在（存活率）
- 那个页面 Google 收不收（收录率）
- 投 10 篇过几篇、等几天（过审率 / 平均耗时）
- **它在第几步坑你**（这一条最值钱，见下）

名单会被抄、会过期、会因为公开而被灌爆。**存活数据不会**，因为它只能靠人天天发才能产生。

---

## 二、已经论证过的关键结论（实施时不要推翻）

### 2.1 清单会因为成功而自毁

免费发文位置有容量上限。一个位置被大量分发，站长几天内就会加验证码 / 关注册 / 开人工审核。所以：

- **绝不提供全量 dump 下载**
- 对外只走接口：agent 请求「niche X 的下 N 个可用位置」，服务端控制分发速率、轮换库存、同站限流
- 目录收录类渠道是例外（见 2.4），可以公开

### 2.2 「能免费自助发」和「链接有效」高度负相关

一个站若允许陌生人无审核放 dofollow 链接，Google 大概率早已清零它的外链权重。

因此本产品的真实买家是 **KPI 按提交数考核的人**（外包 SEO、执行岗、代运营），不是追求排名效果的人。这是「交作业市场」，不是「做效果市场」。产品文案、定价、渠道都按这个定位。**不要在任何地方承诺排名提升。**

### 2.3 D 桶（假免费）是不会自毁的资产

四桶分类：

| 桶 | 含义 | 特征 |
|---|---|---|
| **A** | 即时自助 | 注册即发，无审核或秒过 |
| **B** | 快审 | 几天到两周出结果 |
| **C** | 慢队列 | 几周以上，投了就等 |
| **D** | 假免费 | 最终要钱 / 要排一年 / 表格填完发现是漏斗 |

A/B/C 是易腐库存。**D 桶永久有效**：公开「这 18 个站是坑、坑在第几步、要交多少钱、要等多久」，没人能把它灌爆，站长也不会因为被点名就变免费。

D 桶同时是天然 SEO 内容：`is ___ guest post free`、`___ write for us cost`、`___ write for us scam` 这类长尾，正是被坑的人会搜的。

**C 桶不算损失**，投了就扔进「待开花」池，一年后自己会亮。只是不计入当天 KPI —— 日报和资产库是两本账。

### 2.4 按「渠道类型」组织，不是按「网站清单」

同一个 niche 下先分渠道，每种渠道的成本 / 周期 / 存活率 / 是否 dofollow 完全不同：

| 渠道类型 | 典型例子 | 怕不怕公开 |
|---|---|---|
| `directory` 目录收录 | AlternativeTo、SaaSHub、Product Hunt、Slant、Toolify、awesome-* 列表 | **不怕**，收录站本来就要收录 |
| `guest_post` 投稿 | write for us / contribute 页 | 怕，走接口控速 |
| `forum` 论坛社区 | Discourse / phpBB / XenForo / 垂类论坛 | 中等 |
| `resource_page` 资源页 | "best free X tools" roundup | 中等 |
| `community_answer` 社区回答 | Reddit、Quora | 不怕 |
| `expert_quote` 专家引述 | HARO 一路 | 不怕 |
| `comment` 评论 | 开放评论区 | 低价值，多为 nofollow |

用户真正要问的是「我这类站，最快拿到链接的路子是哪条」，站点清单是答案的第二层。

**目录收录类可以做成免费公开内容拉流量，投稿类放在接口后面控速分发。**

### 2.5 三个垂类地形完全不同

| 垂类 | 主渠道 | 判断 |
|---|---|---|
| **工具站** | `directory` 为主，不是投稿 | 最好打，位置免费永久不怕公开，录用标准是「工具真能用」 |
| **旅游** | `guest_post` + `forum` + `resource_page` | 真·免费投稿存量最大，D 桶占比应最低 |
| **医疗（proivf.com）** | 只剩患者社区 / 机构目录 / 社区回答 / 专家引述 | **YMYL。肯让陌生人免费放 dofollow 的健康站基本已被判定不可信，发了可能反噬** |

**第一阶段只做工具站垂类。** 旅游第二阶段。医疗单独处理，很可能验完发现可用位置是个位数 —— 那就诚实做成「劝退报告」，同样有价值。

**不要按这三个垂类外推到十二个垂类。** 没有一手数据的垂类只能抄别人的死清单，那就退化成第 101 个「免费外链大全」。

### 2.6 淘汰点必须前移

当前工作流的病：把最贵的动作（注册、填表）放在最便宜的判断（收不收钱、要不要排队）前面。

**注册之前必须先跑三查**，任一命中即归 D 桶，不进注册。

### 2.7 记录层必须无痛

人在赶量的时候不会去填表。**记录动作必须压缩到 10 秒内完成**，字段固定。记录层如果不是近乎自动的，数据就攒不起来，整个项目的核心资产就不存在。

**这是第一阶段最高优先级，高于探测器。**

---

## 三、第一阶段实施范围

### 要做的

1. 记录层（CLI + 本地库，10 秒完成一次记录）
2. 探测器（批量跑域名，输出四桶预判 + 依据）
3. 复检任务（定期自动验证库存是否还活着）

### 明确不做的

- 对外网站、落地页、定价页
- 用户系统、付费、接口鉴权
- 旅游 / 医疗垂类
- 任何前端美化

现在做这些都是在没有数据的情况下装修。

### 技术要求

- 本地优先，SQLite。不要上云、不要 Docker、不要微服务
- Python，单仓库，`uv` 或 venv 皆可
- 全部功能可通过 CLI 调用；探测器可并发（默认并发 8，可配置）
- 所有网络请求带 UA、超时 10s、失败重试 1 次、结果落库不抛异常中断批次
- **不要写爬虫绕过验证码或反爬。遇到 403 / Cloudflare 就如实记录状态，交给人处理**

---

## 四、数据模型

```sql
-- 站点主表：一个域名一行
CREATE TABLE sites (
  id INTEGER PRIMARY KEY,
  domain TEXT UNIQUE NOT NULL,
  niche TEXT,                    -- tools / travel / medical / ...
  channel_type TEXT,             -- directory / guest_post / forum / resource_page / community_answer / expert_quote / comment
  bucket TEXT,                   -- A / B / C / D / unknown
  bucket_reason TEXT,            -- 归到这个桶的原因，人话，一句
  entry_url TEXT,                -- 实际投稿/提交入口
  needs_register INTEGER,        -- 0/1
  captcha_type TEXT,             -- none / recaptcha / hcaptcha / cloudflare / email_verify / unknown
  is_dofollow INTEGER,           -- 0/1/null
  cost_note TEXT,                -- D 桶专用：要多少钱 / 要等多久
  source TEXT,                   -- 这个域名从哪来的
  first_seen TEXT,
  last_verified TEXT,            -- 最后一次人工或自动验证时间
  notes TEXT
);

-- 探测结果：每次跑探测器写一行，保留历史
CREATE TABLE probes (
  id INTEGER PRIMARY KEY,
  site_id INTEGER REFERENCES sites(id),
  probed_at TEXT,
  paths_found TEXT,              -- JSON，命中的路径及状态码
  latest_author_post TEXT,       -- 最新外部署名文章日期，核心指标
  has_pricing_page INTEGER,      -- 是否存在 /advertise /pricing /sponsored
  contact_email_type TEXT,       -- editorial / commercial / unknown
  marketplace_hit TEXT,          -- 在哪个外链市场查到报价
  platform TEXT,                 -- wordpress / discourse / phpbb / xenforo / ghost / unknown
  predicted_bucket TEXT,         -- 探测器预判
  predict_confidence REAL,
  raw TEXT                       -- JSON，原始信号，方便后期调规则
);

-- 投递记录：每投一次写一行
CREATE TABLE attempts (
  id INTEGER PRIMARY KEY,
  site_id INTEGER REFERENCES sites(id),
  target_site TEXT,              -- 给哪个站发的（proivf.com / 工具站 / ...）
  submitted_at TEXT,
  status TEXT,                   -- submitted / approved / rejected / published / no_response
  status_at TEXT,
  live_url TEXT,                 -- 成品链接
  time_cost_min INTEGER,         -- 这次花了多少分钟，用来算 ROI
  notes TEXT
);

-- 存活复检：对已发布链接定期检查
CREATE TABLE link_checks (
  id INTEGER PRIMARY KEY,
  attempt_id INTEGER REFERENCES attempts(id),
  checked_at TEXT,
  http_status INTEGER,
  link_present INTEGER,          -- 页面上还有没有我们的链接
  rel_attr TEXT,                 -- dofollow / nofollow / ugc / sponsored
  indexed INTEGER                -- Google 收不收，可选，先留字段
);
```

---

## 五、探测器规则

对一个域名，按顺序跑以下信号。**任一 D 信号命中，直接归 D，不再往下跑**（省流量也省人的时间）。

### 5.1 D 信号（一票归 D）

| 信号 | 检测方式 |
|---|---|
| 存在商业化页面 | HEAD `/advertise` `/advertising` `/pricing` `/sponsored` `/sponsored-post` `/media-kit` 返回 200 |
| 投稿页含收费词 | 抓 entry 页正文，命中 `contribution fee` / `processing fee` / `we charge` / `paid guest post` / `$` 附近出现 post/article |
| 联系邮箱是商务型 | 页面邮箱前缀属于 `seo@` `partnerships@` `marketing@` `sales@` `bd@` |
| 外链市场有报价 | 域名命中 Collaborator / Adsy / PRPosting / Getfluence 的公开目录（先做成本地可维护的域名黑名单文件，抓取靠后再说） |

### 5.2 排队信号（倾向 C）

- 投稿指南含 `editorial calendar` / `plan content 3 months` / `allow 4-6 weeks` / `we are currently at capacity`
- 表单要求 `portfolio` / `writing samples` / `previously published`
- 要求先交 outline 再审、最低字数 ≥ 1500、必须独家原创

### 5.3 活跃度信号（核心，决定 A/B/C）

**这一条比任何页面自述都准，因为它是结果证据不是政策声明。**

抓「最新外部作者署名文章日期」：
- `site:域名 inurl:author/`
- 投稿分类页 / tag 页的最新文章日期
- sitemap 中 author 或 contributor 相关 URL 的 lastmod

判定：

| 最新署名文章 | 判定 |
|---|---|
| 30 天内 | 通道活着，倾向 A/B |
| 30–180 天 | 倾向 C |
| > 180 天 或 查不到 | 通道大概率已死，标 `stale`，**不进人工队列** |

> 注意：路径返回 200 只证明页面存在，**署名时间戳才证明通道通着**。不要把路径探测当核心指标。

### 5.4 平台指纹（决定难易度）

识别 Discourse / phpBB / XenForo / WordPress 开放评论 / Ghost。命中论坛类平台 → 注册即可发，通常归 A。

### 5.5 路径探测清单

```
/write-for-us  /write-for-us/  /writeforus
/guest-post  /guest-posts  /guest-posting  /guest-blogging
/contribute  /contributors  /contribution-guidelines
/submit  /submit-post  /submit-article  /submit-url  /submit-link  /submit-tool
/add-url  /add-listing  /add-your-site  /add-tool
/become-a-contributor  /editorial-guidelines  /submission-guidelines
/advertise  /pricing  /sponsored  /media-kit          # 这四条是 D 信号
/register  /signup  /join
```

### 5.6 输出

探测器最终对每个域名输出三列，这是给人看的：

**能不能发 / 走哪个入口 / 值不值得发**

外加 `predicted_bucket` 与依据。**探测器只做预判，最终桶位由人工确认后写回 `sites.bucket`。**

---

## 六、CLI 接口

```bash
# 1. 导入域名池
bl import domains.txt --niche tools --source "alternativeto-competitors"

# 2. 批量探测（第一阶段最常用）
bl probe --niche tools --limit 200 --concurrency 8

# 3. 看今天该人工处理哪些（探测器筛剩下的）
bl queue --niche tools --exclude-bucket D --exclude-stale

# 4. 记录一次投递 —— 必须 10 秒内完成
bl log example.com --entry /write-for-us --register --captcha recaptcha \
   --status submitted --target proivf.com --time 12
#    交互式补问缺失字段，全部可用单键选择，不要让她打字

# 5. 更新投递结果
bl update <attempt_id> --status published --url https://...

# 6. 复检：所有已发布链接是否还活着
bl recheck --older-than 30d

# 7. 库存复检：投稿入口是否还开着（死的自动降级为 stale）
bl revalidate --older-than 14d

# 8. 出数
bl stats --niche tools
#    输出：四桶占比 / 过审率 / 平均耗时 / 90天存活率 / 每条链接平均耗时
```

**`bl log` 的体验是整个项目的成败点。** 要求：单条命令 + 交互补全，全程单键选择，不打字，5–10 秒结束。如果做出来需要填 30 秒，这个项目的数据就攒不起来。

---

## 七、验收标准

第一阶段做完时，必须能做到：

1. 丢进 200 个域名，10 分钟内跑完探测，输出人工队列
2. 人工队列里 D 桶的域名不出现（已被前置淘汰）
3. 每天记录 20 次投递，总耗时不超过 4 分钟
4. `bl stats` 能给出四桶真实占比

**四桶占比这个数字决定整个产品方向**：D 桶占八成 → 产品是「避坑地图」；A 桶意外地多 → 产品是「速发清单」。现在猜没有意义，等数据。

---

## 八、后续阶段（不要现在做）

### 第二阶段：验证循环

- 90 天存活率、收录率跑起来
- 旅游垂类接入
- 医疗垂类做劝退报告

### 第三阶段：对外

- 内容层：`how to submit a guest post on ___` 长尾内容站，第一手实操，吃 SEO 流量
- D 桶公开：`is ___ guest post free` 类内容
- 接口层：agent 调用「niche X 的下 N 个可用位置」，控速分发，不给 dump
- 自吃狗粮：用自己的库给自己的工具站发外链，把 AlternativeTo / Product Hunt / SaaSHub 位置全占掉，既是冷启动也是活案例

### 合规注意

对外表述不要写成「给 agent 自动群发外链的工具」，离「卖垃圾邮件工具」只有一步，影响支付通道和域名清白度。定位是**外链机会调研与验证数据库**。

---

## 九、给实施者的一句话

这个项目的产出不是代码，是**每天 20 条真实验证记录的持续积累**。所有代码存在的唯一理由，是让记录这个动作从「要花心力」变成「顺手就完成」。任何增加记录成本的功能，都是负价值。
