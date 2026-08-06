#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI HOT 每日要报生成器 v3（云端版，供 GitHub Actions 运行）

数据来源：AI HOT 官方「日报接口」
  - 主入口 /api/v1/dailies/latest（当日日报）
  - 若当日尚未生成（404），回退到 /api/v1/dailies?limit=7 取最近一期
结构：固定五个版块（与 AI HOT 日报 sections 对应）
  模型发布/更新 · 产品发布/更新 · 行业动态 · 论文研究 · 技巧与观点
全局连续编号（不在版块内重新计数）。

产出：
  - ai-daily.html  —— 纯单文件、内联 CSS/JS、无外部资源、响应式卡片网格
  - ai_daily.png   —— 信息图（Hero 统计版）
  - ai-daily.json  —— 结构化数据
  - 推微信（Server酱）：精简版 + 完整网页链接
依赖：pip install pillow
"""
import json, os, sys, html, datetime
import urllib.request, urllib.parse, urllib.error

AIHOT = "https://aihot.virxact.com"
UA = "aihot-skill/1.2.1 (+https://aihot.virxact.com/aihot-skill/)"
SF_URL = "https://api.siliconflow.cn/v1/chat/completions"
SF_MODEL = os.environ.get("SF_MODEL", "deepseek-ai/DeepSeek-V3")

# 五个固定版块（顺序即展示顺序），颜色用于 Hero 统计与卡片描边
SECTION_DEFS = [
    ("模型发布/更新", "#5856d6"),
    ("产品发布/更新", "#af52de"),
    ("行业动态",     "#5ac8fa"),
    ("论文研究",     "#34c759"),
    ("技巧与观点",   "#ff9500"),
]

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
           "%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E"
           "%3Cstop offset='0' stop-color='%23af52de'/%3E%3Cstop offset='1' stop-color='%235ac8fa'/%3E"
           "%3C/linearGradient%3E%3C/defs%3E%3Crect width='100' height='100' rx='22' fill='url(%23g)'/%3E"
           "%3Ctext x='50' y='71' font-size='54' font-family='Arial,sans-serif' font-weight='bold' "
           "text-anchor='middle' fill='white'%3EAI%3C/text%3E%3C/svg%3E")


def log(*a):
    print("[gen]", *a, flush=True)


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


# ---------- 日报拉取（含回退） ----------
def fetch_daily():
    # 1) 当日日报
    try:
        d = _get_json(f"{AIHOT}/api/v1/dailies/latest")
        if d and "report" in d and d["report"].get("sections") is not None:
            return d["report"], d["report"].get("date")
    except Exception as e:
        log("latest daily 失败，尝试回退：", e)
    # 2) 回退：取最近一期
    try:
        idx = _get_json(f"{AIHOT}/api/v1/dailies?limit=7")
        items = (idx or {}).get("items", []) or []
        if items:
            recent = items[0].get("date")
            d = _get_json(f"{AIHOT}/api/v1/dailies/{recent}")
            if d and "report" in d and d["report"].get("sections") is not None:
                log("回退到最近一期：", recent)
                return d["report"], recent
    except Exception as e:
        log("fallback daily 失败：", e)
    raise RuntimeError("无法获取 AI HOT 日报（latest 与 fallback 均失败）")


def canonical(label):
    for name, _ in SECTION_DEFS:
        if name == label or name in label or label in name:
            return name
    return label


# ---------- 时间格式 ----------
def fmt_date(iso_date):
    try:
        y, m, d = iso_date.split("-")
        return f"{int(y)}年{int(m)}月{int(d)}日"
    except Exception:
        return iso_date


def fmt_gen(iso_dt):
    if not iso_dt:
        return ""
    try:
        s = iso_dt.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
        dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        return dt.strftime("%H:%M")
    except Exception:
        return ""


# ---------- 文本工具 ----------
def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def trunc(s, n=60):
    s = " ".join(str(s).split())
    if len(s) <= n:
        return s
    return s[:n - 1] + "…"


def item_link(it):
    links = it.get("links") or {}
    return links.get("aihot") or links.get("original") or "#"


def item_source(it):
    src = it.get("source") or {}
    return src.get("name") or "AI HOT"


# ---------- SiliconFlow 摘要压缩（≤60 字） ----------
def sf_chat(system, user, key, as_json=False, max_tokens=1600):
    if not key:
        return None
    payload = {
        "model": SF_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    if as_json:
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SF_URL, data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.load(r)
        return resp["choices"][0]["message"]["content"]
    except Exception as e:
        log("SF error:", e)
        return None


def compress_summaries(items, key):
    """把超过 60 字的摘要压缩到 ≤60 字（保留核心事实）。失败则截断兜底。"""
    longs = [(i, it.get("summary", "")) for i, it in enumerate(items)
             if len(" ".join(str(it.get("summary", "")).split())) > 60]
    if key and longs:
        sys_p = ("把下面的 AI 资讯摘要每条压缩成不超过 60 个汉字的一句话，保留核心事实与主语，"
                 "不要加『据悉/值得关注』等套话。只输出 JSON："
                 '{"items":[{"i":序号,"s":"压缩后文字"}]}，不要多余文字。')
        user_p = json.dumps([{"i": i, "summary": s} for i, s in longs],
                            ensure_ascii=False)
        out = sf_chat(sys_p, user_p, key, as_json=True)
        mp = {}
        if out:
            try:
                obj = json.loads(out)
                for e in obj.get("items", []):
                    mp[e["i"]] = e.get("s", "")
            except Exception as e:
                log("SF parse err:", e)
        for i, it in enumerate(items):
            if i in mp and mp[i]:
                it["summary_short"] = trunc(mp[i])
            else:
                it["summary_short"] = trunc(it.get("summary", ""))
    else:
        for it in items:
            it["summary_short"] = trunc(it.get("summary", ""))


# ---------- 字体 ----------
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
        out = subprocess.check_output(["fc-match", "-f", "%{file}", ":lang=zh"],
                                      stderr=subprocess.DEVNULL).decode().strip()
        if out and os.path.exists(out):
            return out
    except Exception:
        pass
    return None


import subprocess  # 放在末尾避免循环导入问题（仅在 find_font 内使用）


# ---------- 信息图（Hero 统计版） ----------
def make_image(sections_map, counts, date_human, total, out_path, font_path):
    from PIL import Image, ImageDraw, ImageFont
    W = 820
    pad = 40
    title_h = 110
    sec_header_h = 56
    item_line = 46
    max_items = 4  # 每版块最多展示条数
    H = title_h + 30
    for name, _ in SECTION_DEFS:
        its = sections_map[name][:max_items]
        H += sec_header_h + max(len(its), 1) * item_line + 18

    img = Image.new("RGB", (W, H), (245, 245, 250))
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(font_path, 46, index=0)
    f_date = ImageFont.truetype(font_path, 24, index=0)
    f_sec = ImageFont.truetype(font_path, 28, index=0)
    f_item = ImageFont.truetype(font_path, 22, index=0)
    f_num = ImageFont.truetype(font_path, 26, index=0)

    # 顶部渐变条
    for y in range(title_h):
        t = y / title_h
        col = (int(175 + (90 - 175) * t), int(82 + (200 - 82) * t), int(222 + (250 - 222) * t))
        d.line([(0, y), (W, y)], fill=col)
    d.text((pad, 26), "AI HOT 每日要报", font=f_title, fill=(255, 255, 255))
    d.text((pad, 82), f"{date_human}  ·  共 {total} 条", font=f_date, fill=(235, 235, 245))

    y = title_h + 24
    for idx, (name, col) in enumerate(SECTION_DEFS):
        cnt = counts[name]
        d.rounded_rectangle([pad, y, W - pad, y + 44], radius=12, fill=(255, 255, 255),
                            outline=(225, 225, 235), width=1)
        d.ellipse([pad + 14, y + 12, pad + 34, y + 32], fill=col)
        d.text((pad + 48, y + 8), f"{idx + 1}. {name}", font=f_sec, fill=(40, 40, 55))
        d.text((W - pad - 70, y + 10), f"{cnt} 条", font=f_num, fill=col)
        y += sec_header_h + 6
        its = sections_map[name][:max_items]
        if not its:
            d.text((pad + 16, y), "（暂无）", font=f_item, fill=(160, 160, 175))
            y += item_line
        for it in its:
            d.text((pad + 16, y), f"• {trunc(it['title'], 26)}",
                   font=f_item, fill=(80, 80, 95))
            y += item_line
        y += 12

    img.save(out_path)
    log("image saved:", out_path, img.size)


# ---------- 完整版网页（纯单文件内联） ----------
HTML_TPL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI HOT 每日要报 {DATE_HUMAN}</title>
<link rel="icon" href="{FAVICON}">
<style>
  :root{--bg:#f4f5fa;--card:#fff;--ink:#1e1e2d;--body:#555;--mute:#9a9aa8;}
  *{box-sizing:border-box;}
  html{scroll-behavior:smooth;}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;}
  a{color:inherit;}
  .hero{background:linear-gradient(120deg,#5856d6 0%,#af52de 50%,#5ac8fa 100%);
    color:#fff;padding:30px 18px 26px;}
  .hero-inner{max-width:1100px;margin:0 auto;}
  .brand{font-size:14px;letter-spacing:2px;opacity:.92;font-weight:700;}
  .hero h1{font-size:34px;margin:8px 0 4px;}
  .hero .sub{opacity:.95;font-size:15px;margin:0 0 18px;}
  .stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;}
  .stat{background:rgba(255,255,255,.16);backdrop-filter:blur(4px);
    border:1px solid rgba(255,255,255,.28);border-radius:14px;padding:12px 8px;
    text-align:center;text-decoration:none;color:#fff;transition:.15s;}
  .stat:hover{background:rgba(255,255,255,.28);transform:translateY(-2px);}
  .stat .num{display:block;font-size:26px;font-weight:800;line-height:1.1;}
  .stat .lbl{display:block;font-size:12.5px;margin-top:3px;opacity:.95;}
  .anchornav{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.92);
    backdrop-filter:blur(8px);border-bottom:1px solid #e7e7ef;
    display:flex;gap:8px;overflow-x:auto;padding:10px 16px;max-width:1100px;margin:0 auto;}
  .anchornav a{white-space:nowrap;text-decoration:none;font-size:13.5px;font-weight:600;
    color:#444;padding:6px 12px;border-radius:999px;background:#eef0f7;border:1px solid transparent;transition:.15s;}
  .anchornav a b{color:#888;margin-left:4px;}
  .anchornav a.active{color:#fff;background:var(--c,#af52de);border-color:var(--c,#af52de);}
  .anchornav a.active b{color:rgba(255,255,255,.85);}
  main{max-width:1100px;margin:0 auto;padding:22px 16px 40px;}
  .sec{margin-bottom:30px;scroll-margin-top:60px;}
  .sec h2{font-size:22px;display:flex;align-items:center;gap:10px;margin:0 0 14px;}
  .sec h2 .dot{width:14px;height:14px;border-radius:4px;display:inline-block;}
  .sec h2 .count{font-size:14px;color:#fff;background:#c9c9d6;border-radius:999px;
    padding:1px 10px;font-weight:700;}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;}
  .card{background:var(--card);border-radius:16px;padding:16px 18px;
    box-shadow:0 4px 18px rgba(80,80,120,.08);border-top:3px solid var(--c,#af52de);
    display:flex;flex-direction:column;gap:10px;}
  .card-top{display:flex;gap:12px;align-items:flex-start;}
  .idx{flex:0 0 30px;height:30px;width:30px;border-radius:50%;background:var(--c,#af52de);
    color:#fff;font-size:15px;font-weight:800;display:flex;align-items:center;justify-content:center;}
  .title{font-size:17px;font-weight:700;color:var(--ink);text-decoration:none;line-height:1.4;}
  .title:hover{text-decoration:underline;}
  .chip{display:inline-block;align-self:flex-start;font-size:12.5px;color:#666;
    background:#f0f1f7;border-radius:999px;padding:3px 11px;}
  .summary{font-size:14.5px;color:var(--body);line-height:1.65;margin:0;flex:1;}
  .readmore{font-size:13.5px;font-weight:700;color:var(--c,#af52de);text-decoration:none;}
  .readmore:hover{text-decoration:underline;}
  footer{max-width:1100px;margin:0 auto;padding:18px 16px 50px;font-size:13px;color:var(--mute);
    border-top:1px solid #e7e7ef;}
  footer a{color:#5ac8fa;text-decoration:none;}
  @media (max-width:640px){
    .stats{grid-template-columns:repeat(2,1fr);}
    .hero h1{font-size:27px;}
    .grid{grid-template-columns:1fr;}
  }
</style></head>
<body>
  <header class="hero"><div class="hero-inner">
    <div class="brand">AI HOT · 每日要报</div>
    <h1>{DATE_HUMAN}</h1>
    <p class="sub">共 {TOTAL} 条精选 · 北京时间 {GEN_TIME} 生成</p>
    <div class="stats">{STATS_HTML}</div>
  </div></header>

  <nav class="anchornav">{NAV_HTML}</nav>

  <main>{SECTIONS_HTML}</main>

  <footer>
    共 {TOTAL} 条 · 数据来源：AI HOT（<a href="{REPORT_LINK}" target="_blank" rel="noopener noreferrer">aihot.virxact.com</a>）
    · 条目版权归原作者所有 · 摘要由 AI HOT 与智能压缩生成
  </footer>
<script>
  var links=[].slice.call(document.querySelectorAll('.anchornav a'));
  var secs=[].slice.call(document.querySelectorAll('section.sec'));
  if('IntersectionObserver' in window){
    var obs=new IntersectionObserver(function(es){
      es.forEach(function(e){
        if(e.isIntersecting){
          var id=e.target.id;
          links.forEach(function(l){l.classList.toggle('active',l.getAttribute('href')==='#'+id);});
        }
      });
    },{rootMargin:'-45% 0px -50% 0px'});
    secs.forEach(function(s){obs.observe(s);});
  }
</script>
</body></html>"""


def make_html(sections_map, counts, date_human, gen_time, total, report_link, out_path):
    stats_html = ""
    nav_html = ""
    for idx, (name, col) in enumerate(SECTION_DEFS):
        cnt = counts[name]
        stats_html += (f'<a class="stat" href="#sec-{idx}" style="--c:{col}">'
                       f'<span class="num">{cnt}</span><span class="lbl">{esc(name)}</span></a>')
        nav_html += (f'<a href="#sec-{idx}" data-sec="{idx}" style="--c:{col}">'
                     f'{esc(name)} <b>{cnt}</b></a>')

    sections_html = ""
    for idx, (name, col) in enumerate(SECTION_DEFS):
        items = sections_map[name]
        cards = ""
        for it in items:
            link = esc(item_link(it))
            src = esc(item_source(it))
            summ = esc(it.get("summary_short") or trunc(it.get("summary", "")))
            cards += f"""
        <article class="card" style="--c:{col}">
          <div class="card-top"><span class="idx">{it['_n']}</span>
            <a class="title" href="{link}" target="_blank" rel="noopener noreferrer">{esc(it['title'])}</a>
          </div>
          <span class="chip">{src}</span>
          <p class="summary">{summ}</p>
          <a class="readmore" href="{link}" target="_blank" rel="noopener noreferrer">阅读原文 →</a>
        </article>"""
        sections_html += f"""
    <section id="sec-{idx}" class="sec">
      <h2><span class="dot" style="background:{col}"></span>{idx + 1}. {esc(name)} <span class="count">{len(items)}</span></h2>
      <div class="grid">{cards if cards else '<p class="summary">（本版块今日暂无条目）</p>'}</div>
    </section>"""

    html_out = (HTML_TPL
                .replace("{DATE_HUMAN}", date_human)
                .replace("{GEN_TIME}", gen_time)
                .replace("{TOTAL}", str(total))
                .replace("{STATS_HTML}", stats_html)
                .replace("{NAV_HTML}", nav_html)
                .replace("{SECTIONS_HTML}", sections_html)
                .replace("{REPORT_LINK}", esc(report_link))
                .replace("{FAVICON}", FAVICON))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
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

    # 拉日报（含回退）
    report, used_date = fetch_daily()
    log("daily date:", used_date, "sections:", len(report.get("sections", [])))

    # 分组 + 全局连续编号
    sections_map = {name: [] for name, _ in SECTION_DEFS}
    all_items = []
    n = 0
    for s in report.get("sections", []):
        name = canonical(s.get("label", ""))
        if name not in sections_map:
            log("跳过未知版块：", s.get("label"))
            continue
        for it in s.get("items", []):
            n += 1
            it["_n"] = n
            sections_map[name].append(it)
            all_items.append(it)
    total = n
    counts = {name: len(sections_map[name]) for name, _ in SECTION_DEFS}
    log("total items:", total, "counts:", counts)

    # 摘要压缩（≤60 字）
    compress_summaries(all_items, sf_key)

    date_human = fmt_date(used_date)
    gen_time = fmt_gen(report.get("generatedAt", ""))
    report_link = (report.get("links") or {}).get("aihot") or f"{AIHOT}/daily/{used_date}"

    out_dir = os.getcwd()
    data_path = os.path.join(out_dir, "ai-daily.json")
    img_path = os.path.join(out_dir, "ai_daily.png")
    html_path = os.path.join(out_dir, "ai-daily.html")

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": used_date, "date_human": date_human, "total": total,
            "counts": counts, "report_link": report_link,
            "sections": [{ "name": name,
                            "items": [{"n": it["_n"], "title": it.get("title"),
                                       "summary": it.get("summary_short"),
                                       "source": item_source(it), "url": item_link(it)}
                                      for it in sections_map[name]] }
                          for name, _ in SECTION_DEFS],
        }, f, ensure_ascii=False, indent=2)
    log("data saved:", data_path)

    make_image(sections_map, counts, date_human, total, img_path, font_path)
    make_html(sections_map, counts, date_human, gen_time, total, report_link, html_path)

    # 微信：精简版 + 完整网页链接
    title = f"AI HOT 要报 {date_human}"
    lines = [f"# AI HOT 每日要报（{date_human}）",
             f"> 共 {total} 条 · 五版块：模型/产品/行业/论文/技巧", "",
             f"![AI HOT 信息图]({img_url})", ""]
    for idx, (name, _) in enumerate(SECTION_DEFS):
        its = sections_map[name][:5]
        if not its:
            continue
        lines.append(f"**{idx + 1}. {name}**（{counts[name]}）")
        for it in its:
            lines.append(f"- [{it['title']}]({item_link(it)})")
        lines.append("")
    lines.append(f"📎 完整版网页（与本条同源）：{web_url}")
    lines.append(f"—— 共 {total} 条 / 五版块")
    desp = "\n".join(lines)

    push_serverchan(sc_key, title, desp)
    log("DONE")


if __name__ == "__main__":
    main()
