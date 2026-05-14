"""
通用重试与容错包装器
让任何可能卡住或报错的环节都能自动恢复
"""
import time
from functools import wraps
from typing import Callable, Any, Optional
from loguru import logger


def retry_with_fallback(
    max_retries: int = 3,
    delay: float = 3.0,
    fallback_value: Any = None,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None,
):
    """
    通用重试装饰器
    
    :param max_retries: 最大重试次数
    :param delay: 基础延迟秒数（实际延迟 = delay * attempt，指数退避）
    :param fallback_value: 全部重试失败后返回的默认值（为 None 则继续抛异常）
    :param exceptions: 需要捕获的异常类型
    :param on_retry: 每次重试前调用的回调函数 (attempt, error)
    
    示例:
        @retry_with_fallback(max_retries=3, fallback_value={"modules": []})
        def parse_report(text):
            return llm.invoke(...)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_retries:
                        wait = delay * attempt
                        logger.warning(
                            f"[Retry] {func.__name__} 第 {attempt}/{max_retries} 次失败，"
                            f"{wait:.0f}s 后重试: {str(e)[:200]}"
                        )
                        if on_retry:
                            try:
                                on_retry(attempt, e)
                            except Exception:
                                pass
                        time.sleep(wait)
                    else:
                        logger.error(
                            f"[Retry] {func.__name__} 全部 {max_retries} 次重试失败: {str(last_error)[:500]}"
                        )
            
            if fallback_value is not None:
                logger.info(f"[Retry] 返回 fallback 值: {fallback_value}")
                return fallback_value
            raise last_error
        return wrapper
    return decorator


def safe_invoke_llm(llm, messages, fallback_content: str = "") -> str:
    """
    安全调用 LLM：带重试和超时保护
    
    :param llm: LangChain LLM 客户端
    :param messages: 消息列表
    :param fallback_content: 失败时返回的默认内容
    :return: LLM 返回的文本内容
    """
    last_error = None
    for attempt in range(1, 4):  # 最多重试 3 次
        try:
            response = llm.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            last_error = e
            logger.warning(f"[safe_invoke_llm] 第 {attempt}/3 次调用失败: {str(e)[:200]}")
            if attempt < 3:
                time.sleep(3 * attempt)
    
    logger.error(f"[safe_invoke_llm] 全部重试失败，返回 fallback: {last_error}")
    return fallback_content
