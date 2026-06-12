import functools
import logging
from typing import Any, Callable

def trace_tool(logger: logging.Logger):
    """Decorator to log tool inputs and outputs."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Avoid logging full raw payload of large inputs if needed, 
            # but usually args are short for tool inputs.
            logger.info(f"[{func.__name__}] IN: args={args}, kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                out_str = str(result)
                if len(out_str) > 500:
                    logger.info(f"[{func.__name__}] OUT: <truncated, length={len(out_str)}>")
                else:
                    logger.info(f"[{func.__name__}] OUT: {out_str}")
                return result
            except Exception as e:
                logger.error(f"[{func.__name__}] ERR: {e}", exc_info=True)
                raise
        return wrapper
    return decorator
