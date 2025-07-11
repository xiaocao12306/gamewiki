"""
RAG输出质量评估器
=====================

用于评估RAG系统的输出质量，通过对比实际输出和期望答案，
使用LLM进行质量评分和问题分析。
"""

import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

import google.generativeai as genai

try:
    # 尝试相对导入（包内运行）
    from .rag_query import EnhancedRagQuery
    from .unified_query_processor import UnifiedQueryProcessor
    from .hybrid_retriever import HybridSearchRetriever
    from .gemini_summarizer import create_gemini_summarizer
    from ..config import LLMConfig
except ImportError:
    # 相对导入失败，使用绝对导入（直接运行脚本）
    import sys
    from pathlib import Path
    
    # 添加项目根目录到Python路径
    project_root = Path(__file__).parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    from src.game_wiki_tooltip.ai.rag_query import EnhancedRagQuery
    from src.game_wiki_tooltip.ai.unified_query_processor import UnifiedQueryProcessor
    from src.game_wiki_tooltip.ai.hybrid_retriever import HybridSearchRetriever
    from src.game_wiki_tooltip.ai.gemini_summarizer import create_gemini_summarizer
    from src.game_wiki_tooltip.config import LLMConfig

logger = logging.getLogger(__name__)

@dataclass
class EvaluationResult:
    """单个测试用例的评估结果"""
    query: str
    expected_answer: str
    generated_answer: str
    scores: Dict[str, float]  # 各维度得分
    overall_score: float
    evaluation_reasoning: str
    issues: List[str]
    suggestions: List[str]
    rag_metadata: Dict[str, Any]  # RAG查询的元数据
    processing_time: float

@dataclass
class QualityReport:
    """整体质量报告"""
    total_cases: int
    average_score: float
    scores_by_dimension: Dict[str, float]
    common_issues: List[str]
    improvement_suggestions: List[str]
    detailed_results: List[EvaluationResult]
    metadata: Dict[str, Any]
    generated_at: str

class RAGQualityEvaluator:
    """RAG输出质量评估器"""
    
    EVALUATION_DIMENSIONS = {
        "accuracy": "答案的准确性和事实正确性",
        "completeness": "答案是否涵盖了所有要点",
        "relevance": "答案与问题的相关性",
        "practicality": "答案对玩家的实用性",
        "clarity": "答案的清晰度和可读性"
    }
    
    def __init__(self, game: str = "helldiver2", llm_config: Optional[LLMConfig] = None):
        self.game = game
        self.llm_config = llm_config or LLMConfig()
        
        # RAG组件
        self.rag_engine = None
        self.evaluator_llm = None
        
        # 测试数据路径
        self.test_data_path = Path(__file__).parent.parent.parent.parent / "data" / "sample_inoutput" / f"{game}.json"
        
        # 向量库元数据路径
        self.metadata_path = Path(__file__).parent / "vectorstore" / f"{game}_vectors" / "metadata.json"
        
        # 结果存储
        self.evaluation_results = []
        
    async def initialize(self):
        """初始化RAG引擎和评估LLM"""
        try:
            # 初始化RAG引擎（启用混合搜索和增强功能）
            self.rag_engine = EnhancedRagQuery(
                enable_summarization=True,
                enable_hybrid_search=True,   # 启用混合搜索
                enable_intent_reranking=True,  # 启用意图重排序
                llm_config=self.llm_config,
                hybrid_config={
                    "fusion_method": "rrf",
                    "vector_weight": 0.5,
                    "bm25_weight": 0.5,
                    "rrf_k": 60
                }
            )
            await self.rag_engine.initialize(game_name=self.game)
            logger.info(f"RAG引擎初始化成功: {self.game}")
            
            # 初始化评估LLM (Gemini-2.5-pro)
            api_key = self.llm_config.get_api_key()
            if not api_key:
                raise ValueError("未找到Gemini API密钥")
                
            genai.configure(api_key=api_key)
            
            # 使用gemini-2.0-flash-exp进行评估
            self.evaluator_llm = genai.GenerativeModel(
                model_name="gemini-2.0-flash-exp",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=2048,
                    temperature=0.1,  # 低温度以确保评估一致性
                )
            )
            logger.info("评估LLM初始化成功")
            
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            raise
    
    def load_test_data(self) -> List[Dict[str, str]]:
        """加载测试数据"""
        if not self.test_data_path.exists():
            raise FileNotFoundError(f"测试数据文件不存在: {self.test_data_path}")
            
        with open(self.test_data_path, 'r', encoding='utf-8') as f:
            test_data = json.load(f)
            
        logger.info(f"加载了 {len(test_data)} 个测试用例")
        return test_data
    
    async def run_rag_query(self, query: str) -> Dict[str, Any]:
        """运行RAG查询并返回结果及元数据"""
        print(f"🧪 [EVALUATOR-DEBUG] 运行RAG查询: '{query}'")
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 执行RAG查询
            print(f"🔍 [EVALUATOR-DEBUG] 调用rag_engine.query")
            result = await self.rag_engine.query(query)
            
            # 计算处理时间
            processing_time = asyncio.get_event_loop().time() - start_time
            
            # 添加处理时间到结果
            result['processing_time'] = processing_time
            
            print(f"📊 [EVALUATOR-DEBUG] RAG查询结果: 置信度={result.get('confidence', 0):.3f}, 结果数={result.get('results_count', 0)}")
            print(f"⏱️ [EVALUATOR-DEBUG] 查询耗时: {processing_time:.3f}秒")
            
            return result
            
        except Exception as e:
            print(f"❌ [EVALUATOR-DEBUG] RAG查询失败: {e}")
            logger.error(f"RAG查询失败: {e}")
            return {
                "answer": f"查询失败: {str(e)}",
                "sources": [],
                "confidence": 0.0,
                "processing_time": asyncio.get_event_loop().time() - start_time,
                "error": str(e)
            }
    
    async def evaluate_answer(self, query: str, expected: str, generated: str, rag_metadata: Dict[str, Any]) -> EvaluationResult:
        """使用LLM评估单个答案的质量"""
        
        # 构建评估提示
        evaluation_prompt = f"""
你是一个游戏攻略质量评估专家。请评估以下RAG系统生成的答案质量。

【用户问题】
{query}

【期望答案】
{expected}

【系统生成的答案】
{generated}

【RAG检索信息】
- 检索到的文档数: {rag_metadata.get('results_count', 0)}
- 置信度: {rag_metadata.get('confidence', 0):.2f}
- 使用的检索类型: {rag_metadata.get('search_metadata', {}).get('search_type', 'unknown')}
- 重写后的查询: {rag_metadata.get('search_metadata', {}).get('query', {}).get('rewritten', query)}

请从以下维度评估答案质量（每个维度0-10分）：
1. 准确性(accuracy): 答案的事实正确性，与期望答案的一致性
2. 完整性(completeness): 是否涵盖了期望答案中的所有要点
3. 相关性(relevance): 答案是否直接回答了用户的问题
4. 实用性(practicality): 答案对游戏玩家的实际帮助程度
5. 清晰度(clarity): 答案的表达是否清晰易懂

特别注意：
- 对于推荐类问题（如"最佳战纽推荐"），重点评估推荐的合理性而非与期望答案的完全一致
- 如果生成答案提供了与期望答案不同但同样有效的建议，应给予积极评价
- 考虑答案是否提供了额外的有用信息

请严格按照以下JSON格式输出评估结果：
{{
    "scores": {{
        "accuracy": <分数>,
        "completeness": <分数>,
        "relevance": <分数>,
        "practicality": <分数>,
        "clarity": <分数>
    }},
    "overall_score": <总体分数，0-10>,
    "evaluation_reasoning": "<详细说明评分理由>",
    "issues": ["<问题1>", "<问题2>", ...],
    "suggestions": ["<改进建议1>", "<改进建议2>", ...]
}}
"""
        
        try:
            # 调用LLM进行评估
            response = self.evaluator_llm.generate_content(evaluation_prompt)
            
            # 解析JSON响应
            # 尝试提取JSON部分
            response_text = response.text.strip()
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
                
            evaluation_data = json.loads(response_text)
            
            # 创建评估结果
            return EvaluationResult(
                query=query,
                expected_answer=expected,
                generated_answer=generated,
                scores=evaluation_data["scores"],
                overall_score=evaluation_data["overall_score"],
                evaluation_reasoning=evaluation_data["evaluation_reasoning"],
                issues=evaluation_data.get("issues", []),
                suggestions=evaluation_data.get("suggestions", []),
                rag_metadata=rag_metadata,
                processing_time=rag_metadata.get('processing_time', 0)
            )
            
        except Exception as e:
            logger.error(f"LLM评估失败: {e}")
            # 返回默认评估结果
            return EvaluationResult(
                query=query,
                expected_answer=expected,
                generated_answer=generated,
                scores={dim: 0.0 for dim in self.EVALUATION_DIMENSIONS},
                overall_score=0.0,
                evaluation_reasoning=f"评估失败: {str(e)}",
                issues=["评估过程出错"],
                suggestions=["检查LLM配置和响应格式"],
                rag_metadata=rag_metadata,
                processing_time=rag_metadata.get('processing_time', 0)
            )
    
    async def analyze_common_issues(self, results: List[EvaluationResult]) -> tuple[List[str], List[str]]:
        """分析常见问题并生成改进建议"""
        
        # 收集所有问题
        all_issues = []
        for result in results:
            all_issues.extend(result.issues)
            
        # 统计问题频率
        issue_counts = {}
        for issue in all_issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
            
        # 找出最常见的问题
        common_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 加载向量库元数据以了解知识库情况
        knowledge_base_info = self._analyze_knowledge_base()
        
        # 基于问题分析生成改进建议
        improvement_prompt = f"""
基于以下RAG系统的评估结果，分析问题原因并提供改进建议。

【常见问题】
{json.dumps([issue[0] for issue in common_issues], ensure_ascii=False, indent=2)}

【知识库信息】
{json.dumps(knowledge_base_info, ensure_ascii=False, indent=2)}

【各维度平均得分】
{json.dumps(self._calculate_dimension_averages(results), ensure_ascii=False, indent=2)}

请分析这些问题的根本原因，可能包括：
1. 知识库内容不足或质量问题
2. 检索算法效果不佳
3. 查询理解和重写的问题
4. 答案生成和摘要的问题

请按以下JSON格式输出分析结果：
{{
    "root_causes": ["<根本原因1>", "<根本原因2>", ...],
    "improvement_suggestions": [
        {{
            "area": "<改进领域>",
            "suggestion": "<具体建议>",
            "priority": "<high/medium/low>"
        }},
        ...
    ]
}}
"""
        
        try:
            response = self.evaluator_llm.generate_content(improvement_prompt)
            
            # 解析响应
            response_text = response.text.strip()
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
                
            analysis = json.loads(response_text)
            
            # 提取根本原因和建议
            root_causes = analysis.get("root_causes", [])
            suggestions = [s["suggestion"] for s in analysis.get("improvement_suggestions", [])]
            
            # 添加基于数据的具体建议
            if knowledge_base_info["total_chunks"] < 100:
                suggestions.append("知识库内容较少，建议增加更多游戏攻略内容")
            
            avg_scores = self._calculate_dimension_averages(results)
            if avg_scores.get("completeness", 10) < 6:
                suggestions.append("答案完整性不足，建议改进检索策略或增加相关内容")
                
            return root_causes + [issue[0] for issue in common_issues[:3]], suggestions
            
        except Exception as e:
            logger.error(f"问题分析失败: {e}")
            return (
                [issue[0] for issue in common_issues[:3]], 
                ["优化知识库内容", "改进检索算法", "增强查询理解能力"]
            )
    
    def _analyze_knowledge_base(self) -> Dict[str, Any]:
        """分析知识库的基本信息"""
        try:
            if self.metadata_path.exists():
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    
                # 统计信息
                total_chunks = len(metadata)
                topics = set()
                avg_summary_length = 0
                
                for chunk in metadata:
                    topics.add(chunk.get("topic", ""))
                    avg_summary_length += len(chunk.get("summary", ""))
                    
                avg_summary_length = avg_summary_length / total_chunks if total_chunks > 0 else 0
                
                return {
                    "total_chunks": total_chunks,
                    "unique_topics": len(topics),
                    "average_summary_length": avg_summary_length,
                    "has_keywords": any(chunk.get("keywords") for chunk in metadata)
                }
            else:
                return {
                    "total_chunks": 0,
                    "unique_topics": 0,
                    "average_summary_length": 0,
                    "has_keywords": False
                }
        except Exception as e:
            logger.error(f"知识库分析失败: {e}")
            return {
                "total_chunks": 0,
                "unique_topics": 0, 
                "average_summary_length": 0,
                "has_keywords": False
            }
    
    def _calculate_dimension_averages(self, results: List[EvaluationResult]) -> Dict[str, float]:
        """计算各维度的平均得分"""
        dimension_scores = {dim: [] for dim in self.EVALUATION_DIMENSIONS}
        
        for result in results:
            for dim, score in result.scores.items():
                if dim in dimension_scores:
                    dimension_scores[dim].append(score)
                    
        return {
            dim: sum(scores) / len(scores) if scores else 0.0
            for dim, scores in dimension_scores.items()
        }
    
    async def evaluate_all(self) -> QualityReport:
        """执行完整的质量评估"""
        
        # 确保已初始化
        if not self.rag_engine or not self.evaluator_llm:
            await self.initialize()
            
        # 加载测试数据
        test_cases = self.load_test_data()
        
        # 评估每个测试用例
        logger.info("开始评估测试用例...")
        for i, test_case in enumerate(test_cases):
            logger.info(f"评估进度: {i+1}/{len(test_cases)}")
            
            # 运行RAG查询
            rag_result = await self.run_rag_query(test_case["query"])
            
            # 评估答案质量
            evaluation = await self.evaluate_answer(
                query=test_case["query"],
                expected=test_case["answer"],
                generated=rag_result["answer"],
                rag_metadata=rag_result
            )
            
            self.evaluation_results.append(evaluation)
            
        # 计算总体统计
        total_score = sum(r.overall_score for r in self.evaluation_results)
        average_score = total_score / len(self.evaluation_results) if self.evaluation_results else 0.0
        
        # 计算各维度平均分
        dimension_averages = self._calculate_dimension_averages(self.evaluation_results)
        
        # 分析常见问题和生成建议
        common_issues, suggestions = await self.analyze_common_issues(self.evaluation_results)
        
        # 生成质量报告
        report = QualityReport(
            total_cases=len(test_cases),
            average_score=average_score,
            scores_by_dimension=dimension_averages,
            common_issues=common_issues,
            improvement_suggestions=suggestions,
            detailed_results=self.evaluation_results,
            metadata={
                "game": self.game,
                "rag_config": {
                    "hybrid_search": self.rag_engine.enable_hybrid_search,
                    "intent_reranking": self.rag_engine.enable_intent_reranking,
                    "summarization": self.rag_engine.enable_summarization
                },
                "knowledge_base_info": self._analyze_knowledge_base()
            },
            generated_at=datetime.now().isoformat()
        )
        
        return report
    
    def save_report(self, report: QualityReport, output_path: Optional[Path] = None):
        """保存评估报告"""
        if output_path is None:
            output_path = Path(__file__).parent / f"quality_report_{self.game}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
        # 转换为可序列化的字典
        report_dict = asdict(report)
        
        # 保存JSON报告
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)
            
        logger.info(f"评估报告已保存至: {output_path}")
        
        # 同时生成简化的Markdown报告
        md_path = output_path.with_suffix('.md')
        self._generate_markdown_report(report, md_path)
        
    def _generate_markdown_report(self, report: QualityReport, output_path: Path):
        """生成Markdown格式的报告摘要"""
        md_content = f"""# RAG质量评估报告 - {self.game}

生成时间: {report.generated_at}

## 总体评分

- **平均得分**: {report.average_score:.2f}/10
- **测试用例数**: {report.total_cases}

## 各维度得分

| 维度 | 平均分 | 说明 |
|------|--------|------|
"""
        
        for dim, score in report.scores_by_dimension.items():
            md_content += f"| {dim} | {score:.2f} | {self.EVALUATION_DIMENSIONS.get(dim, '')} |\n"
            
        md_content += f"""
## 主要问题

"""
        for i, issue in enumerate(report.common_issues[:5], 1):
            md_content += f"{i}. {issue}\n"
            
        md_content += f"""
## 改进建议

"""
        for i, suggestion in enumerate(report.improvement_suggestions[:5], 1):
            md_content += f"{i}. {suggestion}\n"
            
        md_content += f"""
## 详细评估结果

"""
        for i, result in enumerate(report.detailed_results, 1):
            md_content += f"""
### 测试用例 {i}

**问题**: {result.query}

**总体得分**: {result.overall_score:.1f}/10

**评估理由**: {result.evaluation_reasoning}

**检索信息**:
- 置信度: {result.rag_metadata.get('confidence', 0):.2f}
- 处理时间: {result.processing_time:.2f}秒
- 检索到的文档数: {result.rag_metadata.get('results_count', 0)}

---
"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        logger.info(f"Markdown报告已保存至: {output_path}")


async def main():
    """主函数 - 运行质量评估"""
    import sys
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 获取游戏名称（默认为helldiver2）
    game = sys.argv[1] if len(sys.argv) > 1 else "helldiver2"
    
    # 创建评估器
    evaluator = RAGQualityEvaluator(game=game)
    
    try:
        # 运行评估
        logger.info(f"开始评估 {game} 的RAG输出质量...")
        report = await evaluator.evaluate_all()
        
        # 保存报告
        evaluator.save_report(report)
        
        # 打印摘要
        print(f"\n{'='*50}")
        print(f"RAG质量评估完成 - {game}")
        print(f"{'='*50}")
        print(f"平均得分: {report.average_score:.2f}/10")
        print(f"测试用例数: {report.total_cases}")
        print(f"\n各维度得分:")
        for dim, score in report.scores_by_dimension.items():
            print(f"  - {dim}: {score:.2f}")
        print(f"\n主要问题:")
        for issue in report.common_issues[:3]:
            print(f"  - {issue}")
        print(f"\n改进建议:")
        for suggestion in report.improvement_suggestions[:3]:
            print(f"  - {suggestion}")
            
    except Exception as e:
        logger.error(f"评估过程出错: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())