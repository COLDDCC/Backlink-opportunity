# 免费外链位置库 —— 第一阶段

这不是又一份「免费外链网站大全」。核心资产不是站点清单，是**存活数据**：一条投稿位置现在
还活不活、发上去的链接存不存、投稿过审要几天、以及它在第几步坑你。这些数据只能靠人天天
实操记录才能产生。所有代码存在的唯一理由，是让**记录**这个动作从「要花心力」变成「顺手就
完成」——`bl log` 必须能在 10 秒内跑完。

完整设计背景见 `docs/spec.md`（第二、三阶段暂不实施）。

## 环境

本地优先，SQLite，无需 Docker/云服务。

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e .
source .venv/bin/activate   # 之后就能直接用 `bl` 命令
```

数据库默认写到当前目录下的 `bl.db`，可用 `--db path/to.db` 或环境变量 `BL_DB_PATH` 覆盖。
`bl.db` 已加入 `.gitignore`——这是你每天攒的真实数据，不要提交进仓库。

## 工作流

```bash
# 1. 导入域名池（一行一个域名/URL，# 开头忽略）
bl import domains.txt --niche tools --source "alternativeto-competitors"

# 2. 批量探测：跑 D 信号 / 排队信号 / 活跃度信号 / 平台指纹，输出预判
bl probe --niche tools --limit 200 --concurrency 8

# 3. 看人工队列（探测器已经把 D 桶和已死的过滤掉）
bl queue --niche tools

# 4. 人工确认最终桶位，写回 sites.bucket（探测器只做预判，不自动写回）
bl confirm example.com --bucket A --reason "目录站，注册即收录" \
   --suitable-for "tools,ai" --wait "2-4 周" --dofollow --link-format listing --dr 42
#   不加 --bucket 会进入单键选择菜单，并显示探测器的预判和依据
#   桶位是 A/B/C/D 时才会追问「适合哪类目标站」「dofollow 还是 nofollow」
#   「链接放在什么形式里（article/comment/profile/listing/other）」「DR 多少」，
#   B/C 桶还会多问一句「预计要等多久」；
#   D/stale/no_channel/unknown 问了也没意义，不会问
#   压根没有外链渠道的站，直接 --bucket no_channel，跟「D=有渠道但是坑」分开记

# 5. 记录一次投递 —— 10 秒内完成，缺什么补什么，全部单键选择不用打字
bl log example.com --entry /write-for-us --register --captcha recaptcha \
   --status submitted --target proivf.com --time 12
#   参数都省略也可以，会交互式单键补全

# 6. 更新投递结果
bl update 1 --status published --url https://example.com/posts/our-article

# 7. 复检已发布链接是否还活着 / 还是不是 dofollow
bl recheck --older-than 30d

# 8. 库存复检：投稿入口是否还开着（判定已死会自动降级为 stale，不需要人工确认）
bl revalidate --older-than 14d

# 9. 出数：四桶占比 / 过审率 / 平均耗时（含提交到出结果的实际等待天数）/ 90 天存活率
bl stats --niche tools

# 10. 筛选已确认可用的库存（不是待处理队列，是"能直接拿去用"的那些）
bl list --niche tools --min-dr 20 --max-dr 50 --dofollow yes --link-format article
```

## 数据模型

基本照搬 spec：`sites`（站点主表，一域名一行）、`probes`（每次探测留痕）、
`attempts`（每次投递留痕）、`link_checks`（存活复检留痕）。另加两张东西：

- `kv` 表：只用来记 `bl log` 里「上次投给哪个站」，好让交互式记录能单键复用。
- `sites.suitable_for` / `sites.expected_wait`：spec 原表没有，是跑起来之后加的两个字段——
  「这个位置适合投给哪类目标站」和「B/C 桶大概要等多久出结果」，`bl confirm` 时顺手问一句，
  跳过不填也行。老的 `bl.db` 文件不用手动迁移，`connect()` 时会自动补上这两列。
- `sites.bucket` 多了一档 `no_channel`：跟 `D`（有渠道但是收费/是坑）分开，专指
  「压根没有任何外链/投稿入口，看一眼首页就能判断，不用深究」的站，两者归因完全不同，
  混在一起会让 D 桶的"坑"数据失真。
- `sites.is_dofollow`（spec 原表就有，之前一直没人写）、`sites.link_format`、
  `sites.domain_rating`：dofollow/nofollow、链接放在 article/comment/profile/listing/other
  哪种形式里、DR/DA 多少。**DR 是人工填的**，第一阶段不接 Ahrefs/Moz 之类的付费 API，
  也不去爬免费查询站（大概率有反爬，抓了也违反"不写反爬绕过"的原则）——你自己在别处查到
  多少就填多少，查不到就跳过。
- `bl list`：跟 `bl queue`（今天该人工处理哪些，还没定桶的）是两码事，`bl list` 是从**已经
  confirm 过**的库存里按 DR/dofollow/形式/适用类型筛，回答"我现在手头有哪些能直接拿去用
  的位置"这个问题。

## 探测器规则说明（`src/bl/prober.py`）

按 spec 第五节实现，任一 D 信号命中即刻短路返回，不再往下跑：

1. **D 信号**：商业化页面（`/advertise` `/pricing` 等 200）、投稿页收费关键词、
   联系邮箱是商务前缀（`seo@` `sales@` 等）、域名命中本地黑名单
   （`data/marketplace_domains.txt`，手工维护，抓取市场目录留到后面阶段）。
2. **排队信号**：editorial calendar / allow 4-6 weeks / 要 portfolio 等，倾向 C。
3. **活跃度信号**（核心判据）：三层兜底——① sitemap 里 URL 含 author/contributor/blog 的
   `<lastmod>`；② 常见的 sitemap **索引**结构（WordPress/Yoast 那种 `sitemap.xml` 只列
   `post-sitemap.xml` `page-sitemap.xml` 这种子文件），会跟进抓最多 2 个文件名像
   post/article/blog 的子 sitemap，取里面最新的 `<lastmod>`；③ 都没有就退化成扫
   `/author` `/contributors` `/blog` 页面里的日期。
   **诚实说明局限**：spec 里描述的 `site:域名 inurl:author/` 需要搜索引擎 API，第一阶段没有
   接入（避免抓 Google 搜索结果触发限流/验证码），所以这是一个近似启发式，不是精确复现，
   而且第②层拿到的是「网站最近有没有发文章」而不是「最近有没有发**外部投稿**文章」——
   两者不完全等价，只是相关性够强的代理指标。
   查不到或 >180 天 → 标 `stale`，不进人工队列；这也是为什么 `bl queue` 默认排除 stale。
4. **平台指纹**：命中 Discourse/phpBB/XenForo 等论坛平台 + 30 天内有活跃 → 倾向 A。

探测器只写 `probes.predicted_bucket`，**不会**自动改 `sites.bucket`——最终定桶必须过一遍
`bl confirm`，这是人在回路里，符合 spec「探测器只做预判」的要求。

`bl revalidate` 是例外：库存复检时如果判定已死，会自动把 `sites.bucket` 降级为 `stale`
（spec 明确允许，降级不需要人工确认，只有升级/首次定桶才需要）。如果复检时首页打不开/被拦截，
不会自动降级——不确定的信号不该拿来杀活的库存，只会打印出来提醒人工复查。

### 关于 `expected_wait` 的一个待定产品问题

C 桶「要排队」和「可能要排一年」在数据上是同一档，但对「按提交数考核」的目标用户来说价值
完全不同——很多站自己都活不过一年。`expected_wait` 只负责把这个数字如实记下来，**要不要在
用户看到的地方把等待很久的位置往后放（而不是删掉/瞒报）**是留给以后做对外展示时决定的产品
判断，现在没有前端，不需要在这里定。

### 关于付费评测（还没做）

「买了某个站的付费额度实际能拿到什么效果，跟官方自称的对比」需要一张新表（价位/官方承诺/
实测效果）和一套完全不同的工作流（真金白银去买测，不是每天批量探测）。这已经是 spec 第三
阶段"D 桶公开"性质的内容层工作，第一阶段先不做，等前面的数据跑出来再看要不要启动。

## 网络请求约束

- 固定 UA，超时 10s，失败重试 1 次，任何单个域名的异常都不会中断整批探测。
- 不写验证码/反爬绕过逻辑。遇到 403 / Cloudflare 挑战，如实记录状态码，交给人处理。
- **首页打不开或被拦截（DNS 失败/超时/403/429/503）会直接短路返回**，不会傻乎乎地把剩下
  20 多个路径全跑一遍再各自超时——一个死域名不该拖垮"200 个域名 10 分钟跑完"的整批预算。
  极少数情况下你明知道某个域名的首页响应有问题但路径其实是通的，可以用 `bl probe --force`
  强制跳过这个短路逻辑。
- **会区分"网站真的拦你"和"你自己的出网环境拦了你"**：如果 `bl` 跑在类似 Claude Code
  沙盒这种默认拒绝出网白名单外域名的环境里，代理会返回一个跟真实网站长得很像的 403，
  这时候探测器不会瞎猜"可能是 Cloudflare"，而是如实说明是本地网络策略拦截，需要换一个
  能正常出网的环境重跑才能得出真实判断。

## 测试

```bash
.venv/bin/python -m pytest
```

`tests/test_prober_rules.py` 用一个本地 fixture HTTP server（`tests/conftest.py`）跑探测器
的完整判定逻辑，不依赖真实网络，CI 友好。
