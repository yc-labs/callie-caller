"""
AI Tools and Function Calling System for Callie Voice Assistant.
Provides various tools that the AI can use during live conversations.
"""

import logging
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
import requests
from google.genai import types

logger = logging.getLogger(__name__)

@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class BaseTool(ABC):
    """Base class for AI tools."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (must match function declaration)."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for the AI."""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """Tool parameters schema."""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    def get_function_declaration(self) -> Dict[str, Any]:
        """Get function declaration for Google GenAI."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }

class TimeInfoTool(BaseTool):
    """Provides current time and date information."""
    
    @property
    def name(self) -> str:
        return "get_current_time"
    
    @property
    def description(self) -> str:
        return "Get current date and time information in various formats and timezones."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Timezone name (e.g., 'America/New_York', 'UTC', 'Europe/London'). Defaults to UTC.",
                    "default": "UTC"
                },
                "format": {
                    "type": "string",
                    "enum": ["iso", "readable", "timestamp", "full"],
                    "description": "Output format: 'iso' (ISO 8601), 'readable' (human-friendly), 'timestamp' (Unix), 'full' (detailed)",
                    "default": "readable"
                }
            },
            "required": []
        }
    
    async def execute(self, timezone: str = "UTC", format: str = "readable") -> ToolResult:
        """Get current time information."""
        try:
            now = datetime.now(timezone.utc)
            
            if format == "iso":
                result = now.isoformat()
            elif format == "timestamp":
                result = int(now.timestamp())
            elif format == "full":
                result = {
                    "iso": now.isoformat(),
                    "readable": now.strftime("%A, %B %d, %Y at %I:%M %p %Z"),
                    "timestamp": int(now.timestamp()),
                    "timezone": str(now.tzinfo),
                    "day_of_week": now.strftime("%A"),
                    "month": now.strftime("%B"),
                    "year": now.year
                }
            else:  # readable
                result = now.strftime("%A, %B %d, %Y at %I:%M %p UTC")
            
            logger.info(f"TimeInfoTool executed: {result}")
            return ToolResult(success=True, data=result)
            
        except Exception as e:
            logger.error(f"TimeInfoTool error: {e}")
            return ToolResult(success=False, error=f"Failed to get time: {str(e)}")

class WeatherTool(BaseTool):
    """Gets weather information using a free weather API."""
    
    @property
    def name(self) -> str:
        return "get_weather"
    
    @property
    def description(self) -> str:
        return "Get current weather information for a specific location using coordinates or city name."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location name (e.g., 'New York', 'London', 'Tokyo') or coordinates (e.g., '40.7128,-74.0060')"
                },
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial", "kelvin"],
                    "description": "Temperature units: 'metric' (Celsius), 'imperial' (Fahrenheit), 'kelvin'",
                    "default": "metric"
                }
            },
            "required": ["location"]
        }
    
    async def execute(self, location: str, units: str = "metric") -> ToolResult:
        """Get weather for a location using Open-Meteo API (free, no key required)."""
        try:
            # First, geocode the location if it's not coordinates
            if ',' in location and location.replace('.', '').replace('-', '').replace(',', '').isdigit():
                # Already coordinates
                lat, lon = map(float, location.split(','))
                location_name = f"{lat:.2f},{lon:.2f}"
            else:
                # Geocode using a simple service
                geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
                async with asyncio.timeout(10):
                    geocode_response = await asyncio.to_thread(requests.get, geocode_url)
                geocode_data = geocode_response.json()
                
                if not geocode_data.get('results'):
                    return ToolResult(success=False, error=f"Location '{location}' not found")
                
                result = geocode_data['results'][0]
                lat, lon = result['latitude'], result['longitude']
                location_name = result.get('name', location)
            
            # Get weather data
            weather_url = f"https://api.open-meteo.com/v1/current_weather?latitude={lat}&longitude={lon}&temperature_unit={'fahrenheit' if units == 'imperial' else 'celsius'}"
            
            async with asyncio.timeout(10):
                weather_response = await asyncio.to_thread(requests.get, weather_url)
            weather_data = weather_response.json()
            
            current = weather_data.get('current_weather', {})
            
            # Format response
            temp_unit = "°F" if units == "imperial" else "°C" if units == "metric" else "K"
            
            result = {
                "location": location_name,
                "temperature": f"{current.get('temperature', 'Unknown')}{temp_unit}",
                "wind_speed": f"{current.get('windspeed', 'Unknown')} km/h",
                "weather_code": current.get('weathercode', 'Unknown'),
                "time": current.get('time', 'Unknown')
            }
            
            # Interpret weather code
            weather_codes = {
                0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
                55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 95: "Thunderstorm"
            }
            
            code = current.get('weathercode', 0)
            result["conditions"] = weather_codes.get(code, "Unknown conditions")
            
            logger.info(f"WeatherTool executed for {location_name}: {result}")
            return ToolResult(success=True, data=result)
            
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="Weather request timed out")
        except Exception as e:
            logger.error(f"WeatherTool error: {e}")
            return ToolResult(success=False, error=f"Failed to get weather: {str(e)}")

class CalculatorTool(BaseTool):
    """Performs mathematical calculations."""
    
    @property
    def name(self) -> str:
        return "calculate"
    
    @property
    def description(self) -> str:
        return "Perform mathematical calculations including basic arithmetic, trigonometry, and common functions."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)')"
                }
            },
            "required": ["expression"]
        }
    
    async def execute(self, expression: str) -> ToolResult:
        """Safely evaluate mathematical expressions."""
        try:
            import math
            
            # Define safe functions and constants
            safe_dict = {
                # Math functions
                'abs': abs, 'round': round, 'min': min, 'max': max,
                'pow': pow, 'sqrt': math.sqrt, 'log': math.log, 'log10': math.log10,
                'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
                'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
                'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
                'exp': math.exp, 'floor': math.floor, 'ceil': math.ceil,
                'degrees': math.degrees, 'radians': math.radians,
                # Constants
                'pi': math.pi, 'e': math.e, 'inf': math.inf,
                # Basic operations (already supported by eval)
                '__builtins__': {}
            }
            
            # Clean expression (basic safety)
            clean_expr = expression.replace('^', '**')  # Convert ^ to **
            
            # Evaluate safely
            result = eval(clean_expr, safe_dict)
            
            # Format result
            if isinstance(result, float):
                if result.is_integer():
                    result = int(result)
                else:
                    result = round(result, 10)  # Limit decimal places
            
            logger.info(f"CalculatorTool executed: {expression} = {result}")
            return ToolResult(success=True, data={
                "expression": expression,
                "result": result,
                "type": type(result).__name__
            })
            
        except Exception as e:
            logger.error(f"CalculatorTool error: {e}")
            return ToolResult(success=False, error=f"Calculation error: {str(e)}")

class ReminderTool(BaseTool):
    """Sets reminders and manages simple notes."""
    
    def __init__(self):
        self.reminders: List[Dict[str, Any]] = []
    
    @property
    def name(self) -> str:
        return "set_reminder"
    
    @property
    def description(self) -> str:
        return "Set a reminder or note for the user. Can store text reminders with optional timing."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The reminder message or note content"
                },
                "minutes": {
                    "type": "integer",
                    "description": "Minutes from now to trigger reminder (optional)",
                    "minimum": 1,
                    "maximum": 1440
                },
                "category": {
                    "type": "string",
                    "enum": ["personal", "work", "call", "general"],
                    "description": "Category of reminder",
                    "default": "general"
                }
            },
            "required": ["message"]
        }
    
    async def execute(self, message: str, minutes: Optional[int] = None, category: str = "general") -> ToolResult:
        """Set a reminder."""
        try:
            reminder = {
                "id": len(self.reminders) + 1,
                "message": message,
                "category": category,
                "created_at": datetime.now().isoformat(),
                "trigger_at": datetime.now().timestamp() + (minutes * 60) if minutes else None,
                "triggered": False
            }
            
            self.reminders.append(reminder)
            
            result_text = f"Reminder set: {message}"
            if minutes:
                result_text += f" (in {minutes} minutes)"
            
            logger.info(f"ReminderTool executed: {result_text}")
            return ToolResult(success=True, data={
                "reminder_id": reminder["id"],
                "message": message,
                "trigger_in_minutes": minutes,
                "category": category,
                "confirmation": result_text
            })
            
        except Exception as e:
            logger.error(f"ReminderTool error: {e}")
            return ToolResult(success=False, error=f"Failed to set reminder: {str(e)}")

class NewsSearchTool(BaseTool):
    """Searches for recent news using a simple news API."""
    
    @property
    def name(self) -> str:
        return "search_news"
    
    @property
    def description(self) -> str:
        return "Search for recent news articles on a specific topic or get general news headlines."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for news (e.g., 'technology', 'politics', 'sports'). Leave empty for general news."
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of articles to return (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 3
                }
            },
            "required": []
        }
    
    async def execute(self, query: str = "", limit: int = 3) -> ToolResult:
        """Search for news using a free news service."""
        try:
            # Use a simple news aggregator API (this is a mock implementation)
            # In a real implementation, you'd use services like NewsAPI, Reddit API, or RSS feeds
            
            # For demonstration, return mock news data
            mock_articles = [
                {
                    "title": "AI Technology Advances in Voice Recognition",
                    "summary": "New breakthroughs in voice AI technology improve accuracy and naturalness",
                    "source": "Tech News",
                    "published_at": "2025-01-20T12:00:00Z"
                },
                {
                    "title": "Climate Change Conference Announces New Initiatives",
                    "summary": "Global leaders commit to ambitious environmental goals",
                    "source": "World News",
                    "published_at": "2025-01-20T10:30:00Z"
                },
                {
                    "title": "Stock Market Shows Strong Performance",
                    "summary": "Major indices reach new highs amid positive economic indicators",
                    "source": "Financial Times",
                    "published_at": "2025-01-20T09:15:00Z"
                }
            ]
            
            # Filter by query if provided
            if query:
                filtered_articles = [
                    article for article in mock_articles 
                    if query.lower() in article["title"].lower() or query.lower() in article["summary"].lower()
                ]
                articles = filtered_articles[:limit]
            else:
                articles = mock_articles[:limit]
            
            if not articles:
                return ToolResult(success=False, error=f"No news found for query: '{query}'")
            
            result = {
                "query": query or "general news",
                "article_count": len(articles),
                "articles": articles
            }
            
            logger.info(f"NewsSearchTool executed: found {len(articles)} articles for '{query}'")
            return ToolResult(success=True, data=result)
            
        except Exception as e:
            logger.error(f"NewsSearchTool error: {e}")
            return ToolResult(success=False, error=f"Failed to search news: {str(e)}")

class ToolManager:
    """Manages AI tools and handles function calling for Live API."""
    
    def __init__(self):
        """Initialize tool manager with available tools."""
        self.tools: Dict[str, BaseTool] = {}
        self._setup_default_tools()
        
    def _setup_default_tools(self) -> None:
        """Setup default tools."""
        default_tools = [
            TimeInfoTool(),
            WeatherTool(),
            CalculatorTool(),
            ReminderTool(),
            NewsSearchTool()
        ]
        
        for tool in default_tools:
            self.register_tool(tool)
        
        logger.info(f"Initialized ToolManager with {len(self.tools)} tools: {list(self.tools.keys())}")
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a new tool."""
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    def unregister_tool(self, tool_name: str) -> bool:
        """Unregister a tool."""
        if tool_name in self.tools:
            del self.tools[tool_name]
            logger.debug(f"Unregistered tool: {tool_name}")
            return True
        return False
    
    def get_function_declarations(self) -> List[Dict[str, Any]]:
        """Get all function declarations for Google GenAI."""
        declarations = []
        for tool in self.tools.values():
            declarations.append(tool.get_function_declaration())
        return declarations
    
    def get_tools_for_genai(self) -> List[types.Tool]:
        """Get tools formatted for Google GenAI Live API."""
        function_declarations = self.get_function_declarations()
        return [types.Tool(function_declarations=function_declarations)]
    
    async def execute_tool(self, function_name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with given parameters."""
        if function_name not in self.tools:
            logger.error(f"Unknown tool: {function_name}")
            return ToolResult(success=False, error=f"Tool '{function_name}' not found")
        
        tool = self.tools[function_name]
        logger.info(f"Executing tool: {function_name} with args: {kwargs}")
        
        try:
            result = await tool.execute(**kwargs)
            logger.info(f"Tool {function_name} executed successfully: {result.success}")
            return result
        except Exception as e:
            logger.error(f"Tool {function_name} execution failed: {e}")
            return ToolResult(success=False, error=f"Tool execution error: {str(e)}")
    
    async def handle_function_call(self, function_call) -> Dict[str, Any]:
        """Handle a function call from the Live API and return formatted response."""
        function_name = function_call.name
        args = dict(function_call.args) if function_call.args else {}
        
        logger.info(f"🔧 Function call received: {function_name}({args})")
        
        # Execute the tool
        result = await self.execute_tool(function_name, **args)
        
        # Format response for Live API
        if result.success:
            response_data = {
                "success": True,
                "result": result.data,
                "tool": function_name,
                "execution_time": datetime.now().isoformat()
            }
            if result.metadata:
                response_data["metadata"] = result.metadata
        else:
            response_data = {
                "success": False,
                "error": result.error,
                "tool": function_name,
                "execution_time": datetime.now().isoformat()
            }
        
        logger.info(f"🔧 Function call result: {function_name} -> {result.success}")
        return response_data
    
    def get_tool_info(self) -> Dict[str, Any]:
        """Get information about all available tools."""
        tools_info = {}
        for name, tool in self.tools.items():
            tools_info[name] = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
        return tools_info
    
    def get_tool_summary(self) -> str:
        """Get a human-readable summary of available tools."""
        summary_lines = ["Available AI Tools:"]
        for tool in self.tools.values():
            summary_lines.append(f"  • {tool.name}: {tool.description}")
        return "\n".join(summary_lines)

# Global tool manager instance
_tool_manager: Optional[ToolManager] = None

def get_tool_manager() -> ToolManager:
    """Get the global tool manager instance."""
    global _tool_manager
    if _tool_manager is None:
        _tool_manager = ToolManager()
    return _tool_manager 