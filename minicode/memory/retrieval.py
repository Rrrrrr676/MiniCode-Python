"""Tokenization, query expansion, BM25, TF-IDF, and classification."""
from __future__ import annotations

import functools
import json
import logging
import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from minicode.config import MINI_CODE_DIR

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]')

_CJK_BIGRAM_RE = re.compile(r'[\u4e00-\u9fff]{2}')

_CODE_TERM_EXPANSIONS: dict[str, list[str]] = {
    "函数": ["function", "func", "method"],
    "function": ["函数", "func", "method"],
    "func": ["函数", "function", "method"],
    "method": ["函数", "function", "func"],
    "类": ["class", "type"],
    "class": ["类", "type"],
    "type": ["类", "class"],
    "变量": ["variable", "var"],
    "variable": ["变量", "var"],
    "var": ["变量", "variable"],
    "参数": ["parameter", "param", "argument", "arg"],
    "parameter": ["参数", "param", "argument"],
    "param": ["参数", "parameter", "arg"],
    "argument": ["参数", "parameter", "arg"],
    "属性": ["attribute", "attr", "property", "prop"],
    "attribute": ["属性", "attr", "property"],
    "property": ["属性", "attr", "prop"],
    "接口": ["interface"],
    "interface": ["接口"],
    "模块": ["module"],
    "module": ["模块"],
    "包": ["package"],
    "package": ["包"],
    "方法": ["method", "function"],
    "对象": ["object", "obj"],
    "object": ["对象", "obj"],
    "继承": ["inherit", "inheritance", "extends"],
    "inherit": ["继承"],
    "多态": ["polymorphism"],
    "封装": ["encapsulation", "encapsulate"],
    "异常": ["exception", "error"],
    "exception": ["异常"],
    "error": ["错误", "异常"],
    "错误": ["error", "bug"],
    "bug": ["错误", "bug", "缺陷"],
    "循环": ["loop", "iteration", "iterate"],
    "loop": ["循环"],
    "条件": ["condition"],
    "condition": ["条件"],
    "数组": ["array"],
    "array": ["数组"],
    "列表": ["list"],
    "list": ["列表"],
    "字典": ["dict", "dictionary", "map"],
    "dict": ["字典", "dictionary"],
    "dictionary": ["字典", "dict"],
    "map": ["字典", "映射"],
    "映射": ["map"],
    "集合": ["set"],
    "set": ["集合"],
    "字符串": ["string", "str"],
    "string": ["字符串"],
    "整数": ["int", "integer"],
    "integer": ["整数"],
    "浮点": ["float"],
    "float": ["浮点"],
    "布尔": ["bool", "boolean"],
    "boolean": ["布尔"],
    "同步": ["sync", "synchronous"],
    "异步": ["async", "asynchronous"],
    "async": ["异步"],
    "回调": ["callback"],
    "callback": ["回调"],
    "事件": ["event"],
    "event": ["事件"],
    "装饰器": ["decorator"],
    "decorator": ["装饰器"],
    "生成器": ["generator"],
    "generator": ["生成器"],
    "迭代器": ["iterator"],
    "iterator": ["迭代器"],
    "测试": ["test", "testing"],
    "test": ["测试"],
    "调试": ["debug", "debugging"],
    "debug": ["调试"],
    "配置": ["config", "configuration"],
    "config": ["配置"],
    "数据库": ["database", "db"],
    "database": ["数据库", "db"],
    "缓存": ["cache"],
    "cache": ["缓存"],
    "队列": ["queue"],
    "queue": ["队列"],
    "栈": ["stack"],
    "stack": ["栈"],
    "树": ["tree"],
    "tree": ["树"],
    "图": ["graph"],
    "graph": ["图"],
    "搜索": ["search"],
    "search": ["搜索"],
    "排序": ["sort", "sorting"],
    "sort": ["排序"],
    "文件": ["file"],
    "file": ["文件"],
    "路径": ["path"],
    "path": ["路径"],
    "网络": ["network"],
    "network": ["网络"],
    "请求": ["request"],
    "request": ["请求"],
    "响应": ["response"],
    "response": ["响应"],
}

_DOMAIN_TERM_EXPANSIONS: dict[str, dict[str, list[str]]] = {
    "frontend": {
        "component": ["组件", "widget", "control", "element"],
        "组件": ["component", "widget", "control"],
        "form": ["表单", "input", "field"],
        "表单": ["form", "input", "field"],
        "style": ["样式", "css", "theme", "design"],
        "样式": ["style", "css", "theme"],
        "css": ["样式", "style", "theme", "tailwind"],
        "render": ["渲染", "display", "paint"],
        "渲染": ["render", "display"],
        "state": ["状态", "store", "context"],
        "状态": ["state", "store"],
        "hook": ["hooks", "钩子"],
        "router": ["路由", "navigation"],
        "路由": ["router", "navigation", "route"],
        "button": ["按钮", "btn"],
        "modal": ["弹窗", "dialog", "popup"],
        "layout": ["布局", "grid", "flex"],
        "布局": ["layout", "grid", "flexbox"],
        "animation": ["动画", "transition", "motion"],
        "event": ["事件", "handler", "listener"],
        "props": ["属性", "properties", "parameters"],
        "dom": ["文档", "document", "node", "element"],
        "responsive": ["响应式", "adaptive", "mobile"],
        "typescript": ["ts", "type"],
    },
    "backend": {
        "api": ["端点", "endpoint", "路由", "route", "handler"],
        "endpoint": ["端点", "api", "路由"],
        "route": ["路由", "path", "endpoint", "api"],
        "auth": ["认证", "鉴权", "login", "token", "jwt", "oauth"],
        "认证": ["auth", "authentication", "login"],
        "middleware": ["中间件", "interceptor", "filter"],
        "中间件": ["middleware", "interceptor"],
        "request": ["请求", "req"],
        "response": ["响应", "res", "reply"],
        "server": ["服务器", "服务端", "host"],
        "服务器": ["server", "host"],
        "queue": ["队列", "message", "mq", "worker"],
        "队列": ["queue", "message", "worker"],
        "cache": ["缓存", "redis", "memcache"],
        "缓存": ["cache", "redis"],
        "cron": ["定时", "schedule", "job", "task"],
        "定时": ["cron", "schedule", "timer"],
        "log": ["日志", "logging", "trace"],
        "日志": ["log", "logging"],
        "validate": ["校验", "验证", "sanitize", "check"],
        "校验": ["validate", "validation", "check"],
        "rate limit": ["限流", "throttle", "quota"],
        "限流": ["rate limit", "throttle"],
        "serialize": ["序列化", "marshal", "json"],
        "序列化": ["serialize", "marshal"],
    },
    "database": {
        "migration": ["迁移", "schema change", "ddl", "alembic", "flyway"],
        "迁移": ["migration", "schema change"],
        "schema": ["模式", "结构", "ddl", "table def"],
        "query": ["查询", "select", "sql"],
        "查询": ["query", "select", "read"],
        "index": ["索引", "btree", "hash"],
        "索引": ["index", "lookup"],
        "transaction": ["事务", "commit", "rollback", "acid"],
        "事务": ["transaction", "commit"],
        "connection": ["连接", "pool", "session"],
        "连接": ["connection", "pool"],
        "postgres": ["postgresql", "pg"],
        "orm": ["prisma", "typeorm", "sequelize", "drizzle", "sqlalchemy"],
        "backup": ["备份", "dump", "restore"],
        "备份": ["backup", "dump"],
        "replica": ["副本", "standby", "slave"],
        "partition": ["分区", "shard", "split"],
    },
    "devops": {
        "deploy": ["部署", "release", "ship"],
        "部署": ["deploy", "release"],
        "docker": ["容器", "container", "image"],
        "容器": ["docker", "container"],
        "ci": ["持续集成", "pipeline", "build"],
        "pipeline": ["流水线", "ci/cd", "workflow"],
        "monitor": ["监控", "alert", "observe", "metrics"],
        "监控": ["monitor", "alert", "metrics"],
        "secret": ["密钥", "credentials", "env"],
        "密钥": ["secret", "credentials", "token"],
        "kubernetes": ["k8s", "pod", "cluster"],
        "k8s": ["kubernetes", "cluster"],
        "nginx": ["反向代理", "proxy", "gateway"],
        "terraform": ["基础设施", "infrastructure", "iac"],
        "log": ["日志", "logging", "收集", "aggregate"],
        "backup": ["备份", "snapshot", "restore"],
    },
    "testing": {
        "test": ["测试", "spec", "assert"],
        "mock": ["模拟", "stub", "fake", "spy"],
        "模拟": ["mock", "stub", "fake"],
        "assert": ["断言", "expect", "should"],
        "断言": ["assert", "expect"],
        "coverage": ["覆盖率", "cover"],
        "e2e": ["端到端", "end-to-end", "integration"],
        "unit": ["单元", "unit test"],
        "fixture": ["夹具", "setup", "teardown"],
        "regression": ["回归", "replay"],
    },
}

_BM25_K1 = 1.5  # Term frequency scaling

_BM25_B = 0.75  # Document length normalization

_CLASSIFICATION_RULES: list[tuple[str, list[str], list[str]]] = [
    ("architecture", ["architecture", "design", "pattern", "api", "rest", "backend", "service", "架构", "设计", "模式"]),
    ("code-pattern", ["function", "method", "def", "class", "函数", "方法", "类"]),
    ("testing", ["test", "assert", "pytest", "unit", "测试", "断言"]),
    ("configuration", ["config", "settings", "env", "配置", "设置", "环境"]),
    ("workflow", ["git", "commit", "branch", "merge", "工作流", "分支", "合并"]),
    ("security", ["security", "auth", "permission", "安全", "认证", "权限"]),
    ("performance", ["performance", "optimization", "benchmark", "性能", "优化", "基准"]),
    ("convention", ["convention", "style", "naming", "规范", "风格", "命名"]),
]

def _expand_query_terms(terms: list[str], active_domains: list[str] | None = None) -> list[str]:
    """Expand query terms using code terminology + domain-specific dictionaries."""
    expanded = list(terms)
    for term in terms:
        if term in _CODE_TERM_EXPANSIONS:
            expanded.extend(_CODE_TERM_EXPANSIONS[term])
    # Domain-specific expansions
    if active_domains:
        for domain in active_domains:
            domain_dict = _DOMAIN_TERM_EXPANSIONS.get(domain, {})
            for term in terms:
                if term in domain_dict:
                    expanded.extend(domain_dict[term])
    return expanded

@functools.lru_cache(maxsize=1024)
def _tokenize(text: str) -> list[str]:
    """Tokenize text into words for TF-IDF scoring.

    Handles alphanumeric words, individual CJK characters, and CJK bigrams
    for better Chinese text semantic matching.
    """
    tokens = [w.lower() for w in _WORD_RE.findall(text)]
    cjk_bigrams = [match.lower() for match in _CJK_BIGRAM_RE.findall(text)]
    return tokens + cjk_bigrams

def _compute_tf(tokens: list[str]) -> dict[str, float]:
    """Compute term frequency for a list of tokens."""
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = len(tokens)
    return {term: count / total for term, count in counts.items()}

def _compute_idf(documents: list[list[str]]) -> dict[str, float]:
    """Compute inverse document frequency across documents.

    Uses smoothed IDF formula: log((N + 1) / (df + 1)) + 1
    """
    n = len(documents)
    if n == 0:
        return {}
    doc_freq: dict[str, int] = {}
    for doc_tokens in documents:
        seen = set(doc_tokens)
        for term in seen:
            doc_freq[term] = doc_freq.get(term, 0) + 1
    return {
        term: math.log((n + 1) / (df + 1)) + 1
        for term, df in doc_freq.items()
    }

def _compute_avgdl(documents: list[list[str]]) -> float:
    """Compute average document length."""
    if not documents:
        return 0.0
    return sum(len(doc) for doc in documents) / len(documents)

def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    idf: dict[str, float],
    avgdl: float,
    *,
    k1: float = _BM25_K1,
    b: float = _BM25_B,
) -> float:
    """Compute Okapi BM25 score between query and document.

    Formula:
        score(q,d) = sum(IDF(qi) * (tf(qi,d) * (k1 + 1)) /
                         (tf(qi,d) + k1 * (1 - b + b * |d|/avgdl)))
    """
    if not query_tokens or not doc_tokens or avgdl == 0:
        return 0.0

    doc_len = len(doc_tokens)
    tf_doc = _compute_tf(doc_tokens)
    total_tokens = doc_len

    score = 0.0
    for term in set(query_tokens):
        if term not in idf:
            continue
        tf = tf_doc.get(term, 0.0)
        if tf == 0:
            continue
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * (total_tokens / avgdl))
        score += idf[term] * (numerator / denominator)

    return score

def _tfidf_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    idf: dict[str, float],
    avgdl: float = 0.0,
) -> float:
    """Compute BM25 score between query and document.

    Note: This function name is kept for backward compatibility but now
    uses BM25 scoring internally for better short-text ranking.
    """
    return _bm25_score(query_tokens, doc_tokens, idf, avgdl)

def get_tfidf_keywords(text: str, top_n: int = 10) -> list[tuple[str, float]]:
    """Extract top N most important terms from text using TF scores.

    Useful for auto-categorization and understanding key topics in text.

    Args:
        text: Input text to analyze
        top_n: Number of top keywords to return

    Returns:
        List of (term, tf_score) tuples sorted by importance
    """
    tokens = _tokenize(text)
    if not tokens:
        return []
    tf = _compute_tf(tokens)
    sorted_terms = sorted(tf.items(), key=lambda x: x[1], reverse=True)
    return sorted_terms[:top_n]

def _auto_classify_content(content: str) -> tuple[str, list[str]]:
    """Analyze content and return (category, tags) using keyword heuristics.

    Supports both English and Chinese keywords. Returns "general" category
    with empty tags if no classification rules match.

    Args:
        content: Text content to classify

    Returns:
        Tuple of (category, tags) - e.g., ("architecture", ["design-pattern"])
    """
    content_lower = content.lower()
    category_scores: dict[str, int] = {}
    matched_tags: list[str] = []

    category_to_tags = {
        "architecture": ["design-pattern"],
        "code-pattern": ["function"],
        "testing": ["test"],
        "configuration": ["config"],
        "workflow": ["git"],
        "security": ["security"],
        "performance": ["optimization"],
        "convention": ["style"],
    }

    for category, keywords in (
        (rule[0], rule[1]) for rule in _CLASSIFICATION_RULES
    ):
        score = sum(1 for kw in keywords if kw in content_lower)
        if score > 0:
            category_scores[category] = score
            matched_tags.extend(category_to_tags.get(category, []))

    if not category_scores:
        return "general", []

    best_category = max(category_scores, key=category_scores.get)
    return best_category, matched_tags

__all__ = ['_expand_query_terms', '_tokenize', '_compute_tf', '_compute_idf', '_compute_avgdl', '_bm25_score', '_tfidf_score', 'get_tfidf_keywords', '_auto_classify_content', '_BM25_B', '_BM25_K1', '_CJK_BIGRAM_RE', '_CLASSIFICATION_RULES', '_CODE_TERM_EXPANSIONS', '_DOMAIN_TERM_EXPANSIONS', '_WORD_RE']
