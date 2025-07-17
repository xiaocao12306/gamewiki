"""
调试BM25检索问题 - 分析分词和匹配逻辑
================================

目标：分析为什么包含"warbond recommendation"的条目没有被正确匹配
"""

import jieba
import re
from typing import List, Set

def debug_tokenization():
    """调试分词问题"""
    print("=== BM25分词调试 ===\n")
    
    # 测试查询
    query = "best warbond recommendations guide"
    
    # 测试目标文本（从metadata.json中的实际条目）
    target_texts = [
        "Warbond Recommendation: Democratic Detonation",
        "Warbond Recommendation: Truth Enforcers", 
        "Warbond Recommendation: Polar Patriots",
        "Warbond Recommendation: Steeled Veterans",
        "Weapon Recommendations from Warbonds",  # 这个确实被匹配了
    ]
    
    print(f"🔍 查询: {query}")
    print(f"📝 标准化查询: {query.lower()}")
    
    # 模拟现有的预处理逻辑
    def current_preprocess_text(text: str) -> List[str]:
        """当前的预处理逻辑（简化版）"""
        if not text:
            return []
            
        # 转换为小写
        text = text.lower()
        
        # 移除特殊字符，但保留中文、英文、数字和空格
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', text)
        
        # 中文分词（jieba对英文处理可能有问题）
        tokens = list(jieba.cut(text))
        
        # 基本停用词
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        # 过滤
        filtered_tokens = []
        for token in tokens:
            token = token.strip()
            if (token and 
                token not in stop_words and 
                (len(token) > 1 or token.isdigit())):
                filtered_tokens.append(token)
        
        return filtered_tokens
    
    # 分析查询分词
    query_tokens = current_preprocess_text(query)
    print(f"🔤 查询分词: {query_tokens}")
    
    print(f"\n📋 目标文本分词结果:")
    for i, text in enumerate(target_texts, 1):
        tokens = current_preprocess_text(text)
        print(f"{i}. '{text}'")
        print(f"   分词: {tokens}")
        
        # 检查匹配
        matched = []
        for query_token in query_tokens:
            if query_token in tokens:
                matched.append(query_token)
        print(f"   匹配的查询词: {matched}")
        print(f"   匹配数量: {len(matched)}/{len(query_tokens)}")
        print()

def debug_english_tokenization():
    """专门调试英文分词问题"""
    print("=== 英文分词问题调试 ===\n")
    
    test_phrases = [
        "warbond recommendation",
        "warbond recommendations", 
        "best warbond recommendations guide",
        "Warbond Recommendation: Democratic Detonation"
    ]
    
    print("🔍 jieba分词结果:")
    for phrase in test_phrases:
        tokens = list(jieba.cut(phrase.lower()))
        print(f"'{phrase}' -> {tokens}")
    
    print("\n🔍 简单空格分词结果:")
    for phrase in test_phrases:
        tokens = phrase.lower().split()
        print(f"'{phrase}' -> {tokens}")

def suggest_fix():
    """建议修复方案"""
    print("=== 修复建议 ===\n")
    
    print("🔧 问题分析:")
    print("1. jieba分词主要针对中文，对英文分词不够准确")
    print("2. 'recommendations'（复数）和'recommendation'（单数）可能无法正确匹配")
    print("3. 英文词汇可能被错误分割")
    
    print("\n💡 修复方案:")
    print("1. 对英文使用空格分词，对中文使用jieba分词")
    print("2. 添加词干提取（stemming）以匹配单复数形式")
    print("3. 添加同义词扩展")
    print("4. 改进权重计算逻辑")

def improved_preprocess_text(text: str) -> List[str]:
    """改进的预处理逻辑"""
    if not text:
        return []
        
    # 转换为小写
    text = text.lower()
    
    # 分离中文和英文处理
    # 简单的英文词干处理
    def simple_stem(word):
        """简单的词干提取"""
        if word.endswith('s') and len(word) > 3:
            # 去除复数s
            return word[:-1]
        if word.endswith('ing') and len(word) > 5:
            return word[:-3]
        if word.endswith('ed') and len(word) > 4:
            return word[:-2]
        return word
    
    # 移除标点符号
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', text)
    
    # 检测是否包含中文
    has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', text))
    
    if has_chinese:
        # 包含中文，使用jieba分词
        tokens = list(jieba.cut(text))
    else:
        # 纯英文，使用空格分词
        tokens = text.split()
    
    # 停用词
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    
    # 过滤和词干处理
    processed_tokens = []
    for token in tokens:
        token = token.strip()
        if (token and 
            token not in stop_words and 
            (len(token) > 1 or token.isdigit())):
            # 应用词干提取
            stemmed = simple_stem(token)
            processed_tokens.append(stemmed)
            # 如果词干不同，也加入原词
            if stemmed != token:
                processed_tokens.append(token)
    
    return processed_tokens

def test_improved_tokenization():
    """测试改进的分词逻辑"""
    print("=== 改进分词测试 ===\n")
    
    query = "best warbond recommendations guide"
    target_texts = [
        "Warbond Recommendation: Democratic Detonation",
        "Warbond Recommendation: Truth Enforcers", 
        "Weapon Recommendations from Warbonds",
    ]
    
    print(f"🔍 查询: {query}")
    
    # 测试改进的分词
    query_tokens = improved_preprocess_text(query)
    print(f"🔤 改进分词: {query_tokens}")
    
    print(f"\n📋 目标文本分词结果（改进版）:")
    for i, text in enumerate(target_texts, 1):
        tokens = improved_preprocess_text(text)
        print(f"{i}. '{text}'")
        print(f"   分词: {tokens}")
        
        # 检查匹配
        matched = []
        for query_token in query_tokens:
            if query_token in tokens:
                matched.append(query_token)
        print(f"   匹配的查询词: {matched}")
        print(f"   匹配数量: {len(matched)}/{len(query_tokens)}")
        print()

if __name__ == "__main__":
    debug_tokenization()
    print("\n" + "="*50 + "\n")
    debug_english_tokenization()
    print("\n" + "="*50 + "\n")
    suggest_fix()
    print("\n" + "="*50 + "\n")
    test_improved_tokenization() 