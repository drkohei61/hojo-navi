"""
補助金ナビ 自動スクレイピングスクリプト
対象サイト: ミラサポplus / J-Net21 / 国土交通省 / 経済産業省 / 厚生労働省
実行: python scraper.py
出力: subsidies_data.json を上書き更新
"""

import json
import time
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── 設定 ──────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9",
}
TIMEOUT = 20
SLEEP   = 1.5   # サイトへの負荷を抑えるための待機秒数

OUTPUT_FILE = Path(__file__).parent / "subsidies_data.json"

# カテゴリ判定キーワード
CAT_KEYWORDS = {
    "exterior":   ["外壁", "屋根", "塗装", "防水", "外装", "リフォーム", "改修", "修繕"],
    "energy":     ["省エネ", "断熱", "遮熱", "ZEH", "LCCM", "太陽光", "創エネ", "節電"],
    "management": ["IT", "DX", "デジタル", "経営", "販路", "広告", "ウェブ", "システム", "クラウド"],
    "hr":         ["人材", "雇用", "育成", "研修", "採用", "キャリア", "技能", "職人"],
    "equipment":  ["設備", "機械", "器具", "車両", "機器", "装置", "ロボット"],
}

TAG_KEYWORDS = {
    "small":    ["小規模", "20名以下", "従業員20人以下"],
    "mid":      ["中小企業", "中小"],
    "indiv":    ["個人事業", "フリーランス", "一人親方"],
    "exterior": ["外壁", "屋根", "塗装", "リフォーム"],
    "energy":   ["省エネ", "断熱", "ZEH"],
    "dx":       ["IT", "DX", "デジタル"],
    "hr":       ["人材", "雇用", "育成"],
    "equip":    ["設備", "機械"],
}

REGION_KEYWORDS = {
    "fukuoka":  ["福岡"],
    "aichi":    ["愛知", "名古屋"],
    "osaka":    ["大阪"],
    "kanagawa": ["神奈川", "横浜"],
    "tokyo":    ["東京"],
}

PAINT_KEYWORDS = [
    "塗装", "外壁", "屋根", "リフォーム", "省エネ", "断熱", "遮熱",
    "住宅改修", "外装", "防水", "中小企業", "小規模", "人材", "設備投資", "IT導入",
]


# ── ユーティリティ ────────────────────────────────
def get(url: str) -> BeautifulSoup | None:
    """GETリクエストを実行してBeautifulSoupを返す。失敗時はNone。"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"  [WARN] fetch failed: {url} → {e}")
        return None


def is_paint_related(text: str) -> bool:
    """テキストが塗装業に関連しているか判定。"""
    return any(kw in text for kw in PAINT_KEYWORDS)


def guess_cat(text: str) -> tuple[str, str]:
    """テキストからカテゴリを推定。(ct, ctL) を返す。"""
    for cat, kws in CAT_KEYWORDS.items():
        if any(kw in text for kw in kws):
            labels = {
                "exterior":   "外装・塗装",
                "energy":     "省エネ・断熱",
                "management": "経営・DX",
                "hr":         "人材・雇用",
                "equipment":  "設備投資",
            }
            return cat, labels[cat]
    return "exterior", "外装・塗装"


def guess_tags(text: str, lv: str) -> list[str]:
    """テキストからタグ一覧を推定。"""
    tags = [lv]
    for tag, kws in TAG_KEYWORDS.items():
        if any(kw in text for kw in kws):
            tags.append(tag)
    for region, kws in REGION_KEYWORDS.items():
        if any(kw in text for kw in kws):
            tags.append(region)
    if not any(t in tags for t in ["small", "mid", "indiv"]):
        tags.extend(["mid", "small"])
    return list(dict.fromkeys(tags))  # 重複除去・順序保持


def guess_status(text: str) -> str:
    """受付状況を推定。"""
    if any(kw in text for kw in ["受付終了", "終了", "締め切り", "募集終了", "閉切"]):
        return "closed"
    if any(kw in text for kw in ["予定", "近日", "公募予定", "準備中"]):
        return "soon"
    return "open"


def clean(text: str) -> str:
    """空白・改行を整理。"""
    return re.sub(r"\s+", " ", text or "").strip()


def make_entry(
    title: str,
    issuer: str,
    lv: str,
    lv_l: str,
    desc: str,
    url: str,
    amount: str = "—",
    rate: str = "—",
    target: str = "中小企業・小規模事業者",
    period: str = "2025年度",
    steps: list[str] | None = None,
    docs: list[str] | None = None,
    note: str = "",
    extra_id: int = 0,
) -> dict:
    """補助金エントリを生成。"""
    ct, ct_l = guess_cat(title + " " + desc)
    tags = guess_tags(title + " " + desc + " " + issuer, lv)
    st   = guess_status(title + " " + desc + " " + period)
    return {
        "id":     extra_id,
        "lv":     lv,
        "lvL":    lv_l,
        "ct":     ct,
        "ctL":    ct_l,
        "st":     st,
        "tags":   tags,
        "title":  clean(title),
        "issuer": clean(issuer),
        "desc":   clean(desc)[:200],
        "amount": clean(amount),
        "rate":   clean(rate),
        "target": clean(target),
        "period": clean(period),
        "url":    url,
        "steps":  steps or ["公式サイトで申請手順を確認してください"],
        "docs":   docs or ["公式サイトで必要書類を確認してください"],
        "note":   note or "自動取得データ。内容を必ず公式サイトで確認してください。",
    }


# ── スクレイパー群 ────────────────────────────────

def scrape_mirasapo() -> list[dict]:
    """ミラサポplus から補助金・助成金情報を取得。"""
    print("→ ミラサポplus を取得中…")
    results = []
    url = "https://mirasapo-plus.go.jp/subsidy/"
    soup = get(url)
    if not soup:
        return results

    cards = soup.select("article, .card, .subsidy-item, li.item, .post")
    if not cards:
        cards = soup.select("a[href*='subsidy']")

    for card in cards[:30]:
        title_el = card.select_one("h2, h3, h4, .title, .name, strong")
        if not title_el:
            continue
        title = clean(title_el.get_text())
        if not title or len(title) < 5:
            continue
        if not is_paint_related(title):
            continue

        desc_el = card.select_one("p, .desc, .summary, .text")
        desc = clean(desc_el.get_text()) if desc_el else ""

        link_el = card.select_one("a[href]")
        link = link_el["href"] if link_el else url
        if link.startswith("/"):
            link = "https://mirasapo-plus.go.jp" + link

        results.append(make_entry(
            title=title, issuer="中小企業庁 / ミラサポplus",
            lv="national", lv_l="国",
            desc=desc or f"{title}に関する補助金・助成金情報。",
            url=link,
        ))

    print(f"  取得件数: {len(results)}")
    return results


def scrape_jnet21() -> list[dict]:
    """J-Net21 支援情報ヘッドライン から取得。"""
    print("→ J-Net21 を取得中…")
    results = []
    url = "https://j-net21.smrj.go.jp/headline/"
    soup = get(url)
    if not soup:
        return results

    items = soup.select(".headlineList li, .news-list li, article, .item")
    if not items:
        items = soup.select("li")

    for item in items[:40]:
        link_el = item.select_one("a[href]")
        if not link_el:
            continue
        title = clean(link_el.get_text())
        if not title or len(title) < 6:
            continue
        if not is_paint_related(title):
            continue

        href = link_el["href"]
        if href.startswith("/"):
            href = "https://j-net21.smrj.go.jp" + href
        elif not href.startswith("http"):
            continue

        desc_el = item.select_one("p, .summary, .text, span:not(.date)")
        desc = clean(desc_el.get_text()) if desc_el else ""

        results.append(make_entry(
            title=title, issuer="中小機構 / J-Net21",
            lv="national", lv_l="国",
            desc=desc or f"中小企業向け支援情報: {title}",
            url=href,
        ))

    print(f"  取得件数: {len(results)}")
    return results


def scrape_mlit() -> list[dict]:
    """国土交通省 住宅局 から住宅リフォーム・省エネ補助金を取得。"""
    print("→ 国土交通省 を取得中…")
    results = []
    url = "https://www.mlit.go.jp/jutakukentiku/house/jutakukentiku_house_tk2_000031.html"
    soup = get(url)
    if not soup:
        return results

    links = soup.select("a[href]")
    for a in links:
        title = clean(a.get_text())
        if not title or len(title) < 8:
            continue
        if not any(kw in title for kw in ["補助", "支援", "事業", "キャンペーン", "省エネ", "リフォーム"]):
            continue
        if not is_paint_related(title):
            continue

        href = a["href"]
        if href.startswith("/"):
            href = "https://www.mlit.go.jp" + href
        elif not href.startswith("http"):
            continue

        results.append(make_entry(
            title=title, issuer="国土交通省",
            lv="national", lv_l="国",
            desc=f"国土交通省による住宅支援施策。{title}",
            url=href,
            steps=[
                "登録施工業者への工事依頼",
                "補助金申請（施工業者または施主が申請）",
                "工事完了後に実績報告・補助金受領",
            ],
            docs=["工事請負契約書", "施工前後写真", "製品証明書（必要な場合）"],
        ))

    print(f"  取得件数: {len(results)}")
    return results


def scrape_meti() -> list[dict]:
    """経済産業省 補助金・助成金ページから取得。"""
    print("→ 経済産業省 を取得中…")
    results = []
    url = "https://www.meti.go.jp/information/publicoffer/hojyokin/index.html"
    soup = get(url)
    if not soup:
        return results

    for a in soup.select("a[href]"):
        title = clean(a.get_text())
        if not title or len(title) < 8:
            continue
        if not any(kw in title for kw in ["補助", "助成", "支援", "給付"]):
            continue
        if not is_paint_related(title):
            continue

        href = a["href"]
        if href.startswith("/"):
            href = "https://www.meti.go.jp" + href
        elif not href.startswith("http"):
            continue

        results.append(make_entry(
            title=title, issuer="経済産業省 / 中小企業庁",
            lv="national", lv_l="国",
            desc=f"中小企業・小規模事業者向け支援施策。{title}",
            url=href,
            steps=[
                "GビズIDプライムの取得（必要な場合）",
                "公式ポータルから申請",
                "採択通知後に事業実施",
                "完了報告・補助金受領",
            ],
            docs=["申請書", "事業計画書", "決算書（直近2期）"],
        ))

    print(f"  取得件数: {len(results)}")
    return results


def scrape_mhlw() -> list[dict]:
    """厚生労働省 助成金ページから雇用・人材関連助成金を取得。"""
    print("→ 厚生労働省 を取得中…")
    results = []
    url = "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/koyou/kyufukin/index.html"
    soup = get(url)
    if not soup:
        return results

    for a in soup.select("a[href]"):
        title = clean(a.get_text())
        if not title or len(title) < 8:
            continue
        if not any(kw in title for kw in ["助成金", "支援", "コース", "加算"]):
            continue
        if not is_paint_related(title):
            continue

        href = a["href"]
        if href.startswith("/"):
            href = "https://www.mhlw.go.jp" + href
        elif not href.startswith("http"):
            continue

        results.append(make_entry(
            title=title, issuer="厚生労働省",
            lv="national", lv_l="国",
            desc=f"雇用・人材育成に関する助成金。{title}",
            url=href,
            target="雇用保険適用事業主",
            steps=[
                "申請前に管轄のハローワーク・労働局に相談",
                "計画書・申請書を提出",
                "要件確認後、支給決定",
            ],
            docs=["申請書", "雇用契約書", "賃金台帳", "出勤簿"],
        ))

    print(f"  取得件数: {len(results)}")
    return results


def scrape_smrj_jizokuka() -> list[dict]:
    """小規模事業者持続化補助金の公式情報を取得。"""
    print("→ 持続化補助金 を取得中…")
    results = []
    url = "https://s23.jizokukahojokin.info/"
    soup = get(url)
    if not soup:
        return results

    # トップページのニュース・概要を取得
    news_items = soup.select(".news li, .info li, .topics li, article")
    for item in news_items[:5]:
        title = clean(item.get_text())
        if not title or len(title) < 6:
            continue
        results.append(make_entry(
            title=f"小規模事業者持続化補助金 — {title[:40]}",
            issuer="中小企業庁 / 商工会議所",
            lv="national", lv_l="国",
            desc="小規模事業者の販路開拓・業務効率化を支援する補助金。広告費・HP制作費・設備費等が対象。",
            url=url,
            amount="最大250万円",
            rate="補助率2/3",
            target="小規模事業者（従業員20名以下）",
            steps=[
                "経営計画書・補助事業計画書の作成",
                "管轄の商工会議所・商工会での確認・受付",
                "電子申請または郵送提出",
                "採択後に事業実施・完了報告",
            ],
            docs=["経営計画書", "補助事業計画書", "確定申告書（直近1期）"],
        ))
        break  # 代表1件のみ

    if not results:
        # フォールバック: トップページ自体を1件として登録
        results.append(make_entry(
            title="小規模事業者持続化補助金",
            issuer="中小企業庁 / 商工会議所",
            lv="national", lv_l="国",
            desc="小規模事業者の販路開拓・業務効率化を支援。広告費・HP制作費・設備費等が対象。",
            url=url,
            amount="最大250万円",
            rate="補助率2/3",
            target="小規模事業者（従業員20名以下）",
            steps=[
                "経営計画書・補助事業計画書の作成",
                "管轄商工会議所での確認・受付",
                "電子申請または郵送提出",
            ],
            docs=["経営計画書", "補助事業計画書", "確定申告書（直近1期）"],
        ))

    print(f"  取得件数: {len(results)}")
    return results


# ── 既存データとのマージ ──────────────────────────

def load_existing() -> list[dict]:
    """既存の subsidies_data.json を読み込む。なければ空リスト。"""
    if OUTPUT_FILE.exists():
        try:
            data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            return data.get("subsidies", [])
        except Exception:
            return []
    return []


def deduplicate(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    """
    既存データと新規取得データをマージ。
    - 同じタイトルがあれば既存を優先（手動編集を上書きしない）
    - 既存にないタイトルは末尾に追加
    - IDを振り直す
    """
    existing_titles = {e["title"] for e in existing}
    added = 0
    for entry in new_entries:
        if entry["title"] not in existing_titles:
            existing.append(entry)
            existing_titles.add(entry["title"])
            added += 1

    # IDを1から振り直す
    for i, e in enumerate(existing, start=1):
        e["id"] = i

    print(f"\n新規追加: {added} 件 / 合計: {len(existing)} 件")
    return existing


# ── メイン ──────────────────────────────────────

def main():
    print("=" * 50)
    print(f"補助金データ 自動更新スクリプト")
    print(f"実行日: {date.today()}")
    print("=" * 50)

    # 既存データをロード
    existing = load_existing()
    print(f"既存データ: {len(existing)} 件\n")

    # 各サイトをスクレイプ
    scrapers = [
        scrape_mirasapo,
        scrape_jnet21,
        scrape_mlit,
        scrape_meti,
        scrape_mhlw,
        scrape_smrj_jizokuka,
    ]

    new_entries = []
    for scraper in scrapers:
        try:
            entries = scraper()
            new_entries.extend(entries)
        except Exception as e:
            print(f"  [ERROR] {scraper.__name__}: {e}")
        time.sleep(SLEEP)

    print(f"\n取得合計: {len(new_entries)} 件（重複含む）")

    # マージ
    merged = deduplicate(existing, new_entries)

    # 出力
    output = {
        "updated": str(date.today()),
        "auto_updated": True,
        "subsidies": merged,
    }
    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n✅ {OUTPUT_FILE} を更新しました（{len(merged)} 件）")
    print("=" * 50)


if __name__ == "__main__":
    main()
