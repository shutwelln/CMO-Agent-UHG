"""Tool registry for agent capabilities."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union, get_type_hints

import structlog

from ..llm.base import ToolDefinition

logger = structlog.get_logger()

# Type alias for async tool functions
ToolFunction = Callable[..., Awaitable[Any]]


def get_json_schema_type(python_type: type) -> Dict[str, Any]:
    """Convert Python type to JSON Schema type."""
    type_map: Dict[type, Dict[str, Any]] = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
    }

    origin = getattr(python_type, "__origin__", None)

    # Handle Optional[X] and Union[X, Y, ...] — unwrap to the first non-None type
    if origin is Union:
        args = getattr(python_type, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return get_json_schema_type(non_none[0])
        return {"type": "string"}

    # Handle Dict[K, V] and typing.Dict[K, V] → object
    if origin is dict:
        return {"type": "object"}

    # Handle List[X] and typing.List[X] → array with item schema
    if origin is list:
        args = getattr(python_type, "__args__", (Any,))
        item_type = args[0] if args else Any
        return {
            "type": "array",
            "items": get_json_schema_type(item_type) if item_type != Any else {},
        }

    return type_map.get(python_type, {"type": "string"})


class ToolRegistry:
    """Registry for tools that the LLM can invoke.

    Tools are async functions that the agent can call based on LLM decisions.
    The registry handles tool definition generation and execution.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolFunction] = {}
        self._definitions: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Callable[[ToolFunction], ToolFunction]:
        """Decorator to register a tool function.

        Args:
            name: Tool name (defaults to function name)
            description: Tool description (defaults to docstring)

        Example:
            @registry.register(
                name="search_web",
                description="Search the web for information"
            )
            async def search_web(query: str) -> dict:
                ...
        """

        def decorator(func: ToolFunction) -> ToolFunction:
            tool_name = name or func.__name__
            tool_description = description or func.__doc__ or f"Execute {tool_name}"

            # Build parameter schema from type hints
            hints = get_type_hints(func)
            sig = inspect.signature(func)

            properties: Dict[str, Any] = {}
            required: List[str] = []

            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue

                param_type = hints.get(param_name, str)
                properties[param_name] = get_json_schema_type(param_type)

                # Add description from parameter annotation if available
                if param.annotation != inspect.Parameter.empty:
                    # Could extract from Annotated types in the future
                    pass

                # Required if no default value
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            definition = ToolDefinition(
                name=tool_name,
                description=tool_description,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            )

            self._tools[tool_name] = func
            self._definitions[tool_name] = definition

            logger.debug("tool_registered", name=tool_name)
            return func

        return decorator

    def get_tool(self, name: str) -> Optional[ToolFunction]:
        """Get a tool function by name."""
        return self._tools.get(name)

    def get_definition(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool definition by name."""
        return self._definitions.get(name)

    def get_all_definitions(self) -> List[ToolDefinition]:
        """Get all registered tool definitions."""
        return list(self._definitions.values())

    def get_definitions_by_names(self, names: List[str]) -> List[ToolDefinition]:
        """Get tool definitions for specific tool names only."""
        return [self._definitions[n] for n in names if n in self._definitions]

    def get_tool_names(self) -> List[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name with the given arguments.

        Args:
            tool_name: Tool name to execute (named to avoid collision with user args)
            arguments: Dictionary of arguments to pass to the tool

        Returns:
            Tool execution result

        Raises:
            KeyError: If tool is not registered
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool not found: {tool_name}")

        # Backward compatibility: convert 'name' to 'workflow_name' for workflow tools
        if tool_name in ("create_workflow", "update_workflow") and "name" in arguments:
            logger.warning(
                "deprecated_argument",
                tool_name=tool_name,
                deprecated_arg="name",
                new_arg="workflow_name",
                message="Use 'workflow_name' instead of 'name' for workflow tools",
            )
            arguments = arguments.copy()
            arguments["workflow_name"] = arguments.pop("name")

        logger.info("tool_executing", tool_name=tool_name, arguments=arguments)

        try:
            result = await tool(**arguments)
            logger.info("tool_completed", tool_name=tool_name)
            return result
        except Exception as e:
            logger.error("tool_failed", tool_name=tool_name, error=str(e))
            raise

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self._definitions.clear()
