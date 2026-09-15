#!/usr/bin/env bash
# 一次性写入 2026-09-15 这批测试数据，跑在这个会话自己的 bl.db 上（仓库根目录，gitignore 已排除）。
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$(pwd)/.venv/bin:$PATH"

TOOLS_FILE=$(mktemp)
GENERAL_FILE=$(mktemp)
MEDICAL_FILE=$(mktemp)
trap 'rm -f "$TOOLS_FILE" "$GENERAL_FILE" "$MEDICAL_FILE"' EXIT

cat > "$TOOLS_FILE" <<'EOF'
peerpush.com
huggingface.co
launchingnext.com
easywithai.com
somi.ai
aiagentsdirectory.com
poweredbyai.app
nxgntools.com
toolai.io
code.market
curateclick.com
deeplaunch.io
websitelaunches.com
EOF

cat > "$GENERAL_FILE" <<'EOF'
facebook.com
instagram.com
wordpress.com
wellfound.com
notion.so
nodeseek.com
sitelike.org
domainrank.app
yo.directory
EOF

cat > "$MEDICAL_FILE" <<'EOF'
gravatar.com
EOF

bl import "$TOOLS_FILE" --niche tools --source "manual-test-2026-09-15"
bl import "$GENERAL_FILE" --niche general --source "manual-test-2026-09-15"
bl import "$MEDICAL_FILE" --niche medical --source "manual-test-2026-09-15"

BLANK=$'\n\n\n\n\n'

bl confirm peerpush.com --bucket unknown \
  --reason "no follow，不互动排名掉 | 可以发，但免费档就是排队等，免费版大概率是 nofollow 或非永久链接" \
  --suitable-for "工具站" --nofollow --link-format listing

bl confirm facebook.com --bucket unknown \
  --reason "养号难，跳实人验证" \
  --suitable-for "通用" --link-format profile

bl confirm domainrank.app --bucket unknown \
  --reason "标了待发布，但备注又说不确定是否免费，需要先确认清楚再定桶" \
  --suitable-for "通用"

bl confirm gravatar.com --bucket A \
  --reason "profile可放" \
  --suitable-for "医疗,proivf" --link-format profile <<< "$BLANK"

bl confirm wellfound.com --bucket A \
  --reason "免费建公司档案，只能当公司名片" \
  --suitable-for "通用" --link-format profile <<< "$BLANK"

bl confirm huggingface.co --bucket A \
  --reason "网站型创业项目/公司，大多no follow" \
  --suitable-for "工具站" --nofollow --link-format profile <<< "$BLANK"

bl confirm toolai.io --bucket B \
  --reason "no follow" \
  --suitable-for "工具站" --nofollow --link-format listing <<< "$BLANK"

bl confirm code.market --bucket B \
  --reason "no follow" \
  --suitable-for "工具站" --nofollow --link-format listing <<< "$BLANK"

bl confirm yo.directory --bucket B \
  --reason "目录类站点" \
  --suitable-for "通用" --link-format listing <<< "$BLANK"

bl confirm instagram.com --bucket A \
  --reason "正文没有外链，只能放主页bio" \
  --suitable-for "通用" --link-format profile <<< "$BLANK"

bl confirm wordpress.com --bucket A \
  --reason "发表博客文章 | 有免费套餐但藏得很深：注册-选域名-compare plans，往下点才有免费套餐" \
  --suitable-for "通用" --link-format article <<< "$BLANK"

bl confirm notion.so --bucket A \
  --reason "注册之后发表文章即有外链" \
  --suitable-for "通用" --dofollow --link-format article <<< "$BLANK"

bl confirm sitelike.org --bucket A \
  --reason "推荐相似域名 | 单页权重趋近于零，免费但需绑定信用卡，前十几天免费试用，过程简单可以让agent代发" \
  --suitable-for "通用" --nofollow --link-format listing <<< "$BLANK"

bl confirm launchingnext.com --bucket C \
  --reason "感觉是骗人邮箱的，提交表单后毫无反馈、无任何提示" \
  --suitable-for "工具站" --nofollow --link-format listing <<< "$BLANK"

bl confirm nodeseek.com --bucket C \
  --reason "勉强通用，默认工具站，需要养号（论坛），尽量要有telegram账号，否则排队申请很麻烦" \
  --suitable-for "通用" --link-format other <<< "$BLANK"

bl confirm curateclick.com --bucket C \
  --reason "免费提交但不一定保证收录，就是要你买链接；1-2个月内审核，非跟随链接，基础目录展示；徽章换dofollow本质是互惠链接，价值接近零还留痕迹" \
  --suitable-for "工具站" --nofollow --link-format listing --wait "1-2 个月" <<< "$BLANK"

bl confirm easywithai.com --bucket D \
  --reason "目录站默认no follow会有审核，仅教育/学术研究类且free或开源可以免费，其他都要收费" \
  --suitable-for "工具站" --nofollow --link-format listing <<< "$BLANK"

bl confirm somi.ai --bucket D \
  --reason "审核看的是产品给用户的输出，必须是真正的AI SaaS工具才能过审" \
  --suitable-for "工具站" --link-format listing <<< "$BLANK"

bl confirm aiagentsdirectory.com --bucket D \
  --reason "免费dofollow但强制反向挂链，必须要真的有AI功能的网站才行，AI做的网站不算" \
  --suitable-for "工具站" --dofollow --link-format listing --dr 71 <<< "$BLANK"

bl confirm poweredbyai.app --bucket D \
  --reason "no follow，并且没有任何付费入口，疑似站群" \
  --suitable-for "工具站" --nofollow --link-format listing <<< "$BLANK"

bl confirm nxgntools.com --bucket D \
  --reason "no follow，免费额度排到明年，网站不一定能活到那时候" \
  --suitable-for "工具站" --nofollow --link-format listing <<< "$BLANK"

bl confirm deeplaunch.io --bucket D \
  --reason "免费外链要求在自己网站全站footer放一条给deeplaunch.io的dofollow链接，等于每页都在给DR71的同赛道目录站输血，代价远超收益；而且实际要收费" \
  --suitable-for "工具站" --dr 71 --link-format listing <<< "$BLANK"

bl confirm websitelaunches.com --bucket D \
  --reason "no follow，收录与否由系统自动检测决定提交没用，老站被抓到也只进归档不进日榜" \
  --suitable-for "工具站" --nofollow --link-format listing <<< "$BLANK"

echo "=== 全部 23 条记录完成 ==="
