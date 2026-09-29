# -*- coding: utf-8 -*-
"""
weather_tool.py - 天气查询专用工具
=============================================
使用 wttr.in 免费天气API（无需API Key）查询实时天气和预报。
比通用搜索引擎更精准、更快，避免搜索返回无关结果。
"""

import requests
from typing import Optional
from loguru import logger

from langchain_core.tools import Tool


def get_weather(city: str, days: int = 3) -> str:
    """
    查询指定城市的天气信息

    Args:
        city: 城市名称（支持中文，如"成都"、"成都武侯区"）
        days: 预报天数（1-3天，默认3天）

    Returns:
        str: 格式化的天气信息
    """
    # 清理城市名，去掉多余空格
    city = city.strip()
    if not city:
        return "请提供城市名称"

    logger.info(f"查询天气: {city}, 预报{days}天")

    try:
        # wttr.in 免费API，返回JSON格式
        # format=j1 返回完整JSON，包含当前天气和3天预报
        url = f"https://wttr.in/{city}"
        params = {
            "format": "j1",
            "lang": "zh",
        }
        headers = {
            "User-Agent": "curl/8.0",  # wttr.in要求UA
            "Accept-Language": "zh-CN",
        }

        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # 解析当前天气
        current = data.get("current_condition", [{}])[0]
        temp_c = current.get("temp_C", "?")
        feels_like = current.get("FeelsLikeC", "?")
        humidity = current.get("humidity", "?")
        # 天气描述（中文）
        weather_desc = current.get("lang_zh", [{}])
        if isinstance(weather_desc, list) and weather_desc:
            weather_desc = weather_desc[0].get("value", "未知")
        else:
            weather_desc = current.get("weatherDesc", [{}])[0].get("value", "未知")
        wind_speed = current.get("windspeedKmph", "?")
        wind_dir = current.get("winddir16Point", "?")
        visibility = current.get("visibility", "?")
        uv_index = current.get("uvIndex", "?")

        # 解析位置信息
        nearest_area = data.get("nearest_area", [{}])[0]
        area_name = nearest_area.get("areaName", [{}])[0].get("value", city)
        country = nearest_area.get("country", [{}])[0].get("value", "")

        # 解析未来预报
        forecasts = data.get("weather", [])

        parts = [f"📍 {area_name}（{country}）天气\n"]
        parts.append("【当前天气】")
        parts.append(f"  天气: {weather_desc}")
        parts.append(f"  温度: {temp_c}°C（体感 {feels_like}°C）")
        parts.append(f"  湿度: {humidity}%")
        parts.append(f"  风速: {wind_speed} km/h（{wind_dir}）")
        parts.append(f"  能见度: {visibility} km")
        parts.append(f"  UV指数: {uv_index}")

        if forecasts:
            parts.append(f"\n【未来{min(days, len(forecasts))}天预报】")
            for i, day in enumerate(forecasts[:days]):
                date = day.get("date", "?")
                max_temp = day.get("maxtempC", "?")
                min_temp = day.get("mintempC", "?")
                # 取中午时段的天气描述
                hourly = day.get("hourly", [])
                day_desc = "未知"
                if hourly:
                    # 找12:00的时段
                    noon = [h for h in hourly if h.get("time") == "1200"]
                    if noon:
                        desc_list = noon[0].get("lang_zh", [])
                        if isinstance(desc_list, list) and desc_list:
                            day_desc = desc_list[0].get("value", "未知")
                        else:
                            day_desc = noon[0].get("weatherDesc", [{}])[0].get("value", "未知")
                    else:
                        desc_list = hourly[0].get("lang_zh", [])
                        if isinstance(desc_list, list) and desc_list:
                            day_desc = desc_list[0].get("value", "未知")
                # 降雨概率
                rain_chance = "?"
                if hourly:
                    noon = [h for h in hourly if h.get("time") == "1200"]
                    if noon:
                        rain_chance = noon[0].get("chanceofrain", "?")

                day_label = "今天" if i == 0 else ("明天" if i == 1 else f"第{i+1}天")
                parts.append(f"  {day_label}({date}): {day_desc}, {min_temp}~{max_temp}°C, 降雨概率{rain_chance}%")

        return "\n".join(parts)

    except requests.exceptions.Timeout:
        return f"天气查询超时，请稍后重试。您也可以直接访问 https://wttr.in/{city} 查看。"
    except requests.exceptions.RequestException as e:
        logger.error(f"天气查询失败: {e}")
        return f"天气查询失败: {str(e)[:100]}。请检查城市名称是否正确，或稍后重试。"
    except Exception as e:
        logger.error(f"天气查询解析失败: {e}")
        return f"天气数据解析失败: {str(e)[:100]}"


def get_weather_tool() -> Tool:
    """获取天气查询工具实例"""
    return Tool(
        name="Weather",
        func=get_weather,
        description="查询指定城市的实时天气和未来3天预报。输入城市名称字符串，"
                    "如'成都'、'北京'、'上海浦东'。返回温度、湿度、风速、天气状况和预报。"
                    "当用户询问天气、气温、降雨、穿衣建议等天气相关问题时使用此工具。"
                    "注意：此工具比通用搜索更精准快速，天气问题优先使用此工具而非Search。"
    )


# 模块测试
if __name__ == "__main__":
    print(get_weather("成都"))
