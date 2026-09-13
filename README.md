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
3. **活跃度信号**（核心判据）：尝试从 sitemap 的 `<lastmod>`（URL 含 author/contributor/blog）
   或 `/author` `/contributors` `/blog` 页面里抓最新日期。
   **诚实说明局限**：spec 里描述的 `site:域名 inurl:author/` 需要搜索引擎 API，第一阶段没有
   接入（避免抓 Google 搜索结果触发限流/验证码），所以这是一个近似启发式，不是精确复现。
   查不到或 >180 天 → 标 `stale`，不进人工队列；这也是为什么 `bl queue` 默认排除 stale。
4. **平台指纹**：命中 Discourse/phpBB/XenForo 等论坛平台 + 30 天内有活跃 → 倾向 A。

探测器只写 `probes.predicted_bucket`，**不会**自动改 `sites.bucket`——最终定桶必须过一遍
`bl confirm`，这是人在回路里，符合 spec「探测器只做预判」的要求。

`bl revalidate` 是例外：库存复检时如果判定已死，会自动把 `sites.bucket` 降级为 `stale`
（spec 明确允许，降级不需要人工确认，只有升级/首次定桶才需要）。

## 网络请求约束

- 固定 UA，超时 10s，失败重试 1 次，任何单个域名的异常都不会中断整批探测。
- 不写验证码/反爬绕过逻辑。遇到 403 / Cloudflare 挑战，如实记录状态码，交给人处理。

## 测试

```bash
.venv/bin/python -m pytest
```

`tests/test_prober_rules.py` 用一个本地 fixture HTTP server（`tests/conftest.py`）跑探测器
的完整判定逻辑，不依赖真实网络，CI 友好。
