"""
Custom logging handler for WebSocket integration.
"""
import logging
from typing import Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from callie_caller.core.websocket_manager import WebSocketManager

class WebSocketLoggingHandler(logging.Handler):
    """Logging handler that emits logs via WebSocket."""
    
    def __init__(self, ws_manager: Optional['WebSocketManager'] = None):
        super().__init__()
        self.ws_manager = ws_manager
        
    def set_ws_manager(self, ws_manager: 'WebSocketManager'):
        """Set the WebSocket manager."""
        self.ws_manager = ws_manager
        
    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record via WebSocket."""
        try:
            # Skip WebSocket-related logs to avoid recursion
            if record.name.startswith('callie_caller.core.websocket'):
                return
            
            # Categorize logs by type
            logger_name = record.name
            # Check for RTP/audio first since rtp_bridge contains 'sip' in its path
            if 'rtp' in logger_name.lower() or 'audio' in logger_name.lower():
                log_type = 'rtp'
            elif 'sip' in logger_name.lower():
                log_type = 'sip'
            elif 'ai' in logger_name.lower() or 'gemini' in logger_name.lower():
                log_type = 'ai'
            else:
                log_type = 'system'
                
            # Format the log entry
            log_entry = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'message': self.format(record),
                'type': log_type,
                'logger': record.name
            }
            
            # Emit via WebSocket to all active calls
            active_calls = list(self.ws_manager.active_connections.keys())
            if active_calls:
                for call_id in active_calls:
                    self.ws_manager.emit_log_entry(call_id, log_type, self.format(record), record.levelname)
            else:
                # Log at debug level when no connections (only once to avoid spam)
                if not hasattr(self, '_no_connections_logged'):
                    self._no_connections_logged = True
                    import logging as std_logging
                    debug_logger = std_logging.getLogger('callie_caller.core.logging_handler')
                    debug_logger.info(f"WebSocketLoggingHandler: No active WebSocket connections available yet")
                
        except Exception as e:
            # Log the error once to avoid spam
            if not hasattr(self, '_error_logged'):
                self._error_logged = True
                import logging as std_logging
                debug_logger = std_logging.getLogger('callie_caller.core.logging_handler')
                debug_logger.error(f"WebSocketLoggingHandler error: {e}") 