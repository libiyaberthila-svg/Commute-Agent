import time
import inspect
import functools
from typing import Dict, Any, Callable, List, Optional
from backend.database import log_tool_call
from backend.schemas import ToolCallRecord

# Try LangChain tool decorator
try:
    from langchain_core.tools import tool as lc_tool
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False


class ToolRegistry:
    """
    Central registry for all agent tools.
    Supports:
    - Direct deterministic execution
    - LangChain Tool registration
    - Performance & execution timing
    - SQLite Tool logging
    - Parameter validation
    """
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._descriptions: Dict[str, str] = {}
        self._langchain_tools: Dict[str, Any] = {}

    def register(self, name: str, description: str):
        def decorator(func: Callable):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

            self._tools[name] = func
            self._descriptions[name] = description

            if HAS_LANGCHAIN:
                try:
                    # Create LangChain tool
                    decorated_tool = lc_tool(name, description=description)(func)
                    self._langchain_tools[name] = decorated_tool
                except Exception as e:
                    pass

            return wrapper
        return decorator

    def execute(self, tool_name: str, session_id: Optional[str] = None, **kwargs) -> ToolCallRecord:
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' is not registered in ToolRegistry.")

        func = self._tools[tool_name]
        start_time = time.perf_counter()
        status = "SUCCESS"
        error_msg = None
        result = None

        try:
            # Filter kwargs to only those accepted by func
            sig = inspect.signature(func)
            valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
            result = func(**valid_kwargs)
        except Exception as e:
            status = "ERROR"
            error_msg = str(e)
            result = {"error": str(e)}

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        record = ToolCallRecord(
            tool_name=tool_name,
            input_params=kwargs,
            output_result=result,
            execution_time_ms=elapsed_ms,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            status=status,
            error_message=error_msg
        )

        # Log to SQLite
        try:
            log_tool_call(
                session_id=session_id or "direct_tool_run",
                tool_name=tool_name,
                input_params=kwargs,
                output_result=result,
                execution_time_ms=elapsed_ms,
                status=status,
                error_message=error_msg
            )
        except Exception:
            pass

        return record

    def list_tools(self) -> List[Dict[str, Any]]:
        result = []
        for name, func in self._tools.items():
            sig = inspect.signature(func)
            params = {
                k: {
                    "default": str(v.default) if v.default != inspect.Parameter.empty else None,
                    "annotation": str(v.annotation.__name__) if hasattr(v.annotation, "__name__") else str(v.annotation)
                }
                for k, v in sig.parameters.items()
            }
            result.append({
                "name": name,
                "description": self._descriptions.get(name, ""),
                "parameters": params
            })
        return result

    def get_langchain_tools(self) -> List[Any]:
        return list(self._langchain_tools.values())


registry = ToolRegistry()
