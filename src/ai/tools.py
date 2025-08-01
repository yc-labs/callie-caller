"""
AI Tools and Function Calling System for Callie Voice Assistant.
Provides various tools that the AI can use during live conversations.
"""

import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from callie_caller.ai.conversation import ConversationManager
from callie_caller.ai.client import GeminiClient
from dataclasses import dataclass
from abc import ABC, abstractmethod
import requests
from google.genai import types
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

CONTACTS_FILE = "data/contacts.json"
NOTES_FILE = "data/notes.json"
PROJECTS_FILE = "data/projects.json"

class EmailManager:
    """Manages sending emails."""
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")

    def send_email(self, to_recipients: List[str], subject: str, body: str) -> None:
        if not all([self.smtp_server, self.smtp_port, self.smtp_user, self.smtp_password]):
            raise ValueError("SMTP settings are not configured in environment variables.")

        msg = MIMEMultipart()
        msg['From'] = self.smtp_user
        msg['To'] = ", ".join(to_recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

class ProjectManager:
    """Manages project data using DataManager."""
    def __init__(self):
        self.data_manager = DataManager(PROJECTS_FILE)

    def get_all_projects(self) -> Dict[str, Any]:
        return self.data_manager._load_data()

    def get_project(self, project_name: str) -> Optional[Dict[str, Any]]:
        return self.data_manager.get_entry(project_name)

    def create_project(self, project_name: str, description: str, team_members: Optional[List[str]] = None) -> Dict[str, Any]:
        if self.get_project(project_name):
            raise ValueError("Project with this name already exists.")
        
        project_data = {
            "description": description,
            "status": "Not Started",
            "team_members": team_members or [],
            "created_at": datetime.now().isoformat(),
            "updates": []
        }
        self.data_manager.save_entry(project_name, project_data)
        return project_data

    def update_project_status(self, project_name: str, status: str, update_message: str) -> Dict[str, Any]:
        project_data = self.get_project(project_name)
        if not project_data:
            raise ValueError("Project not found.")
        
        project_data["status"] = status
        update = {
            "message": update_message,
            "timestamp": datetime.now().isoformat()
        }
        project_data["updates"].append(update)
        self.data_manager.save_entry(project_name, project_data)
        return project_data

class DataManager:
    """Manages data stored in local JSON files."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w") as f:
                json.dump({}, f)

    def _load_data(self) -> Dict[str, Any]:
        with open(self.file_path, "r") as f:
            return json.load(f)

    def _save_data(self, data: Dict[str, Any]):
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=4)

    def get_entry(self, key: str) -> Optional[Any]:
        data = self._load_data()
        return data.get(key)

    def save_entry(self, key: str, value: Any):
        data = self._load_data()
        data[key] = value
        self._save_data(data)

class ContactManager:
    """Manages contact data using DataManager."""
    def __init__(self):
        self.data_manager = DataManager(CONTACTS_FILE)

    def get_contact(self, phone_number: str) -> Optional[Dict[str, Any]]:
        return self.data_manager.get_entry(phone_number)

    def save_contact(self, phone_number: str, name: Optional[str] = None, preferences: Optional[str] = None) -> Dict[str, Any]:
        contact_data = self.get_contact(phone_number) or {}
        
        if name:
            contact_data["name"] = name
        if preferences:
            contact_data["preferences"] = preferences
        
        contact_data["last_updated"] = datetime.now().isoformat()
        self.data_manager.save_entry(phone_number, contact_data)
        return contact_data

class NotesManager:
    """Manages notes data using DataManager."""
    def __init__(self):
        self.data_manager = DataManager(NOTES_FILE)

    def get_notes(self, phone_number: str) -> Optional[List[Dict[str, Any]]]:
        return self.data_manager.get_entry(phone_number)

    def save_note(self, phone_number: str, note: str) -> Dict[str, Any]:
        notes = self.get_notes(phone_number) or []
        
        note_data = {
            "note": note,
            "timestamp": datetime.now().isoformat()
        }
        notes.append(note_data)
        self.data_manager.save_entry(phone_number, notes)
        return note_data

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
            now = datetime.now()
            
            if format == "iso":
                result = now.isoformat()
            elif format == "timestamp":
                result = int(now.timestamp())
            elif format == "full":
                result = {
                    "iso": now.isoformat(),
                    "readable": now.strftime("%A, %B %d, %Y at %I:%M %p %Z"),
                    "timestamp": int(now.timestamp()),
                    "timezone": str(now.astimezone().tzinfo),
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
    
class SaveContactTool(BaseTool):
    """Saves or updates contact information for the current caller."""
    
    def __init__(self):
        self.contact_manager = ContactManager()
    
    @property
    def name(self) -> str:
        return "save_contact"
    
    @property
    def description(self) -> str:
        return "Save or update contact details like name and preferences for the current caller. This information is linked to their phone number."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the contact."
                },
                "preferences": {
                    "type": "string",
                    "description": "User preferences or other notes."
                }
            },
            "required": []
        }
    
    async def execute(self, phone_number: str, name: Optional[str] = None, preferences: Optional[str] = None) -> ToolResult:
        if not phone_number:
            return ToolResult(success=False, error="Phone number is required to save contact.")
        if not name and not preferences:
            return ToolResult(success=False, error="Either a name or preferences must be provided to save contact.")
            
        try:
            contact_data = await asyncio.to_thread(
                self.contact_manager.save_contact, phone_number, name, preferences
            )
            return ToolResult(success=True, data=contact_data)
        except Exception as e:
            logger.error(f"SaveContactTool error: {e}")
            return ToolResult(success=False, error=str(e))

class GetContactTool(BaseTool):
    """Retrieves contact information for the current caller."""

class SaveNoteTool(BaseTool):
    """Saves a note for the current caller."""

    def __init__(self):
        self.notes_manager = NotesManager()

    @property
    def name(self) -> str:
        return "save_note"

    @property
    def description(self) -> str:
        return "Save a note for the current caller. The note is linked to their phone number."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The note to save."
                }
            },
            "required": ["note"]
        }

    async def execute(self, phone_number: str, note: str) -> ToolResult:
        if not phone_number:
            return ToolResult(success=False, error="Phone number is required to save a note.")
        if not note:
            return ToolResult(success=False, error="Note content must be provided.")
            
        try:
            note_data = await asyncio.to_thread(
                self.notes_manager.save_note, phone_number, note
            )
            return ToolResult(success=True, data=note_data)
        except Exception as e:
            logger.error(f"SaveNoteTool error: {e}")
            return ToolResult(success=False, error=str(e))

class GetNotesTool(BaseTool):
    """Retrieves all notes for the current caller."""
class CreateProjectTool(BaseTool):
    """Creates a new project."""
    def __init__(self):
        self.project_manager = ProjectManager()

    @property
    def name(self) -> str:
        return "create_project"

    @property
    def description(self) -> str:
        return "Create a new project with a name, description, and optional team members."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "The name of the project."
                },
                "description": {
                    "type": "string",
                    "description": "A description of the project."
                },
                "team_members": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "A list of team members on the project."
                }
            },
            "required": ["project_name", "description"]
        }

    async def execute(self, project_name: str, description: str, team_members: Optional[List[str]] = None) -> ToolResult:
        try:
            project_data = await asyncio.to_thread(
                self.project_manager.create_project, project_name, description, team_members
            )
            return ToolResult(success=True, data=project_data)
        except Exception as e:
            logger.error(f"CreateProjectTool error: {e}")
            return ToolResult(success=False, error=str(e))

class GetProjectStatusTool(BaseTool):
    """Gets the status of a project."""
    def __init__(self):
        self.project_manager = ProjectManager()

    @property
    def name(self) -> str:
        return "get_project_status"

    @property
    def description(self) -> str:
        return "Get the status and other details of a specific project."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "The name of the project to get the status of."
                }
            },
            "required": ["project_name"]
        }

    async def execute(self, project_name: str) -> ToolResult:
        try:
            project_data = await asyncio.to_thread(self.project_manager.get_project, project_name)
            if project_data:
                return ToolResult(success=True, data=project_data)
            else:
                return ToolResult(success=False, error="Project not found.")
        except Exception as e:
            logger.error(f"GetProjectStatusTool error: {e}")
            return ToolResult(success=False, error=str(e))

class UpdateProjectStatusTool(BaseTool):
    """Updates the status of a project."""
    def __init__(self):
        self.project_manager = ProjectManager()

    @property
    def name(self) -> str:
        return "update_project_status"

    @property
    def description(self) -> str:
        return "Update the status of a project and add an update message."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "The name of the project to update."
                },
                "status": {
                    "type": "string",
                    "description": "The new status of the project."
                },
                "update_message": {
                    "type": "string",
                    "description": "A message describing the update."
                }
            },
            "required": ["project_name", "status", "update_message"]
        }

    async def execute(self, project_name: str, status: str, update_message: str) -> ToolResult:
        try:
            project_data = await asyncio.to_thread(
                self.project_manager.update_project_status, project_name, status, update_message
            )
            return ToolResult(success=True, data=project_data)
        except Exception as e:
            logger.error(f"UpdateProjectStatusTool error: {e}")
            return ToolResult(success=False, error=str(e))

class ListProjectsTool(BaseTool):
    """Lists all projects."""
    def __init__(self):
        self.project_manager = ProjectManager()

    @property
    def name(self) -> str:
        return "list_projects"

    @property
    def description(self) -> str:
        return "List all active projects."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self) -> ToolResult:
        try:
            projects = await asyncio.to_thread(self.project_manager.get_all_projects)
            return ToolResult(success=True, data=projects)
        except Exception as e:
            logger.error(f"ListProjectsTool error: {e}")
            return ToolResult(success=False, error=str(e))

class ConversationSummaryTool(BaseTool):
    """Summarizes the current conversation."""
    def __init__(self):
        self.conversation_manager = ConversationManager()
        self.ai_client = GeminiClient()

    @property
    def name(self) -> str:
        return "summarize_conversation"

    @property
    def description(self) -> str:
        return "Summarize the current conversation."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self, conversation_id: str) -> ToolResult:
        try:
            conversation = self.conversation_manager.get_conversation(conversation_id)
            if not conversation:
                return ToolResult(success=False, error="Conversation not found.")

            summary = await asyncio.to_thread(
                self.ai_client.generate_call_summary,
                [{'role': m.role, 'content': m.content} for m in conversation.messages]
            )
            return ToolResult(success=True, data={"summary": summary})
        except Exception as e:
            logger.error(f"ConversationSummaryTool error: {e}")
            return ToolResult(success=False, error=str(e))

class ActionItemExtractionTool(BaseTool):
    """Extracts action items from the current conversation."""

class HangupCallTool(BaseTool):
    """Hangs up the current call."""
    def __init__(self, voip_adapter):
        self.voip_adapter = voip_adapter

    @property
    def name(self) -> str:
        return "hangup_call"

    @property
    def description(self) -> str:
        return "Hang up the current call."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self) -> ToolResult:
        try:
            if self.voip_adapter:
                self.voip_adapter.hangup_call()
                return ToolResult(success=True, data={"status": "Call hung up."})
            else:
                return ToolResult(success=False, error="VOIP adapter not available.")
        except Exception as e:
            logger.error(f"HangupCallTool error: {e}")
            return ToolResult(success=False, error=str(e))



class EmailTool(BaseTool):
    """Sends an email."""
    def __init__(self):
        self.email_manager = EmailManager()

    @property
    def name(self) -> str:
        return "send_email"

    @property
    def description(self) -> str:
        return "Send an email to one or more recipients."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to_recipients": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "A list of recipient email addresses."
                },
                "subject": {
                    "type": "string",
                    "description": "The subject of the email."
                },
                "body": {
                    "type": "string",
                    "description": "The body of the email."
                }
            },
            "required": ["to_recipients", "subject", "body"]
        }

    async def execute(self, to_recipients: List[str], subject: str, body: str) -> ToolResult:
        try:
            await asyncio.to_thread(
                self.email_manager.send_email, to_recipients, subject, body
            )
            return ToolResult(success=True, data={"status": "Email sent."})
        except Exception as e:
            logger.error(f"EmailTool error: {e}")
            return ToolResult(success=False, error=str(e))

class ToolManager:
    """Manages AI tools and handles function calling for Live API."""
    
    def __init__(self, voip_adapter=None):
        """Initialize tool manager with available tools."""
        self.tools: Dict[str, BaseTool] = {}
        self.voip_adapter = voip_adapter
        self._setup_default_tools()
        
    def _setup_default_tools(self) -> None:
        """Setup default tools."""
        default_tools = [
            TimeInfoTool(),
            WeatherTool(),
            CalculatorTool(),
            ReminderTool(),
            # NewsSearchTool(),  # Commented out - not implemented yet
            SaveContactTool(),
            # GetContactTool(),  # Commented out - not implemented yet
            SaveNoteTool(),
            # GetNotesTool(),  # Commented out - not implemented yet
            CreateProjectTool(),
            GetProjectStatusTool(),
            UpdateProjectStatusTool(),
            ListProjectsTool(),
            ConversationSummaryTool(),
            # ActionItemExtractionTool(),  # Commented out - not implemented yet
            EmailTool(),
            HangupCallTool(self.voip_adapter),
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
        
        # Inspect the tool's execute method signature
        import inspect
        sig = inspect.signature(tool.execute)
        
        # Filter kwargs to only include parameters accepted by the tool's execute method
        tool_kwargs = {
            k: v for k, v in kwargs.items() if k in sig.parameters
        }

        try:
            result = await tool.execute(**tool_kwargs)
            logger.info(f"Tool {function_name} executed successfully: {result.success}")
            return result
        except Exception as e:
            logger.error(f"Tool {function_name} execution failed: {e}")
            return ToolResult(success=False, error=f"Tool execution error: {str(e)}")
    
    async def handle_function_call(self, function_call, phone_number: Optional[str] = None, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Handle a function call from the Live API and return formatted response."""
        function_name = function_call.name
        args = dict(function_call.args) if function_call.args else {}
        
        logger.info(f"🔧 Function call received for {phone_number} in conversation {conversation_id}: {function_name}({args})")
        
        # Execute the tool, passing the phone number and conversation_id if the tool accepts them
        result = await self.execute_tool(function_name, phone_number=phone_number, conversation_id=conversation_id, **args)
        
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

# Global tool manager instances
_tool_managers: Dict[str, ToolManager] = {}

def get_tool_manager(conversation_id: str, voip_adapter=None) -> ToolManager:
    """Get the tool manager instance for a given conversation."""
    if conversation_id not in _tool_managers:
        _tool_managers[conversation_id] = ToolManager(voip_adapter)
    return _tool_managers[conversation_id]
