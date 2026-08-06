#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 每日要报生成器 v2（云端版，供 GitHub Actions 运行）
内容聚焦两块：
  板块一：AI × 经济金融 好用技能（GitHub 高星 skills / Claude·Codex·Obsidian / Cursor，含用法解读）
  板块二：全球 AI 与金融科技公司动态（AI HOT 按金融/公司关键词筛选）
再叠加「说人话」改写与技能解读（SiliconFlow 大模型；缺 key 自动降级）。
产出：ai_daily.png（信息图）、ai-daily.html（完整版网页）、ai-daily.json；并推微信（精简版 + 链接完整网页）。
依赖：pip install pillow requests
"""
import json, os, sys, subprocess, datetime
import urllib.request, urllib.parse, urllib.error

AIHOT_URL = "https://aihot.virxact.com/api/v1/items?mode=selected&window=24h&limit=30"
UA = "aihot-skill/1.2.1 (+https://aihot.virxact.com/aihot-skill/)"
SF_URL = "https://api.siliconflow.cn/v1/chat/completions"
SF_MODEL = os.environ.get("SF_MODEL", "deepseek-ai/DeepSeek-V3")

# 金融 / 公司 关键词（小写匹配）
FIN_KW = [
    "金融", "金融科技", "fintech", "银行", "保险", "支付", "信贷", "量化", "加密",
    "区块链", "比特币", "以太坊", "央行", "美联储", "证监会", "监管", "融资", "ipo",
    "财报", "估值", "蚂蚁", "阿里", "腾讯", "字节", "百度", "京东", "拼多多", "美团",
    "stripe", "paypal", "square", "visa", "mastercard", "jpmorgan", "goldman", "摩根",
    "高盛", "汇丰", "花旗", "陆金所", "招行", "工商", "建设", "平安",
    "openai", "anthropic", "google", "gemini", "meta", "microsoft", "nvidia", "apple",
    "特斯拉", "智能投顾", "风控",
]

# GitHub 技能检索词（覆盖 WorkBuddy/Claude/Codex/Obsidian/Cursor 生态）
SKILL_QUERIES = [
    "claude skills",
    "cursor rules",
    "obsidian plugin ai",
    "ai agent skills",
]

# Life OS 配色
C_PURPLE = (175, 82, 222)
C_CYAN = (90, 200, 250)
C_INDIGO = (88, 86, 214)
C_BG = (245, 245, 250)
C_CARD = (255, 255, 255)
C_TITLE = (30, 30, 45)
C_BODY = (70, 70, 85)
C_MUTE = (130, 130, 150)
C_GREEN = (52, 199, 89)
C_ORANGE = (255, 149, 0)


def log(*a):
    print("[gen]", *a, flush=True)


def fetch_json(url, headers=None, timeout=30, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_aihot():
    return fetch_json(AIHOT_URL, headers={"User-Agent": UA})


def parse_bj(iso):
    if not iso:
        return ""
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
        dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso)


def clean(text, limit=120):
    if not text:
        return "详见链接。"
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


def find_font():
    cands = [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    try:
        out = subprocess.check_output(
            ["fc-match", "-f", "%{file}", ":lang=zh"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        pass
    return None


def wrap_text(text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        if font.getlength(test) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------- SiliconFlow 大模型 ----------
def sf_chat(system, user, key, as_json=False, max_tokens=1600):
    if not key:
        return None
    payload = {
        "model": SF_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
    }
    if as_json:
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SF_URL, data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.load(r)
        return resp["choices"][0]["message"]["content"]
    except Exception as e:
        log("SF error:", e)
        return None


# ---------- 板块二：AI HOT 公司/金融动态 ----------
def collect_company_items():
    data = fetch_aihot()
    raw = data.get("items", []) or []
    picked = []
    for it in raw:
        title = (it.get("title") or it.get("headline") or "")
        summary = it.get("summary") or it.get("content") or ""
        src = it.get("source")
        src_name = src.get("name") if isinstance(src, dict) else str(src)
        blob = (title + " " + summary + " " + str(src_name)).lower()
        if any(k in blob for k in FIN_KW):
            picked.append({
                "title": clean(title or "AI 进展", 44),
                "summary": clean(summary, 160),
                "source": src_name or "AI HOT",
                "time": parse_bj(it.get("publishedAt") or it.get("discoveredAt")),
                "url": (it.get("links") or {}).get("aihot") or "",
            })
    # 去重（按标题）
    seen, uniq = set(), []
    for p in picked:
        if p["title"] not in seen:
            seen.add(p["title"])
            uniq.append(p)
    return uniq[:6]


def humanize_companies(companies, key):
    if not companies:
        return companies
    sys_p = ("你是面向金融学教师的助手。把下面几条 AI / 金融科技资讯用大白话改写，"
             "每条严格 2 句内：第1句说清『这件事是什么』，第2句说清『和钱/金融/研究有啥关系或有什么用』。"
             "不要堆术语，不要套话。直接按原序号输出，格式：『1. 改写文字』，不要额外解释。")
    user_p = "\n".join(f"{i+1}. 标题：{c['title']}\n   原文：{c['summary']}"
                        for i, c in enumerate(companies))
    out = sf_chat(sys_p, user_p, key)
    if not out:
        return companies
    # 解析序号
    import re
    map_idx = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\.\s*(.+)", line)
        if m:
            map_idx[int(m.group(1))] = m.group(2).strip()
    if map_idx:
        for i, c in enumerate(companies):
            if (i + 1) in map_idx:
                c["summary"] = clean(map_idx[i + 1], 160)
    return companies


# ---------- 板块一：GitHub 高星 skills ----------
def collect_skills():
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "aria-aihot"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    repos = {}
    for q in SKILL_QUERIES:
        url = ("https://api.github.com/search/repositories?q="
               + urllib.parse.quote(q) + "&sort=stars&order=desc&per_page=6")
        try:
            d = fetch_json(url, headers=headers, timeout=30)
        except Exception as e:
            log("github search err:", e)
            continue
        for r in d.get("items", []) or []:
            fn = r.get("full_name")
            if not fn or fn in repos:
                continue
            repos[fn] = {
                "name": r.get("name"),
                "full_name": fn,
                "desc": r.get("description") or "",
                "stars": r.get("stargazers_count", 0),
                "lang": r.get("language") or "",
                "topics": r.get("topics", []) or [],
                "url": r.get("html_url"),
            }
    # 排序取前 6
    top = sorted(repos.values(), key=lambda x: x["stars"], reverse=True)[:6]
    return top


def explain_skills(skills, key):
    if not skills:
        return skills
    sys_p = ("你是面向非技术研究者（金融学教师）的助手。下面列出 GitHub 上近期高星的 AI 技能/工具仓库。"
             "请对每一个用中文写 2-3 句：它是什么 + 怎么用（尤其说明适合 WorkBuddy / Codex / Obsidian 用户的场景）。"
             "口语、别套话、别说『值得注意的是』。只输出 JSON，格式："
             '{"skills":[{"full_name":"...","usage":"..."}]}，不要多余文字。')
    user_p = json.dumps(
        [{"full_name": s["full_name"], "desc": s["desc"], "stars": s["stars"],
          "topics": s["topics"], "lang": s["lang"]} for s in skills],
        ensure_ascii=False)
    out = sf_chat(sys_p, user_p, key, as_json=True)
    if not out:
        return skills
    try:
        obj = json.loads(out)
        mp = {s["full_name"]: s.get("usage", "") for s in obj.get("skills", [])}
        for s in skills:
            if s["full_name"] in mp and mp[s["full_name"]]:
                s["usage"] = clean(mp[s["full_name"]], 200)
    except Exception as e:
        log("skill explain parse err:", e)
    return skills


# ---------- 信息图 ----------
def make_image(companies, skills, date_str, overview, out_path, font_path):
    from PIL import Image, ImageDraw, ImageFont
    W = 820
    pad = 40
    title_h = 96
    ov_h = 60
    card_h = 150
    gap = 16
    skill_h = 150
    H = (title_h + ov_h + gap + len(companies) * (card_h + gap)
         + 30 + skill_h + 50)

    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(font_path, 44, index=0)
    f_date = ImageFont.truetype(font_path, 24, index=0)
    f_cardtitle = ImageFont.truetype(font_path, 27, index=0)
    f_body = ImageFont.truetype(font_path, 21, index=0)
    f_src = ImageFont.truetype(font_path, 20, index=0)
    f_sec = ImageFont.truetype(font_path, 28, index=0)

    d.text((pad, 24), "AI 每日要报", font=f_title, fill=C_TITLE)
    d.text((pad, 80), f"{date_str}  ·  金融 / 公司动态 + 好用技能", font=f_date, fill=C_MUTE)

    y = title_h + ov_h
    ov_lines = wrap_text(overview, f_body, W - 2 * pad)
    for ln in ov_lines[:2]:
        d.text((pad, y), ln, font=f_body, fill=C_BODY)
        y += 32
    y += 10

    d.text((pad, y), "① 全球 AI / 金融科技公司动态", font=f_sec, fill=C_PURPLE)
    y += 42
    for i, it in enumerate(companies, 1):
        x0, y0 = pad, y
        x1, y1 = W - pad, y + card_h
        d.rounded_rectangle([x0, y0, x1, y1], radius=14,
                            fill=C_CARD, outline=(225, 225, 235), width=1)
        d.text((x0 + 18, y0 + 14), str(i), font=f_cardtitle, fill=C_PURPLE)
        tx = x0 + 54
        for j, ln in enumerate(wrap_text(it["title"], f_cardtitle, W - (x0 + 54) - pad)[:1]):
            d.text((tx, y0 + 12 + j * 34), ln, font=f_cardtitle, fill=C_TITLE)
        sy = y0 + 64
        for ln in wrap_text(it["summary"], f_body, W - (x0 + 24) - pad)[:3]:
            d.text((x0 + 24, sy), ln, font=f_body, fill=C_BODY)
            sy += 30
        d.text((x0 + 24, y1 - 28), f"{it['source']} · {it['time']}",
               font=f_src, fill=C_PURPLE)
        y += card_h + gap

    d.text((pad, y), "② 今日推荐好用技能（GitHub 高星）", font=f_sec, fill=C_INDIGO)
    y += 42
    # 技能卡片：名称 + 一句话用法
    for s in skills[:4]:
        x0, y0 = pad, y
        x1, y1 = W - pad, y + 30
        d.rounded_rectangle([x0, y0, x1, y1 + 78], radius=12,
                            fill=C_CARD, outline=(220, 220, 235), width=1)
        d.ellipse([x0 + 14, y0 + 14, x0 + 34, y0 + 34], fill=C_INDIGO)
        d.text((x0 + 24, y0 + 16), "★", font=f_src, fill=(255, 255, 255))
        nm = f"{s['name']}  ({s['stars']}★)"
        d.text((x0 + 50, y0 + 16), nm, font=f_cardtitle, fill=C_TITLE)
        usage = s.get("usage") or s.get("desc") or ""
        uy = y0 + 54
        for ln in wrap_text(clean(usage, 150), f_body, W - (x0 + 24) - pad)[:3]:
            d.text((x0 + 24, uy), ln, font=f_body, fill=C_BODY)
            uy += 28
        y += 96

    img.save(out_path)
    log("image saved:", out_path, img.size)


# ---------- 完整版网页 ----------
def make_html(companies, skills, date_str, overview, out_path, img_url, web_url):
    def c_cards():
        if not companies:
            return '<div class="empty">今日未筛到强相关的公司/金融动态，可看完整 AI HOT。</div>'
        s = ""
        for i, it in enumerate(companies, 1):
            s += f"""
      <div class="card">
        <div class="num">{i}</div>
        <div class="content">
          <a class="ctitle" href="{it['url']}" target="_blank" rel="noopener">{it['title']}</a>
          <div class="cbody">{it['summary']}</div>
          <div class="cmeta">{it['source']} · {it['time']}</div>
        </div>
      </div>"""
        return s

    def s_cards():
        if not skills:
            return '<div class="empty">今日未取到 GitHub 技能数据。</div>'
        s = ""
        for sk in skills:
            usage = sk.get("usage") or sk.get("desc") or "（暂无解读）"
            s += f"""
      <div class="skill">
        <div class="shead">
          <span class="sname"><a href="{sk['url']}" target="_blank" rel="noopener">{sk['name']}</a></span>
          <span class="sstars">★ {sk['stars']}</span>
        </div>
        <div class="sdesc">{sk['desc']}</div>
        <div class="susage"><b>怎么用：</b>{usage}</div>
        <div class="smeta">{sk['lang']} · {', '.join(sk['topics'][:4])}</div>
      </div>"""
        return s

    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 要报 {date_str}</title>
<style>
  body{{margin:0;background:#f5f5fa;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#2c2c3a;}}
  .wrap{{max-width:820px;margin:0 auto;padding:28px 18px 60px;}}
  h1{{font-size:30px;margin:0 0 4px;}}
  .sub{{color:#888;font-size:14px;margin-bottom:14px;}}
  .ov{{background:#fff;border-radius:16px;padding:16px 20px;color:#555;font-size:15px;box-shadow:0 4px 18px rgba(80,80,120,.08);margin-bottom:18px;}}
  .sec{{font-size:22px;font-weight:800;margin:26px 0 12px;}}
  .sec.s1{{color:#af52de;}} .sec.s2{{color:#5856d6;}}
  img.hero{{width:100%;border-radius:16px;margin:8px 0 18px;box-shadow:0 6px 24px rgba(80,80,120,.12);}}
  .card{{display:flex;gap:16px;background:#fff;border-radius:16px;padding:18px 20px;margin-bottom:14px;box-shadow:0 4px 18px rgba(80,80,120,.08);}}
  .num{{flex:0 0 40px;height:40px;width:40px;border-radius:50%;background:#af52de;color:#fff;font-size:20px;font-weight:700;display:flex;align-items:center;justify-content:center;}}
  .ctitle{{font-size:18px;font-weight:700;color:#1e1e2d;text-decoration:none;}}
  .ctitle:hover{{color:#af52de;}}
  .cbody{{font-size:15px;color:#555;margin:8px 0;line-height:1.6;}}
  .cmeta{{font-size:13px;color:#af52de;}}
  .skill{{background:#fff;border-radius:16px;padding:16px 20px;margin-bottom:14px;box-shadow:0 4px 18px rgba(80,80,120,.08);}}
  .shead{{display:flex;justify-content:space-between;align-items:center;}}
  .sname{{font-size:18px;font-weight:700;}}
  .sname a{{color:#1e1e2d;text-decoration:none;}} .sname a:hover{{color:#5856d6;}}
  .sstars{{color:#ff9500;font-weight:700;font-size:15px;}}
  .sdesc{{font-size:14px;color:#666;margin:8px 0;line-height:1.5;}}
  .susage{{font-size:15px;color:#333;line-height:1.6;}}
  .smeta{{font-size:12px;color:#aaa;margin-top:6px;}}
  .empty{{color:#aaa;font-size:14px;padding:10px 0;}}
  .foot{{margin-top:24px;font-size:13px;color:#999;}}
  .foot a{{color:#5ac8fa;text-decoration:none;}}
</style></head>
<body><div class="wrap">
  <h1>AI 每日要报 · 金融与公司版</h1>
  <div class="sub">{date_str} · 来源 AI HOT + GitHub · 与手机推送同源</div>
  <img class="hero" src="{img_url}" alt="AI 要报信息图">
  <div class="ov">{overview}</div>

  <div class="sec s1">① 全球 AI / 金融科技公司动态</div>
  {c_cards()}

  <div class="sec s2">② 今日好用技能（GitHub 高星 · 含用法）</div>
  {s_cards()}

  <div class="foot">完整版每日与微信推送同步更新 · 图片与网页托管于 <a href="{web_url}">{web_url}</a></div>
</div></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    log("html saved:", out_path)


# ---------- 微信推送 ----------
def push_serverchan(key, title, desp):
    if not key:
        log("SERVERCHAN_KEY 为空，跳过推送")
        return None
    if key.startswith("sctp"):
        uid = key[len("sctp"):].split("t")[0]
        base = f"https://{uid}.push.ft07.com/send/{key}.send"
    else:
        base = f"https://sctapi.ftqq.com/{key}.send"
    data = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
    req = urllib.request.Request(base, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    log("serverchan resp:", resp)
    return resp


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", "ww1y1515-beep/richlife")
    pages_base = os.environ.get("PAGES_BASE_URL", "").strip()
    if not pages_base:
        owner, name = (repo.split("/", 1) + [""])[:2] if "/" in repo else (repo, "")
        pages_base = f"https://{owner}.github.io/{name}" if owner else ""
    img_url = f"{pages_base}/ai_daily.png" if pages_base else ""
    web_url = f"{pages_base}/ai-daily.html" if pages_base else ""

    sf_key = os.environ.get("SILICONFLOW_KEY", "").strip()
    sc_key = os.environ.get("SERVERCHAN_KEY", "").strip()

    font_path = find_font()
    if not font_path:
        log("ERROR: 未找到中文字体")
        sys.exit(1)
    log("font:", font_path)

    # 板块二：公司/金融动态
    companies = collect_company_items()
    log("company items:", len(companies))
    companies = humanize_companies(companies, sf_key)

    # 板块一：GitHub 技能
    skills = collect_skills()
    log("skill repos:", len(skills))
    skills = explain_skills(skills, sf_key)

    bj_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = bj_now.strftime("%Y-%m-%d")

    overview = (f"今日聚焦 AI 与金融的交叉：筛选出 {len(companies)} 条全球 AI / 金融科技公司动态，"
                f"并整理了 {len(skills)} 个高星好用技能（含用法）。用大白话讲清楚，打开就能看。")

    out_dir = os.getcwd()
    data_path = os.path.join(out_dir, "ai-daily.json")
    img_path = os.path.join(out_dir, "ai_daily.png")
    html_path = os.path.join(out_dir, "ai-daily.html")

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"date": date_str, "overview": overview,
                   "companies": companies, "skills": skills},
                  f, ensure_ascii=False, indent=2)
    log("data saved:", data_path)

    make_image(companies, skills, date_str, overview, img_path, font_path)
    make_html(companies, skills, date_str, overview, html_path, img_url, web_url)

    # 微信：精简版 + 完整网页链接
    title = f"AI 要报 {date_str}"
    lines = [f"# AI 要报（{date_str}）· 金融与公司版",
             "> 来源 AI HOT + GitHub · 过去 24 小时", "",
             f"![AI 要报信息图]({img_url})", "",
             overview, ""]
    if companies:
        lines.append("**① 公司 / 金融动态**")
        for i, it in enumerate(companies[:5], 1):
            lines.append(f"{i}. **[{it['title']}]({it['url']})**")
            lines.append(f"> {it['summary']}")
        lines.append("")
    if skills:
        lines.append("**② 今日好用技能**")
        for s in skills[:5]:
            lines.append(f"- [{s['name']}]({s['url']})（{s['stars']}★）")
        lines.append("")
    lines.append(f"📎 完整版网页（与本条同源）：{web_url}")
    lines.append(f"—— 共 {len(companies)} 条动态 / {len(skills)} 个技能")
    desp = "\n".join(lines)

    push_serverchan(sc_key, title, desp)
    log("DONE")


if __name__ == "__main__":
    main()
