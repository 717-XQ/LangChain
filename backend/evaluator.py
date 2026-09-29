# -*- coding: utf-8 -*-
"""
evaluator.py - Agent评估模块
=============================================
功能：
  - 在30条多步任务测试集上评估Agent
  - 统计任务完成率、工具调用准确率、平均轮次
  - 失败案例分类分析
  - 输出评估报告（JSON + 文本）
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from loguru import logger

from tqdm import tqdm


class AgentEvaluator:
    """
    Agent评估器

    在测试集上运行Agent，自动评估：
    1. 任务完成率：回答是否包含期望关键词
    2. 工具调用准确率：是否调用了期望的工具
    3. 平均轮次：完成任务平均工具调用次数
    4. 失败案例分析
    """

    def __init__(self, agent_manager, test_data_path: str = "tests/eval_tasks.json"):
        """
        Args:
            agent_manager: Agent管理器
            test_data_path: 测试集路径
        """
        self.manager = agent_manager
        self.test_data_path = Path(test_data_path)
        self.results = []

    def load_test_data(self) -> List[Dict[str, Any]]:
        """加载测试集"""
        with open(self.test_data_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def evaluate_single(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估单条任务

        Args:
            task: 测试任务

        Returns:
            Dict: 评估结果
        """
        task_id = task["id"]
        question = task["task"]
        expected_tools = task.get("expected_tools", [])
        expected_keywords = task.get("expected_keywords", [])

        logger.info(f"评估任务 {task_id}: {question[:50]}")

        start_time = time.time()
        try:
            result = self.manager.run_agent(
                query=question,
                session_id=f"eval_{task_id}",
                agent_type="react",
            )
            answer = result.get("answer", "")
            tool_calls = result.get("tool_calls", [])
            error = result.get("error")
        except Exception as e:
            answer = ""
            tool_calls = []
            error = str(e)

        duration = time.time() - start_time

        # 评估1：关键词匹配（任务是否完成）
        answer_lower = answer.lower()
        keywords_found = [
            kw for kw in expected_keywords
            if str(kw).lower() in answer_lower
        ]
        task_completed = len(keywords_found) > 0 if expected_keywords else True

        # 评估2：工具调用准确率
        called_tools = [tc.get("tool", "") for tc in tool_calls]
        tools_correct = all(
            any(et in ct for ct in called_tools)
            for et in expected_tools
        ) if expected_tools else True

        # 评估3：工具调用次数
        num_tool_calls = len(tool_calls)

        # 失败原因分类
        failure_reason = None
        if not task_completed:
            if error:
                failure_reason = "execution_error"
            elif not called_tools and expected_tools:
                failure_reason = "no_tool_called"
            elif not tools_correct:
                failure_reason = "wrong_tool"
            elif not keywords_found:
                failure_reason = "wrong_answer"
            else:
                failure_reason = "unknown"

        return {
            "id": task_id,
            "task": question,
            "category": task.get("category", "unknown"),
            "difficulty": task.get("difficulty", "unknown"),
            "answer": answer[:1000],
            "expected_tools": expected_tools,
            "called_tools": called_tools,
            "expected_keywords": expected_keywords,
            "keywords_found": keywords_found,
            "task_completed": task_completed,
            "tools_correct": tools_correct,
            "num_tool_calls": num_tool_calls,
            "duration": round(duration, 2),
            "error": error,
            "failure_reason": failure_reason,
        }

    def run_evaluation(self, output_dir: str = "eval_results") -> Dict[str, Any]:
        """
        运行完整评估

        Args:
            output_dir: 结果输出目录

        Returns:
            Dict: 评估报告
        """
        logger.info("=" * 60)
        logger.info("开始Agent评估")
        logger.info("=" * 60)

        test_data = self.load_test_data()
        logger.info(f"加载 {len(test_data)} 条测试任务")

        # 逐条评估
        for task in tqdm(test_data, desc="评估进度"):
            result = self.evaluate_single(task)
            self.results.append(result)

        # 生成报告
        report = self._generate_report()

        # 保存结果
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # JSON结果
        with open(output_path / "eval_results.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 文本报告
        with open(output_path / "eval_report.txt", "w", encoding="utf-8") as f:
            f.write(self._format_report(report))

        logger.info(f"评估完成！结果已保存到 {output_path}")
        print(self._format_report(report))

        return report

    def _generate_report(self) -> Dict[str, Any]:
        """生成评估报告"""
        total = len(self.results)
        completed = sum(1 for r in self.results if r["task_completed"])
        tools_correct = sum(1 for r in self.results if r["tools_correct"])
        avg_tool_calls = (
            sum(r["num_tool_calls"] for r in self.results) / total
            if total > 0 else 0
        )
        avg_duration = (
            sum(r["duration"] for r in self.results) / total
            if total > 0 else 0
        )

        # 按类别统计
        category_stats = {}
        for r in self.results:
            cat = r["category"]
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "completed": 0}
            category_stats[cat]["total"] += 1
            if r["task_completed"]:
                category_stats[cat]["completed"] += 1

        # 按难度统计
        difficulty_stats = {}
        for r in self.results:
            diff = r["difficulty"]
            if diff not in difficulty_stats:
                difficulty_stats[diff] = {"total": 0, "completed": 0}
            difficulty_stats[diff]["total"] += 1
            if r["task_completed"]:
                difficulty_stats[diff]["completed"] += 1

        # 失败案例
        failures = [
            {
                "id": r["id"],
                "task": r["task"],
                "reason": r["failure_reason"],
                "called_tools": r["called_tools"],
                "expected_tools": r["expected_tools"],
            }
            for r in self.results if not r["task_completed"]
        ]

        # 失败原因统计
        failure_reasons = {}
        for f in failures:
            reason = f["reason"] or "unknown"
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

        return {
            "summary": {
                "total_tasks": total,
                "completed": completed,
                "completion_rate": round(completed / total * 100, 1) if total else 0,
                "tools_accuracy": round(tools_correct / total * 100, 1) if total else 0,
                "avg_tool_calls": round(avg_tool_calls, 1),
                "avg_duration": round(avg_duration, 1),
            },
            "category_stats": category_stats,
            "difficulty_stats": difficulty_stats,
            "failure_reasons": failure_reasons,
            "failures": failures,
            "results": self.results,
            "timestamp": datetime.now().isoformat(),
        }

    def _format_report(self, report: Dict) -> str:
        """格式化文本报告"""
        s = report["summary"]
        lines = [
            "=" * 60,
            "Agent评估报告",
            f"时间: {report['timestamp']}",
            "=" * 60,
            "",
            "--- 总体指标 ---",
            f"总任务数:       {s['total_tasks']}",
            f"完成数:         {s['completed']}",
            f"完成率:         {s['completion_rate']}%",
            f"工具准确率:     {s['tools_accuracy']}%",
            f"平均工具调用:   {s['avg_tool_calls']} 次",
            f"平均耗时:       {s['avg_duration']} 秒",
            "",
            "--- 按类别统计 ---",
        ]

        for cat, stats in report["category_stats"].items():
            rate = round(stats["completed"] / stats["total"] * 100, 1)
            lines.append(f"  {cat}: {stats['completed']}/{stats['total']} ({rate}%)")

        lines.append("")
        lines.append("--- 按难度统计 ---")
        for diff, stats in report["difficulty_stats"].items():
            rate = round(stats["completed"] / stats["total"] * 100, 1)
            lines.append(f"  {diff}: {stats['completed']}/{stats['total']} ({rate}%)")

        lines.append("")
        lines.append("--- 失败原因分布 ---")
        for reason, count in report["failure_reasons"].items():
            lines.append(f"  {reason}: {count}")

        if report["failures"]:
            lines.append("")
            lines.append("--- 失败案例 ---")
            for f in report["failures"]:
                lines.append(f"  [#{f['id']}] {f['task'][:60]}")
                lines.append(f"    原因: {f['reason']}, 调用工具: {f['called_tools']}")

        lines.append("")
        lines.append("--- 优化建议 ---")
        if s["completion_rate"] < 80:
            lines.append("  - 任务完成率低于80%，建议优化Prompt和工具描述")
        if report["failure_reasons"].get("wrong_tool"):
            lines.append("  - 存在工具选择错误，建议优化工具description")
        if report["failure_reasons"].get("wrong_answer"):
            lines.append("  - 存在回答内容错误，建议增加few-shot示例")
        if report["failure_reasons"].get("execution_error"):
            lines.append("  - 存在执行错误，建议增强异常处理")

        lines.append("=" * 60)
        return "\n".join(lines)


if __name__ == "__main__":
    from agent_manager import AgentManager
    manager = AgentManager()
    evaluator = AgentEvaluator(manager)
    evaluator.run_evaluation()
