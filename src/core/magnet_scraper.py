"""
磁力链接搜索引擎抓取器 (数据源: sukebei.nyaa.si)

无需 Playwright 浏览器引擎，纯 HTTP 请求 + HTML 解析。
在 GitHub Actions 数据中心 IP 上完全可达。
"""

import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser


class NyaaResultParser(HTMLParser):
    """解析 sukebei.nyaa.si 搜索结果 HTML 的状态机"""

    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._in_title_cell = False
        self._in_size_cell = False
        self._in_seeders_cell = False
        self._td_index = 0
        self._in_tr = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == 'tr':
            self._in_tr = True
            self._td_index = 0
            self._current = {"title": "", "magnet": "", "size": "", "seeders": 0}

        elif tag == 'td' and self._in_tr:
            self._td_index += 1
            css_class = attrs_dict.get('class', '')
            # nyaa 表格结构: col1=category, col2=title, col3=links, col4=size, col5=date, col6=seeders, col7=leechers
            if self._td_index == 2:
                self._in_title_cell = True
            elif self._td_index == 4:
                self._in_size_cell = True
            elif self._td_index == 6:
                self._in_seeders_cell = True

        elif tag == 'a' and self._current:
            href = attrs_dict.get('href', '')
            title = attrs_dict.get('title', '')

            # 提取标题（在标题列的链接中）
            if self._in_title_cell and href.startswith('/view/') and title:
                self._current["title"] = title

            # 提取磁力链接
            if href.startswith('magnet:'):
                self._current["magnet"] = href

    def handle_data(self, data):
        if self._current:
            if self._in_size_cell:
                text = data.strip()
                if text and any(u in text for u in ['GiB', 'MiB', 'KiB', 'TiB', 'GB', 'MB']):
                    self._current["size"] = text
            elif self._in_seeders_cell:
                text = data.strip()
                if text.isdigit():
                    self._current["seeders"] = int(text)

    def handle_endtag(self, tag):
        if tag == 'td':
            self._in_title_cell = False
            self._in_size_cell = False
            self._in_seeders_cell = False

        elif tag == 'tr' and self._in_tr:
            self._in_tr = False
            if self._current and self._current.get("magnet"):
                self.results.append(self._current)
            self._current = None


class MagnetScraper:
    """基于 sukebei.nyaa.si 的磁力链接搜索引擎（纯 HTTP，无需浏览器）"""

    BASE_URL = "https://sukebei.nyaa.si/"
    REQUEST_TIMEOUT = 15
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    )

    def search_keyword(self, keyword: str, max_results: int = 10) -> list[dict]:
        """
        搜索指定关键字，返回结果列表

        Args:
            keyword: 搜索关键字（如 "SSIS-001"）
            max_results: 最多返回的结果数量

        Returns:
            包含 title, magnet, size, seeders 的字典列表
        """
        encoded = urllib.parse.quote(keyword)
        # f=0 全部, c=0_0 全分类, s=seeders 按做种数排序, o=desc 降序
        url = f"{self.BASE_URL}?q={encoded}&f=0&c=0_0&s=seeders&o=desc"
        print(f"  🔎 搜索: {url}")

        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            resp = urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT)
            html = resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"  ❌ HTTP 请求失败: {e}")
            return []

        # 解析 HTML
        parser = NyaaResultParser()
        parser.feed(html)
        results = parser.results[:max_results]

        print(f"  📋 找到 {len(results)} 条有效结果")
        return results

    def score_result(self, result: dict, keyword: str) -> int:
        """
        对搜索结果进行质量评分

        评分维度：
        - 标题精准匹配原始关键字 (+10)
        - 含中文字幕相关标记 (+8)
        - 含高清画质标记 (+3)
        - 做种数量加分 (+基于做种数的浮动分)
        - 文件体积加分 (+基于体积的浮动分)
        """
        score = 0
        title = result.get("title", "").upper()

        # 关键字精准匹配
        normalized_keyword = keyword.upper().replace("-", "").replace("_", "")
        normalized_title = title.replace("-", "").replace("_", "").replace(" ", "")
        if normalized_keyword in normalized_title:
            score += 10

        # 中文字幕加分（权重最高，这是核心需求）
        subtitle_markers = ["中文", "字幕", "中字", "CH-SUB", "CHINESE", "C-SUB"]
        for marker in subtitle_markers:
            if marker.upper() in title:
                score += 8
                break

        # 高清画质加分
        hd_markers = ["1080P", "4K", "2160P", "FHD", "UHD", "H265", "H.265", "HEVC"]
        for marker in hd_markers:
            if marker in title:
                score += 3
                break

        # 做种数评分
        seeders = result.get("seeders", 0)
        if seeders > 50:
            score += 5
        elif seeders > 10:
            score += 3
        elif seeders > 0:
            score += 1

        # 文件体积评分
        size_gb = self._parse_size_gb(result.get("size", ""))
        score += min(int(size_gb * 2), 6)  # 封顶 6 分

        return score

    @staticmethod
    def _parse_size_gb(size_text: str) -> float:
        """将文件大小文本解析为 GB 单位的浮点数"""
        if not size_text:
            return 0.0
        try:
            match = re.search(r'([\d.]+)\s*(GiB|MiB|KiB|TiB|GB|MB|KB|TB)', size_text, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                unit = match.group(2).upper()
                if unit in ("TIB", "TB"):
                    return value * 1024
                elif unit in ("GIB", "GB"):
                    return value
                elif unit in ("MIB", "MB"):
                    return value / 1024
                elif unit in ("KIB", "KB"):
                    return value / (1024 * 1024)
        except Exception:
            pass
        return 0.0

    def search_best_magnet(self, keyword: str) -> str | None:
        """
        高层级便捷方法：搜索 -> 评分 -> 返回最优磁力链接

        Args:
            keyword: 搜索关键字（如 "SSIS-001"）

        Returns:
            最优磁力链接字符串，或 None
        """
        results = self.search_keyword(keyword)
        if not results:
            return None

        # 按评分排序
        scored = [(self.score_result(r, keyword), r) for r in results]
        scored.sort(key=lambda x: x[0], reverse=True)

        # 取最高分的磁力
        best_score, best_result = scored[0]
        print(f"  🏆 最优 [{best_score}分] {best_result['title'][:60]}... "
              f"({best_result['size']}, {best_result['seeders']} seeds)")

        magnet = best_result.get("magnet")
        if magnet:
            print(f"  🧲 磁力: {magnet[:60]}...")
            return magnet

        print(f"  😞 最优结果无有效磁力链接")
        return None
