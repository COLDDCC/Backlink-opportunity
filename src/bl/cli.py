from __future__ import annotations

import json
import sys

import click

from . import stats as stats_mod
from .db import connect, get_or_create_site, normalize_domain, now_iso, kv_get, kv_set
from .interactive import confirm_key, select_key
from .linkcheck import check_link
from .prober import ENTRY_PATHS, probe_batch, probe_site, result_to_row
from .util import parse_duration_hours

BUCKETS = ("A", "B", "C", "D", "stale", "unknown")
CAPTCHA_TYPES = ("none", "recaptcha", "hcaptcha", "cloudflare", "email_verify", "unknown")
ATTEMPT_STATUSES = ("submitted", "approved", "rejected", "published", "no_response")


@click.group()
@click.option("--db", "db_path", default=None, envvar="BL_DB_PATH", help="sqlite 文件路径，默认 ./bl.db")
@click.pass_context
def main(ctx: click.Context, db_path: str | None) -> None:
    """免费外链位置库 —— 记录层 + 探测器 + 复检任务。"""
    ctx.obj = connect(db_path)


@main.command(name="import")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--niche", default="tools", show_default=True)
@click.option("--source", default=None, help="这批域名从哪来的")
@click.option("--channel-type", default=None,
              type=click.Choice(["directory", "guest_post", "forum", "resource_page",
                                  "community_answer", "expert_quote", "comment"]))
@click.pass_context
def import_cmd(ctx: click.Context, file: str, niche: str, source: str | None, channel_type: str | None) -> None:
    """导入域名池。文件一行一个域名/URL，`#` 开头的行和空行忽略。"""
    conn = ctx.obj
    new_count = 0
    dup_count = 0
    with open(file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            domain = normalize_domain(line)
            if not domain:
                continue
            existing = conn.execute("SELECT id FROM sites WHERE domain = ?", (domain,)).fetchone()
            get_or_create_site(conn, domain, niche=niche, source=source, channel_type=channel_type)
            if existing:
                dup_count += 1
            else:
                new_count += 1
    click.echo(f"导入完成：新增 {new_count}，已存在跳过 {dup_count}。")


@main.command(name="probe")
@click.option("--niche", default=None)
@click.option("--limit", default=200, show_default=True, type=int)
@click.option("--concurrency", default=8, show_default=True, type=int)
@click.option("--domain", "domains_opt", multiple=True, help="只探测这些域名（忽略 --niche/--limit 的候选筛选）")
@click.option("--include-bucket", "include_buckets", multiple=True,
              help="默认只探测 unknown 的站点；加此选项可以把已分桶的站点也纳入重新探测候选")
@click.option("--force", is_flag=True, default=False,
              help="跳过「首页打不开/被拦截就提前退出」的短路逻辑，强制跑完整套路径探测")
@click.pass_context
def probe_cmd(ctx: click.Context, niche: str | None, limit: int, concurrency: int,
              domains_opt: tuple[str, ...], include_buckets: tuple[str, ...], force: bool) -> None:
    """批量探测，输出四桶预判 + 依据。"""
    conn = ctx.obj
    if domains_opt:
        domains = []
        for d in domains_opt:
            d = normalize_domain(d)
            get_or_create_site(conn, d, niche=niche)
            domains.append(d)
    else:
        q = "SELECT domain FROM sites WHERE 1=1"
        params: list = []
        if include_buckets:
            placeholders = ",".join("?" for _ in include_buckets)
            q += f" AND (bucket IS NULL OR bucket = 'unknown' OR bucket IN ({placeholders}))"
            params.extend(include_buckets)
        else:
            q += " AND (bucket IS NULL OR bucket = 'unknown')"
        if niche:
            q += " AND niche = ?"
            params.append(niche)
        q += " ORDER BY first_seen ASC LIMIT ?"
        params.append(limit)
        domains = [r["domain"] for r in conn.execute(q, params).fetchall()]

    if not domains:
        click.echo("没有需要探测的域名（都已分桶；用 --domain 指定或 --include-bucket 扩大候选范围）。")
        return

    click.echo(f"开始探测 {len(domains)} 个域名，并发 {concurrency} ...")
    counts: dict[str, int] = {}

    def on_result(res):
        site_id = get_or_create_site(conn, res.domain, niche=niche)
        row = result_to_row(res)
        conn.execute(
            """INSERT INTO probes (site_id, probed_at, paths_found, latest_author_post,
                has_pricing_page, contact_email_type, marketplace_hit, platform,
                predicted_bucket, predict_confidence, raw)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (site_id, now_iso(), row["paths_found"], row["latest_author_post"], row["has_pricing_page"],
             row["contact_email_type"], row["marketplace_hit"], row["platform"], row["predicted_bucket"],
             row["predict_confidence"], row["raw"]),
        )
        if res.entry_url:
            conn.execute("UPDATE sites SET entry_url = ? WHERE id = ? AND (entry_url IS NULL OR entry_url = '')",
                         (res.entry_url, site_id))
        conn.commit()
        counts[res.predicted_bucket] = counts.get(res.predicted_bucket, 0) + 1
        click.echo(f"  {res.domain:35s} -> {res.predicted_bucket:8s}  {res.bucket_reason}")

    probe_batch(list(domains), concurrency=concurrency, on_result=on_result, force=force)

    click.echo("\n完成。四桶预判分布：")
    for b, n in sorted(counts.items()):
        click.echo(f"  {b}: {n}")
    click.echo("下一步：`bl queue` 看人工队列，`bl confirm <domain>` 写回最终桶位。")


@main.command(name="queue")
@click.option("--niche", default=None)
@click.option("--exclude-bucket", multiple=True, default=("D",), show_default=True)
@click.option("--exclude-stale/--include-stale", default=True, show_default=True)
@click.pass_context
def queue_cmd(ctx: click.Context, niche: str | None, exclude_bucket: tuple[str, ...], exclude_stale: bool) -> None:
    """看今天该人工处理哪些（探测器筛剩下的）。"""
    conn = ctx.obj
    q = """
    SELECT s.domain, s.channel_type, s.entry_url, s.bucket,
           p.predicted_bucket, p.predict_confidence, p.latest_author_post
    FROM sites s
    LEFT JOIN probes p ON p.id = (
        SELECT id FROM probes WHERE site_id = s.id ORDER BY probed_at DESC LIMIT 1
    )
    WHERE 1=1
    """
    params: list = []
    if niche:
        q += " AND s.niche = ?"
        params.append(niche)
    # (predict_confidence IS NULL) sorts 0 (has a value) before 1 (NULL) —
    # portable "NULLS LAST" without depending on SQLite >= 3.30 syntax
    q += " ORDER BY (p.predict_confidence IS NULL), p.predict_confidence DESC, s.domain ASC"
    rows = conn.execute(q, params).fetchall()

    excluded = {b.upper() for b in exclude_bucket}
    shown = 0
    for r in rows:
        confirmed = r["bucket"] not in (None, "unknown")
        effective = (r["bucket"] if confirmed else r["predicted_bucket"]) or "unknown"
        if effective.upper() in excluded:
            continue
        if exclude_stale and effective == "stale":
            continue
        shown += 1
        flag = "confirmed" if confirmed else "predicted"
        click.echo(
            f"{r['domain']:35s} [{flag:9s}] bucket={effective:8s} "
            f"conf={r['predict_confidence'] or 0:.2f} entry={r['entry_url'] or '-'} "
            f"latest_post={r['latest_author_post'] or '-'}"
        )
    click.echo(f"\n共 {shown} 条待人工处理。" if shown else "队列为空。")


@main.command(name="confirm")
@click.argument("domain")
@click.option("--bucket", type=click.Choice(BUCKETS), default=None)
@click.option("--reason", default=None)
@click.pass_context
def confirm_cmd(ctx: click.Context, domain: str, bucket: str | None, reason: str | None) -> None:
    """人工确认最终桶位，写回 sites.bucket。"""
    conn = ctx.obj
    domain = normalize_domain(domain)
    site = conn.execute("SELECT * FROM sites WHERE domain = ?", (domain,)).fetchone()
    if not site:
        raise click.ClickException(f"未找到域名 {domain}，先 `bl import` 或 `bl probe --domain {domain}`。")

    latest_probe = conn.execute(
        "SELECT * FROM probes WHERE site_id = ? ORDER BY probed_at DESC LIMIT 1", (site["id"],)
    ).fetchone()
    predicted = latest_probe["predicted_bucket"] if latest_probe else None
    predicted_reason = None
    if latest_probe and latest_probe["raw"]:
        try:
            predicted_reason = json.loads(latest_probe["raw"]).get("bucket_reason")
        except (json.JSONDecodeError, AttributeError):
            predicted_reason = None

    if bucket is None:
        if latest_probe:
            click.echo(f"最近一次探测预判: {predicted} (confidence={latest_probe['predict_confidence']:.2f})")
            click.echo(f"依据: {predicted_reason or '-'}")
        else:
            click.echo("这个域名还没被探测过。")
        options = [
            ("a", "A 即时自助", "A"), ("b", "B 快审", "B"), ("c", "C 慢队列", "C"),
            ("d", "D 假免费", "D"), ("s", "stale 已死", "stale"), ("u", "unknown 待定", "unknown"),
        ]
        default = predicted if predicted in BUCKETS else None
        bucket = select_key(f"确认 {domain} 的最终桶位：", options, default=default)

    if reason is None:
        reason = predicted_reason

    conn.execute(
        "UPDATE sites SET bucket = ?, bucket_reason = ?, last_verified = ? WHERE id = ?",
        (bucket, reason, now_iso(), site["id"]),
    )
    conn.commit()
    click.echo(f"{domain} -> {bucket}")


@main.command(name="log")
@click.argument("domain")
@click.option("--entry", default=None, help="投稿/提交入口路径或 URL")
@click.option("--register/--no-register", "register", default=None)
@click.option("--captcha", type=click.Choice(CAPTCHA_TYPES), default=None)
@click.option("--status", type=click.Choice(ATTEMPT_STATUSES), default=None)
@click.option("--target", default=None, help="给哪个站发的（如 proivf.com）")
@click.option("--time", "time_cost_min", type=int, default=None, help="这次花了多少分钟")
@click.option("--url", "live_url", default=None, help="发布成功后的成品链接")
@click.option("--niche", default="tools", show_default=True, help="新域名首次记录时使用的 niche")
@click.option("--notes", default=None)
@click.pass_context
def log_cmd(ctx: click.Context, domain: str, entry: str | None, register: bool | None, captcha: str | None,
            status: str | None, target: str | None, time_cost_min: int | None, live_url: str | None,
            niche: str, notes: str | None) -> None:
    """记录一次投递。目标：10 秒内完成，全部单键选择，不打字。

    全部字段都可以用 flag 一次性传完（脚本化场景）；缺哪个就交互补哪个。
    """
    conn = ctx.obj
    domain = normalize_domain(domain)
    site = conn.execute("SELECT * FROM sites WHERE domain = ?", (domain,)).fetchone()
    if site is None:
        site_id = get_or_create_site(conn, domain, niche=niche)
        site = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()

    # entry_url: offer paths discovered by the last probe as a single-key menu
    if entry is None and not site["entry_url"]:
        latest_probe = conn.execute(
            "SELECT paths_found FROM probes WHERE site_id = ? ORDER BY probed_at DESC LIMIT 1", (site["id"],)
        ).fetchone()
        candidates = []
        if latest_probe and latest_probe["paths_found"]:
            try:
                paths = json.loads(latest_probe["paths_found"])
                # only offer entry-style paths — not /pricing, /register etc.
                # that happen to also 200 (see ALL_PATHS in prober.py)
                candidates = [p for p in ENTRY_PATHS if paths.get(p) == 200]
            except json.JSONDecodeError:
                candidates = []
        if candidates:
            options = [(str(i + 1), p, p) for i, p in enumerate(candidates[:9])]
            options.append(("0", "其他 / 手动输入", None))
            entry = select_key(f"{domain} 的投稿入口：", options)
            if entry is None:
                entry = click.prompt("输入入口路径/URL", default="", show_default=False) or None
        else:
            entry = click.prompt("输入入口路径/URL（回车跳过）", default="", show_default=False) or None
    entry_url = entry or site["entry_url"]

    if register is None:
        if site["needs_register"] is not None:
            register = bool(site["needs_register"])
        else:
            register = confirm_key(f"{domain} 需要注册吗？", default=True)

    if captcha is None:
        captcha = site["captcha_type"] or select_key(
            "验证码类型：",
            [(str(i + 1), c, c) for i, c in enumerate(CAPTCHA_TYPES)],
            default="none",
        )

    if status is None:
        status = select_key(
            "本次结果：",
            [("s", "submitted 已提交", "submitted"), ("a", "approved 已过审", "approved"),
             ("r", "rejected 被拒", "rejected"), ("p", "published 已发布", "published"),
             ("n", "no_response 无回应", "no_response")],
            default="submitted",
        )

    last_target = kv_get(conn, "last_target")
    if target is None:
        if last_target:
            options = [("y", f"同上次 ({last_target})", last_target), ("n", "换一个", None)]
            target = select_key("给哪个站发的：", options, default=last_target)
        if target is None:
            target = click.prompt("目标站点 (target_site)")
    kv_set(conn, "last_target", target)

    if time_cost_min is None:
        time_cost_min = click.prompt("花了几分钟", type=int, default=5)

    if status == "published" and live_url is None:
        live_url = click.prompt("成品链接 URL（回车跳过）", default="", show_default=False) or None

    submitted_at = now_iso()
    cur = conn.execute(
        """INSERT INTO attempts (site_id, target_site, submitted_at, status, status_at, live_url,
                                  time_cost_min, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (site["id"], target, submitted_at, status, submitted_at, live_url, time_cost_min, notes),
    )
    conn.execute(
        """UPDATE sites SET entry_url = COALESCE(?, entry_url), needs_register = ?, captcha_type = ?,
                             last_verified = ? WHERE id = ?""",
        (entry_url, int(register), captcha, submitted_at, site["id"]),
    )
    conn.commit()
    click.echo(f"记录完成：attempt #{cur.lastrowid} — {domain} -> {target} [{status}]")


@main.command(name="update")
@click.argument("attempt_id", type=int)
@click.option("--status", type=click.Choice(ATTEMPT_STATUSES), required=True)
@click.option("--url", "live_url", default=None)
@click.option("--notes", default=None)
@click.pass_context
def update_cmd(ctx: click.Context, attempt_id: int, status: str, live_url: str | None, notes: str | None) -> None:
    """更新投递结果。"""
    conn = ctx.obj
    row = conn.execute("SELECT id FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    if not row:
        raise click.ClickException(f"未找到 attempt #{attempt_id}")
    conn.execute(
        """UPDATE attempts SET status = ?, status_at = ?, live_url = COALESCE(?, live_url),
                                notes = COALESCE(?, notes) WHERE id = ?""",
        (status, now_iso(), live_url, notes, attempt_id),
    )
    conn.commit()
    click.echo(f"attempt #{attempt_id} -> {status}" + (f" ({live_url})" if live_url else ""))


@main.command(name="recheck")
@click.option("--older-than", default="30d", show_default=True, help='如 "30d" "12h" "2w"')
@click.option("--limit", default=500, show_default=True, type=int)
@click.pass_context
def recheck_cmd(ctx: click.Context, older_than: str, limit: int) -> None:
    """复检：所有已发布链接是否还活着，dofollow 状态有没有变。"""
    conn = ctx.obj
    hours = parse_duration_hours(older_than)
    cutoff = _hours_ago_iso(hours)
    rows = conn.execute(
        """
        SELECT a.id AS attempt_id, a.live_url, a.target_site
        FROM attempts a
        WHERE a.status = 'published' AND a.live_url IS NOT NULL
          AND a.id NOT IN (
              SELECT attempt_id FROM link_checks
              GROUP BY attempt_id HAVING MAX(checked_at) > ?
          )
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()

    if not rows:
        click.echo("没有到期需要复检的链接。")
        return

    click.echo(f"复检 {len(rows)} 条已发布链接 ...")
    alive = dead = 0
    rel_counts: dict[str, int] = {}
    for r in rows:
        target_domain = normalize_domain(r["target_site"]) if r["target_site"] else ""
        result = check_link(r["live_url"], target_domain)
        conn.execute(
            """INSERT INTO link_checks (attempt_id, checked_at, http_status, link_present, rel_attr)
               VALUES (?, ?, ?, ?, ?)""",
            (r["attempt_id"], now_iso(), result.http_status, int(result.link_present), result.rel_attr),
        )
        conn.commit()
        if result.link_present:
            alive += 1
            rel_counts[result.rel_attr or "unknown"] = rel_counts.get(result.rel_attr or "unknown", 0) + 1
        else:
            dead += 1
        status_word = "ALIVE" if result.link_present else "DEAD"
        click.echo(f"  attempt #{r['attempt_id']:<6d} {status_word:5s} http={result.http_status} rel={result.rel_attr}")

    click.echo(f"\n完成：alive={alive} dead={dead}")
    if rel_counts:
        click.echo("rel 分布：" + ", ".join(f"{k}={v}" for k, v in rel_counts.items()))


@main.command(name="revalidate")
@click.option("--older-than", default="14d", show_default=True, help='如 "14d" "12h" "2w"')
@click.option("--niche", default=None)
@click.option("--limit", default=500, show_default=True, type=int)
@click.pass_context
def revalidate_cmd(ctx: click.Context, older_than: str, niche: str | None, limit: int) -> None:
    """库存复检：投稿入口是否还开着。死的自动降级为 stale，不需要人工确认。"""
    conn = ctx.obj
    hours = parse_duration_hours(older_than)
    cutoff = _hours_ago_iso(hours)
    q = """SELECT * FROM sites WHERE bucket IN ('A','B','C')
           AND (last_verified IS NULL OR last_verified < ?)"""
    params: list = [cutoff]
    if niche:
        q += " AND niche = ?"
        params.append(niche)
    q += " LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()

    if not rows:
        click.echo("没有到期需要复检的库存。")
        return

    click.echo(f"复检 {len(rows)} 个库存位置 ...")
    downgraded = 0
    for site in rows:
        res = probe_site(site["domain"])
        row = result_to_row(res)
        conn.execute(
            """INSERT INTO probes (site_id, probed_at, paths_found, latest_author_post,
                has_pricing_page, contact_email_type, marketplace_hit, platform,
                predicted_bucket, predict_confidence, raw)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (site["id"], now_iso(), row["paths_found"], row["latest_author_post"], row["has_pricing_page"],
             row["contact_email_type"], row["marketplace_hit"], row["platform"], row["predicted_bucket"],
             row["predict_confidence"], row["raw"]),
        )
        if res.predicted_bucket in ("stale", "D"):
            conn.execute(
                "UPDATE sites SET bucket = ?, bucket_reason = ?, last_verified = ? WHERE id = ?",
                (res.predicted_bucket, res.bucket_reason, now_iso(), site["id"]),
            )
            downgraded += 1
            click.echo(f"  {site['domain']:35s} 降级 -> {res.predicted_bucket}  {res.bucket_reason}")
        elif res.raw.get("blocked"):
            # unreachable/blocked right now isn't proof it's dead — could be
            # a transient WAF trip. Don't downgrade on a guess; leave the
            # bucket as-is and flag it for a human to actually look at.
            click.echo(f"  {site['domain']:35s} 无法访问/被拦截，未改动桶位，建议人工复查  {res.bucket_reason}")
        else:
            conn.execute("UPDATE sites SET last_verified = ? WHERE id = ?", (now_iso(), site["id"]))
            click.echo(f"  {site['domain']:35s} 仍然活着 ({site['bucket']})")
        conn.commit()

    click.echo(f"\n完成：{len(rows)} 条已复检，{downgraded} 条自动降级。")


@main.command(name="stats")
@click.option("--niche", default=None)
@click.pass_context
def stats_cmd(ctx: click.Context, niche: str | None) -> None:
    """出数：四桶占比 / 过审率 / 平均耗时 / 90天存活率。"""
    conn = ctx.obj
    dist = stats_mod.bucket_distribution(conn, niche)
    total_sites = sum(dist.values())
    attempts = stats_mod.attempt_stats(conn, niche)
    survival = stats_mod.survival_rate_90d(conn, niche)

    click.echo(f"=== bl stats{f' --niche {niche}' if niche else ''} ===\n")

    click.echo("四桶占比：")
    for b in ("A", "B", "C", "D", "stale", "unknown"):
        n = dist.get(b, 0)
        pct = (n / total_sites * 100) if total_sites else 0
        click.echo(f"  {b:8s} {n:5d}  ({pct:5.1f}%)")
    click.echo(f"  合计 {total_sites}\n")

    click.echo("投递情况：")
    click.echo(f"  总投递数: {attempts['total']}")
    for status, n in sorted(attempts["counts"].items()):
        click.echo(f"    {status}: {n}")
    rate = attempts["approval_rate"]
    click.echo(f"  过审率 (approved+published / 已有结果的): {rate * 100:.1f}%" if rate is not None else "  过审率: 数据不足")
    avg = attempts["avg_time_cost_min"]
    click.echo(f"  平均每次投递耗时: {avg:.1f} 分钟" if avg is not None else "  平均耗时: 数据不足")
    avg_pub = attempts["avg_time_per_published_min"]
    click.echo(f"  每条成品链接平均耗时: {avg_pub:.1f} 分钟" if avg_pub is not None else "  每条链接平均耗时: 数据不足")
    click.echo()

    click.echo("90 天存活率：")
    if survival["eligible"]:
        click.echo(f"  {survival['alive']}/{survival['eligible']} = {survival['rate'] * 100:.1f}%")
    else:
        click.echo("  还没有满 90 天的已发布链接，数据不足。")


def _hours_ago_iso(hours: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
