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
bl confirm example.com --bucket A --reason "目录站，注册即收录"
#   不加 --bucket 会进入单键选择菜单，并显示探测器的预判和依据

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

# 9. 出数：四桶占比 / 过审率 / 平均耗时 / 90 天存活率
bl stats --niche tools
```

## 数据模型

严格照搬 spec：`sites`（站点主表，一域名一行）、`probes`（每次探测留痕）、
`attempts`（每次投递留痕）、`link_checks`（存活复检留痕）。另加一张 `kv` 表，只用来记
`bl log` 里「上次投给哪个站」，好让交互式记录能单键复用。

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
