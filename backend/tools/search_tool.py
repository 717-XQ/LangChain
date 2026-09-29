# -*- coding: utf-8 -*-
"""
search_tool.py - 联网搜索工具
=============================================
功能：搜索互联网实时信息，返回Top5结果摘要
支持三种搜索引擎（自动降级）：
  1. ddgs（DuckDuckGo新版，免费无需Key）
  2. 百度搜索（国内稳定，无需Key）
  3. SerpAPI（需要Key，结果最稳定）
"""

import re
import html
from typing import List, Dict, Any
from loguru import logger

from langchain_core.tools import Tool


# ============================================================
# 搜索引擎实现
# ============================================================

def _search_ddgs(query: str, num_results: int = 5) -> str:
    """
    使用ddgs（DuckDuckGo新版）搜索

    Args:
        query: 搜索关键词
        num_results: 返回结果数

    Returns:
        str: 格式化的搜索结果
    """
    try:
        from ddgs import DDGS

        results = []
        with DDGS(timeout=8) as ddgs:
            for r in ddgs.text(query, max_results=num_results, region="cn-zh"):
                results.append({
                    "title": r.get("title", "无标题"),
                    "body": r.get("body", "无摘要"),
                    "href": r.get("href", "无链接"),
                })

        if not results:
            return ""  # 返回空字符串表示失败，触发降级

        return _format_results(query, results)

    except ImportError:
        logger.warning("ddgs包未安装")
        return ""
    except Exception as e:
        logger.warning(f"ddgs搜索失败: {e}")
        return ""


def _search_baidu(query: str, num_results: int = 5) -> str:
    """
    使用百度搜索（国内稳定，无需Key）

    通过requests抓取百度搜索结果页面，解析标题和摘要。

    Args:
        query: 搜索关键词
        num_results: 返回结果数

    Returns:
        str: 格式化的搜索结果
    """
    try:
        import requests

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        url = "https://www.baidu.com/s"
        params = {"wd": query, "rn": num_results}

        resp = requests.get(url, params=params, headers=headers, timeout=8)
        resp.encoding = "utf-8"

        # 解析搜索结果
        results = []
        # 百度搜索结果在 <div class="result c-container ..."> 中
        # 使用正则提取标题和摘要
        result_blocks = re.findall(
            r'<h3[^>]*class="[^"]*t[^"]*"[^>]*>(.*?)</h3>.*?<span[^>]*class="[^"]*content-right[^"]*"[^>]*>(.*?)</span>',
            resp.text,
            re.DOTALL,
        )

        if not result_blocks:
            # 备用解析方式
            result_blocks = re.findall(
                r'<h3[^>]*>(.*?)</h3>.*?<div[^>]*class="[^"]*c-abstract[^"]*"[^>]*>(.*?)</div>',
                resp.text,
                re.DOTALL,
            )

        for title_html, abstract_html in result_blocks[:num_results]:
            # 提取标题中的链接和文本
            link_match = re.search(r'href="([^"]+)"', title_html)
            title_text = re.sub(r"<[^>]+>", "", title_html).strip()
            abstract_text = re.sub(r"<[^>]+>", "", abstract_html).strip()
            link = link_match.group(1) if link_match else "无链接"

            # HTML实体解码
            title_text = html.unescape(title_text)
            abstract_text = html.unescape(abstract_text)

            if title_text:
                results.append({
                    "title": title_text,
                    "body": abstract_text[:200],
                    "href": link,
                })

        if not results:
            return ""

        return _format_results(query, results)

    except ImportError:
        logger.warning("requests包未安装")
        return ""
    except Exception as e:
        logger.warning(f"百度搜索失败: {e}")
        return ""


def _search_serpapi(query: str, api_key: str, num_results: int = 5) -> str:
    """
    使用SerpAPI搜索（需要API Key）

    Args:
        query: 搜索关键词
        api_key: SerpAPI Key
        num_results: 返回结果数

    Returns:
        str: 格式化的搜索结果
    """
    try:
        import requests

        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": api_key,
            "num": num_results,
            "hl": "zh-cn",
        }

        resp = requests.get(url, params=params, timeout=15)
        data = resp.json()

        organic_results = data.get("organic_results", [])
        results = []
        for r in organic_results[:num_results]:
            results.append({
                "title": r.get("title", "无标题"),
                "body": r.get("snippet", "无摘要"),
                "href": r.get("link", "无链接"),
            })

        if not results:
            return ""

        return _format_results(query, results)

    except Exception as e:
        logger.warning(f"SerpAPI搜索失败: {e}")
        return ""


def _filter_results(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    过滤搜索结果，移除明显不相关的结果（百科、旅游、地图等）

    Args:
        results: 原始搜索结果
        query: 搜索关键词（用于判断相关性）

    Returns:
        List[Dict]: 过滤后的结果
    """
    # 不相关域名黑名单
    irrelevant_domains = [
        "baike.baidu.com",      # 百度百科
        "map.baidu.com",        # 百度地图
        "baike.sogou.com",      # 搜狗百科
        "kkday.com",            # 旅游网站
        "mafengwo.cn",          # 马蜂窝旅游
        "ctrip.com",            # 携程旅游
        "qunar.com",            # 去哪儿旅游
        "trip.com",             # 旅游网站
    ]

    # 不相关关键词（出现在标题或摘要中时过滤）
    irrelevant_keywords = [
        "旅游攻略", "必去景点", "自由行", "打卡清单",
        "百度百科", "搜狗百科",
    ]

    filtered = []
    for r in results:
        href = r.get("href", "").lower()
        title = r.get("title", "")
        body = r.get("body", "")

        # 检查域名黑名单
        skip = False
        for domain in irrelevant_domains:
            if domain in href:
                skip = True
                break

        # 检查关键词黑名单
        if not skip:
            for kw in irrelevant_keywords:
                if kw in title or kw in body:
                    skip = True
                    break

        if not skip:
            filtered.append(r)

    # 如果过滤后结果太少（<2条），保留原始结果（避免完全没结果）
    if len(filtered) < 2:
        return results[:5]

    return filtered


def _format_results(query: str, results: List[Dict[str, Any]]) -> str:
    """格式化搜索结果（先过滤再格式化）"""
    # 过滤不相关结果
    filtered = _filter_results(results, query)

    if not filtered:
        return ""

    parts = [f"搜索关键词: {query}\n"]
    for i, r in enumerate(filtered, 1):
        parts.append(f"[{i}] {r['title']}")
        parts.append(f"    摘要: {r['body']}")
        parts.append(f"    链接: {r['href']}")
        parts.append("")
    return "\n".join(parts)


# ============================================================
# 主搜索函数（自动降级）
# ============================================================

def search(query: str) -> str:
    """
    联网搜索工具主函数（自动降级：ddgs → 百度 → SerpAPI）

    Args:
        query: 搜索关键词

    Returns:
        str: 搜索结果摘要
    """
    from config import get_config

    config = get_config()
    search_config = config.tools.search
    num_results = search_config.num_results

    logger.info(f"联网搜索: {query}")

    # 1. 优先使用ddgs（DuckDuckGo）
    result = _search_ddgs(query, num_results)
    if result:
        logger.info("ddgs搜索成功")
        return result

    # 2. 降级到百度搜索（国内稳定）
    logger.info("ddgs搜索失败，降级到百度搜索")
    result = _search_baidu(query, num_results)
    if result:
        logger.info("百度搜索成功")
        return result

    # 3. 如果配置了SerpAPI，最后尝试
    if search_config.provider == "serpapi" and search_config.serpapi_key:
        logger.info("百度搜索失败，尝试SerpAPI")
        result = _search_serpapi(query, search_config.serpapi_key, num_results)
        if result:
            return result

    # 全部失败
    error_msg = (
        f"联网搜索暂时不可用（已尝试DuckDuckGo和百度搜索）。\n"
        f"可能原因：网络连接问题或搜索服务暂时不可用。\n"
        f"建议：稍后重试，或在config.yaml中配置SerpAPI Key以获得更稳定的搜索服务。"
    )
    logger.error("所有搜索引擎均失败")
    return error_msg


def get_search_tool() -> Tool:
    """获取搜索工具实例"""
    return Tool(
        name="Search",
        func=search,
        description="联网搜索互联网获取实时信息。输入搜索关键词字符串，"
                    "返回相关网页的标题、摘要和链接。"
                    "适用场景：新闻、天气、股价、最新事件、事实查询等需要实时信息的问题。"
                    "示例输入：'2026年诺贝尔物理学奖'、'今日成都天气'"
    )


# 模块测试
if __name__ == "__main__":
    print(search("Python是什么"))
