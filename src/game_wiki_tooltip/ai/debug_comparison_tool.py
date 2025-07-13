"""
RAG系统调试比较工具
==================

用于比较app.py和run_quality_evaluation.py中RAG系统的详细执行流程，
帮助识别两者之间的差异。
"""

import json
import re
import sys
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging
from io import StringIO

logger = logging.getLogger(__name__)


@dataclass
class DebugStep:
    """单个调试步骤"""
    step_type: str  # VECTOR, BM25, HYBRID, FUSION, INTENT, QUERY, SUMMARY
    step_name: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class RAGExecutionTrace:
    """RAG执行轨迹"""
    system_name: str
    query: str
    steps: List[DebugStep] = field(default_factory=list)
    final_result: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    

class DebugOutputCapture:
    """调试输出捕获器"""
    
    def __init__(self):
        self.captured_output = StringIO()
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
    def __enter__(self):
        sys.stdout = self.captured_output
        sys.stderr = self.captured_output
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
    def get_output(self) -> str:
        return self.captured_output.getvalue()


class DebugLogParser:
    """调试日志解析器"""
    
    DEBUG_PATTERNS = {
        'VECTOR': r'🔍 \[VECTOR-DEBUG\] (.+)',
        'BM25': r'🔍 \[BM25-DEBUG\] (.+)',
        'HYBRID': r'🔍 \[HYBRID-DEBUG\] (.+)',
        'FUSION': r'🔄 \[FUSION-DEBUG\] (.+)',
        'INTENT': r'🎯 \[INTENT-DEBUG\] (.+)',
        'RERANK': r'🔄 \[RERANK-DEBUG\] (.+)',
        'QUERY': r'🔄 \[QUERY-DEBUG\] (.+)',
        'SUMMARY': r'📝 \[SUMMARY-DEBUG\] (.+)',
        'RAG': r'🔍 \[RAG-DEBUG\] (.+)',
        'EVALUATOR': r'🧪 \[EVALUATOR-DEBUG\] (.+)',
        'SEARCHBAR': r'🎯 \[SEARCHBAR-DEBUG\] (.+)'
    }
    
    def parse_debug_output(self, output: str) -> List[DebugStep]:
        """解析调试输出并提取步骤"""
        steps = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 匹配调试模式
            for step_type, pattern in self.DEBUG_PATTERNS.items():
                match = re.match(pattern, line)
                if match:
                    step_name = match.group(1)
                    details = self._extract_details(line, step_type)
                    
                    step = DebugStep(
                        step_type=step_type,
                        step_name=step_name,
                        details=details
                    )
                    steps.append(step)
                    break
        
        return steps
    
    def _extract_details(self, line: str, step_type: str) -> Dict[str, Any]:
        """从调试行中提取详细信息"""
        details = {}
        
        # 提取常见的数值信息
        score_match = re.search(r'分数[：:]?\s*(\d+\.?\d*)', line)
        if score_match:
            details['score'] = float(score_match.group(1))
            
        count_match = re.search(r'数量[：:]?\s*(\d+)', line)
        if count_match:
            details['count'] = int(count_match.group(1))
            
        time_match = re.search(r'时间[：:]?\s*(\d+\.?\d*)', line)
        if time_match:
            details['time'] = float(time_match.group(1))
            
        # 提取查询信息
        query_match = re.search(r"query[=：]\s*['\"]([^'\"]+)['\"]", line)
        if query_match:
            details['query'] = query_match.group(1)
            
        # 提取主题信息
        topic_match = re.search(r"主题[：:]?\s*([^，\s]+)", line)
        if topic_match:
            details['topic'] = topic_match.group(1)
            
        # 提取意图信息
        intent_match = re.search(r"意图[：:]?\s*(\w+)", line)
        if intent_match:
            details['intent'] = intent_match.group(1)
            
        # 提取置信度信息
        confidence_match = re.search(r"置信度[：:]?\s*(\d+\.?\d*)", line)
        if confidence_match:
            details['confidence'] = float(confidence_match.group(1))
            
        return details


class RAGComparator:
    """RAG系统比较器"""
    
    def __init__(self):
        self.parser = DebugLogParser()
        
    def compare_traces(self, trace1: RAGExecutionTrace, trace2: RAGExecutionTrace) -> Dict[str, Any]:
        """比较两个执行轨迹"""
        comparison = {
            'query': trace1.query,
            'system1': trace1.system_name,
            'system2': trace2.system_name,
            'execution_time_diff': trace2.execution_time - trace1.execution_time,
            'steps_comparison': self._compare_steps(trace1.steps, trace2.steps),
            'results_comparison': self._compare_results(trace1.final_result, trace2.final_result),
            'differences': self._find_differences(trace1, trace2)
        }
        
        return comparison
    
    def _compare_steps(self, steps1: List[DebugStep], steps2: List[DebugStep]) -> Dict[str, Any]:
        """比较执行步骤"""
        steps_by_type1 = self._group_steps_by_type(steps1)
        steps_by_type2 = self._group_steps_by_type(steps2)
        
        comparison = {}
        
        # 找出所有步骤类型
        all_types = set(steps_by_type1.keys()) | set(steps_by_type2.keys())
        
        for step_type in all_types:
            type_steps1 = steps_by_type1.get(step_type, [])
            type_steps2 = steps_by_type2.get(step_type, [])
            
            comparison[step_type] = {
                'system1_count': len(type_steps1),
                'system2_count': len(type_steps2),
                'system1_details': [step.details for step in type_steps1],
                'system2_details': [step.details for step in type_steps2],
                'differences': self._compare_step_details(type_steps1, type_steps2)
            }
        
        return comparison
    
    def _group_steps_by_type(self, steps: List[DebugStep]) -> Dict[str, List[DebugStep]]:
        """按类型分组步骤"""
        grouped = {}
        for step in steps:
            if step.step_type not in grouped:
                grouped[step.step_type] = []
            grouped[step.step_type].append(step)
        return grouped
    
    def _compare_step_details(self, steps1: List[DebugStep], steps2: List[DebugStep]) -> List[str]:
        """比较步骤详细信息"""
        differences = []
        
        # 比较数量
        if len(steps1) != len(steps2):
            differences.append(f"步骤数量不同: {len(steps1)} vs {len(steps2)}")
        
        # 比较详细信息
        for i in range(min(len(steps1), len(steps2))):
            step1 = steps1[i]
            step2 = steps2[i]
            
            # 比较分数
            if 'score' in step1.details and 'score' in step2.details:
                score_diff = abs(step1.details['score'] - step2.details['score'])
                if score_diff > 0.001:  # 阈值
                    differences.append(f"分数差异: {step1.details['score']:.4f} vs {step2.details['score']:.4f}")
            
            # 比较其他关键字段
            for key in ['count', 'time', 'intent', 'confidence']:
                if key in step1.details and key in step2.details:
                    if step1.details[key] != step2.details[key]:
                        differences.append(f"{key}差异: {step1.details[key]} vs {step2.details[key]}")
        
        return differences
    
    def _compare_results(self, result1: Dict[str, Any], result2: Dict[str, Any]) -> Dict[str, Any]:
        """比较最终结果"""
        comparison = {
            'answer_length_diff': len(str(result1.get('answer', ''))) - len(str(result2.get('answer', ''))),
            'confidence_diff': result1.get('confidence', 0) - result2.get('confidence', 0),
            'results_count_diff': result1.get('results_count', 0) - result2.get('results_count', 0),
            'query_time_diff': result1.get('query_time', 0) - result2.get('query_time', 0)
        }
        
        return comparison
    
    def _find_differences(self, trace1: RAGExecutionTrace, trace2: RAGExecutionTrace) -> List[str]:
        """找出关键差异"""
        differences = []
        
        # 执行时间差异
        time_diff = abs(trace2.execution_time - trace1.execution_time)
        if time_diff > 0.1:  # 100ms阈值
            differences.append(f"执行时间差异显著: {time_diff:.3f}秒")
        
        # 步骤数量差异
        steps_diff = abs(len(trace2.steps) - len(trace1.steps))
        if steps_diff > 0:
            differences.append(f"执行步骤数量不同: {len(trace1.steps)} vs {len(trace2.steps)}")
        
        # 最终结果差异
        result1 = trace1.final_result
        result2 = trace2.final_result
        
        if result1.get('confidence', 0) != result2.get('confidence', 0):
            differences.append(f"最终置信度不同: {result1.get('confidence', 0)} vs {result2.get('confidence', 0)}")
        
        if result1.get('results_count', 0) != result2.get('results_count', 0):
            differences.append(f"结果数量不同: {result1.get('results_count', 0)} vs {result2.get('results_count', 0)}")
        
        return differences
    
    def generate_report(self, comparison: Dict[str, Any]) -> str:
        """生成比较报告"""
        report = f"""
# RAG系统比较报告

**查询**: {comparison['query']}
**系统1**: {comparison['system1']}
**系统2**: {comparison['system2']}
**执行时间差异**: {comparison['execution_time_diff']:.3f}秒

## 主要差异

"""
        
        # 添加关键差异
        if comparison['differences']:
            for diff in comparison['differences']:
                report += f"- {diff}\n"
        else:
            report += "- 没有发现显著差异\n"
        
        report += "\n## 步骤比较\n\n"
        
        # 添加步骤比较
        for step_type, step_comp in comparison['steps_comparison'].items():
            report += f"### {step_type}\n\n"
            report += f"- {comparison['system1']}: {step_comp['system1_count']} 个步骤\n"
            report += f"- {comparison['system2']}: {step_comp['system2_count']} 个步骤\n"
            
            if step_comp['differences']:
                report += "- 差异:\n"
                for diff in step_comp['differences']:
                    report += f"  - {diff}\n"
            
            report += "\n"
        
        report += "\n## 结果比较\n\n"
        
        # 添加结果比较
        results_comp = comparison['results_comparison']
        report += f"- 答案长度差异: {results_comp['answer_length_diff']} 字符\n"
        report += f"- 置信度差异: {results_comp['confidence_diff']:.3f}\n"
        report += f"- 结果数量差异: {results_comp['results_count_diff']}\n"
        report += f"- 查询时间差异: {results_comp['query_time_diff']:.3f}秒\n"
        
        return report


def create_debug_comparison_tool():
    """创建调试比较工具实例"""
    return RAGComparator()


def run_comparison_analysis(query: str, output_file: Optional[str] = None):
    """运行比较分析"""
    print(f"🔍 开始RAG系统比较分析")
    print(f"查询: '{query}'")
    
    comparator = RAGComparator()
    
    # 这里需要实际运行两个系统并捕获输出
    # 由于篇幅限制，这里只是示例框架
    
    print(f"📊 分析完成")
    
    if output_file:
        print(f"📄 报告已保存至: {output_file}")


if __name__ == "__main__":
    # 示例用法
    query = "bile titan弱点"
    run_comparison_analysis(query) 