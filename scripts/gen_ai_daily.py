#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 圈每日要报生成器（云端版，供 GitHub Actions 运行）
- 抓取 AI HOT 过去 24h 精选（匿名、无需 Key）
- 生成「说人话」简报数据（ai-daily.json）
- 生成信息图（ai_daily.png，自动探测中文字体）
- 生成工作台页面（ai-daily.html）
- 推送带图简报到个人微信（Server酱）
依赖：pip install pillow requests
"""
import json, os, sys, subprocess, datetime
import urllib.request, urllib.parse

AIHOT_URL = "https://aihot.virxact.com/api/v1/items?mode=selected&window=24h&limit=8"
UA = "aihot-skill/1.2.1 (+https://aihot.virxact.com/aihot-skill/)"
MAX_ITEMS = 5

# Life OS 配色
C_PURPLE = (175, 82, 222)
C_CYAN = (90, 200, 250)
C_INDIGO = (88, 86, 214)
C_BG = (245, 245, 250)
C_CARD = (255, 255, 255)
C_TITLE = (30, 30, 45)
C_BODY = (70, 70, 85)
C_MUTE = (130, 130, 150)


def log(*a):
    print("[gen]", *a, flush=True)


def fetch_aihot():
    req = urllib.request.Request(AIHOT_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


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
    """按像素宽度做中文友好换行（逐字符测量）。"""
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


def make_image(items, date_str, overview, out_path, font_path):
    from PIL import Image, ImageDraw, ImageFont
    W = 820
    pad = 40
    title_h = 100
    ov_h = 64
    card_h = 196
    gap = 20
    H = title_h + ov_h + gap + len(items) * (card_h + gap) + 50

    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(font_path, 46, index=0)
    f_date = ImageFont.truetype(font_path, 26, index=0)
    f_cardtitle = ImageFont.truetype(font_path, 30, index=0)
    f_body = ImageFont.truetype(font_path, 24, index=0)
    f_src = ImageFont.truetype(font_path, 22, index=0)

    # 头部
    d.text((pad, 26), "AI 圈每日要报", font=f_title, fill=C_TITLE)
    d.text((pad, 84), f"{date_str}   来源 AI HOT · 过去 24 小时",
           font=f_date, fill=C_MUTE)

    y = title_h + ov_h
    # 总览
    ov_lines = wrap_text(overview, f_body, W - 2 * pad)
    for ln in ov_lines[:2]:
        d.text((pad, y), ln, font=f_body, fill=C_BODY)
        y += 34
    y += gap - 34 * (len(ov_lines[:2]) - 1) if ov_lines else y
    y += 6

    for i, it in enumerate(items):
        x0, y0 = pad, y
        x1, y1 = W - pad, y + card_h
        d.rounded_rectangle([x0, y0, x1, y1], radius=16,
                            fill=C_CARD, outline=(225, 225, 235), width=1)
        # 编号圆点
        cx, cy = x0 + 34, y0 + 34
        d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=C_PURPLE)
        d.text((cx - 11, cy - 16), str(i + 1), font=f_cardtitle, fill=(255, 255, 255))
        # 标题
        tx = x0 + 70
        for j, ln in enumerate(wrap_text(it["title"], f_cardtitle, W - (x0 + 70) - pad)[:2]):
            d.text((tx, y0 + 16 + j * 36), ln, font=f_cardtitle, fill=C_TITLE)
        # 摘要
        sy = y0 + 92
        for ln in wrap_text(it["summary"], f_body, W - (x0 + 24) - pad)[:3]:
            d.text((x0 + 24, sy), ln, font=f_body, fill=C_BODY)
            sy += 32
        # 来源·时间
        d.text((x0 + 24, y1 - 30),
               f"{it['source']} · {it['time']}", font=f_src, fill=C_PURPLE)
        y += card_h + gap

    img.save(out_path)
    log("image saved:", out_path, img.size)


def make_html(items, date_str, overview, out_path, img_url):
    cards = ""
    for i, it in enumerate(items, 1):
        cards += f"""
        <div class="card">
          <div class="num">{i}</div>
          <div class="content">
            <a class="ctitle" href="{it['url']}" target="_blank" rel="noopener">{it['title']}</a>
            <div class="cbody">{it['summary']}</div>
            <div class="cmeta">{it['source']} · {it['time']}</div>
          </div>
        </div>"""
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 每日要报 {date_str}</title>
<style>
  body{{margin:0;background:#f5f5fa;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#2c2c3a;}}
  .wrap{{max-width:760px;margin:0 auto;padding:28px 18px 60px;}}
  h1{{font-size:30px;margin:0 0 4px;}}
  .sub{{color:#888;font-size:14px;margin-bottom:18px;}}
  .ov{{background:#fff;border-radius:16px;padding:16px 20px;color:#555;font-size:15px;box-shadow:0 4px 18px rgba(80,80,120,.08);margin-bottom:20px;}}
  .card{{display:flex;gap:16px;background:#fff;border-radius:16px;padding:18px 20px;margin-bottom:16px;box-shadow:0 4px 18px rgba(80,80,120,.08);}}
  .num{{flex:0 0 40px;height:40px;width:40px;border-radius:50%;background:#af52de;color:#fff;font-size:20px;font-weight:700;display:flex;align-items:center;justify-content:center;}}
  .ctitle{{font-size:18px;font-weight:700;color:#1e1e2d;text-decoration:none;}}
  .ctitle:hover{{color:#af52de;}}
  .cbody{{font-size:15px;color:#555;margin:8px 0;line-height:1.6;}}
  .cmeta{{font-size:13px;color:#af52de;}}
  img.hero{{width:100%;border-radius:16px;margin:10px 0 22px;box-shadow:0 6px 24px rgba(80,80,120,.12);}}
  .back{{display:inline-block;margin-top:10px;color:#5ac8fa;text-decoration:none;font-size:14px;}}
</style></head>
<body><div class="wrap">
  <h1>AI 圈每日要报</h1>
  <div class="sub">{date_str} · 来源 AI HOT · 过去 24 小时</div>
  <img class="hero" src="{img_url}" alt="AI 要报信息图">
  <div class="ov">{overview}</div>
  {cards}
  <a class="back" href="./">← 返回工作台</a>
</div></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    log("html saved:", out_path)


def push_serverchan(key, title, desp):
    if not key:
        log("SERVECHAN_KEY 为空，跳过推送")
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


def clean(text, limit=90):
    if not text:
        return "详见链接。"
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", "ww1y1515-beep/richlife")
    owner, name = (repo.split("/", 1) + [""])[:2] if "/" in repo else (repo, "")
    pages_base = f"https://{owner}.github.io/{name}" if owner else ""
    img_url = f"{pages_base}/ai_daily.png" if pages_base else ""

    font_path = find_font()
    if not font_path:
        log("ERROR: 未找到中文字体，无法生成信息图")
        sys.exit(1)
    log("font:", font_path)

    data = fetch_aihot()
    raw = data.get("items", [])[:MAX_ITEMS]
    if not raw:
        log("ERROR: 未抓到任何条目")
        sys.exit(1)

    bj_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = bj_now.strftime("%Y-%m-%d")

    items = []
    for it in raw:
        src = it.get("source")
        src_name = src.get("name") if isinstance(src, dict) else str(src)
        items.append({
            "title": clean(it.get("title") or it.get("headline") or "AI 进展", 40),
            "summary": clean(it.get("summary") or it.get("content"), 90),
            "source": src_name or "AI HOT",
            "time": parse_bj(it.get("publishedAt") or it.get("discoveredAt")),
            "url": (it.get("links") or {}).get("aihot") or "",
        })

    overview = (f"今天 AI 圈共有 {len(items)} 条值得关注的进展，"
                f"已帮你用大白话整理好了，打开就能看。")

    out_dir = os.getcwd()
    data_path = os.path.join(out_dir, "ai-daily.json")
    img_path = os.path.join(out_dir, "ai_daily.png")
    html_path = os.path.join(out_dir, "ai-daily.html")

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"date": date_str, "overview": overview, "items": items},
                  f, ensure_ascii=False, indent=2)
    log("data saved:", data_path)

    make_image(items, date_str, overview, img_path, font_path)
    make_html(items, date_str, overview, html_path, img_url)

    # 组装推送
    title = f"AI 要报 {date_str}"
    lines = [f"# AI 要报（{date_str}）",
             "> 来源 AI HOT · 过去 24 小时", "",
             f"![AI 要报信息图]({img_url})", "",
             overview, ""]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. **[{it['title']}]({it['url']})**")
        lines.append(f"> {it['summary']}")
        lines.append(f"> {it['source']} · {it['time']}")
        lines.append("")
    lines.append(f"—— 共 {len(items)} 条")
    desp = "\n".join(lines)

    key = os.environ.get("SERVERCHAN_KEY", "")
    push_serverchan(key, title, desp)
    log("DONE")


if __name__ == "__main__":
    main()
