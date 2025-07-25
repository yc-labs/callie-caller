"""
Advanced SIP debugging logger for isolating call termination issues.
Tracks all SIP messages, session timers, and call states with forensic detail.
"""

import logging
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class SipMessage:
    """Detailed SIP message capture."""
    timestamp: float
    direction: str  # "outgoing" or "incoming"
    method: str
    status_code: Optional[int]
    headers: Dict[str, str]
    body: str
    remote_addr: str
    call_id: Optional[str] = None
    
@dataclass
class CallEvent:
    """Call state change event."""
    timestamp: float
    call_id: str
    event_type: str  # "state_change", "timer_event", "media_event"
    old_state: Optional[str]
    new_state: Optional[str]
    details: Dict[str, Any]

class SipDebugLogger:
    """Forensic SIP message and call state logger."""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Create session-specific log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_log = self.log_dir / f"sip_debug_{timestamp}.log"
        self.json_log = self.log_dir / f"sip_events_{timestamp}.json"
        
        # In-memory storage for analysis
        self.messages: List[SipMessage] = []
        self.events: List[CallEvent] = []
        self.call_sessions: Dict[str, Dict] = {}
        
        # Setup detailed logger
        self.logger = self._setup_logger()
        
        self.logger.info("🔍 SIP Debug Logger initialized")
        self.logger.info(f"📁 Session log: {self.session_log}")
        self.logger.info(f"📁 JSON events: {self.json_log}")
        
    def _setup_logger(self) -> logging.Logger:
        """Setup detailed file logger."""
        logger = logging.getLogger("sip_debug")
        logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers
        logger.handlers.clear()
        
        # File handler with detailed format
        file_handler = logging.FileHandler(self.session_log)
        file_handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        return logger
    
    def log_outgoing_sip(self, message: str, remote_addr: str, call_id: Optional[str] = None):
        """Log outgoing SIP message with full analysis."""
        timestamp = time.time()
        parsed = self._parse_sip_message(message, "outgoing", remote_addr, timestamp)
        parsed.call_id = call_id
        
        self.messages.append(parsed)
        
        self.logger.info(f"📤 OUTGOING SIP to {remote_addr} (Call-ID: {call_id})")
        self._log_sip_details(parsed, "📤")
        
        # Check for session timer headers
        self._analyze_session_timers(parsed)
        
        # Save to JSON
        self._save_event_json({
            'type': 'sip_message',
            'timestamp': timestamp,
            'data': asdict(parsed)
        })
    
    def log_incoming_sip(self, message: str, remote_addr: str, call_id: Optional[str] = None):
        """Log incoming SIP message with full analysis."""
        timestamp = time.time()
        parsed = self._parse_sip_message(message, "incoming", remote_addr, timestamp)
        parsed.call_id = call_id
        
        self.messages.append(parsed)
        
        self.logger.info(f"📥 INCOMING SIP from {remote_addr} (Call-ID: {call_id})")
        self._log_sip_details(parsed, "📥")
        
        # Check for session timer headers
        self._analyze_session_timers(parsed)
        
        # Check for call termination
        if parsed.method == "BYE" or (parsed.status_code and parsed.status_code >= 400):
            self._analyze_call_termination(parsed)
        
        # Save to JSON
        self._save_event_json({
            'type': 'sip_message', 
            'timestamp': timestamp,
            'data': asdict(parsed)
        })
    
    def log_call_event(self, call_id: str, event_type: str, old_state: str = None, 
                      new_state: str = None, **details):
        """Log call state change or event."""
        timestamp = time.time()
        
        event = CallEvent(
            timestamp=timestamp,
            call_id=call_id,
            event_type=event_type,
            old_state=old_state,
            new_state=new_state,
            details=details
        )
        
        self.events.append(event)
        
        if old_state != new_state:
            self.logger.info(f"🔄 CALL STATE: {call_id} {old_state} → {new_state}")
        
        self.logger.info(f"📊 CALL EVENT: {event_type} - {details}")
        
        # Track call session
        if call_id not in self.call_sessions:
            self.call_sessions[call_id] = {
                'start_time': timestamp,
                'states': [],
                'events': []
            }
        
        self.call_sessions[call_id]['events'].append(asdict(event))
        if new_state:
            self.call_sessions[call_id]['states'].append({
                'timestamp': timestamp,
                'state': new_state
            })
        
        # Save to JSON
        self._save_event_json({
            'type': 'call_event',
            'timestamp': timestamp,
            'data': asdict(event)
        })
    
    def _parse_sip_message(self, message: str, direction: str, remote_addr: str, timestamp: float) -> SipMessage:
        """Parse SIP message into structured format."""
        lines = message.strip().split('\\n')
        if not lines:
            return SipMessage(timestamp, direction, "UNKNOWN", None, {}, "", remote_addr)
        
        # Parse first line (method or status)
        first_line = lines[0].strip()
        method = None
        status_code = None
        
        if first_line.startswith('SIP/2.0'):
            # Status response
            parts = first_line.split(' ', 2)
            if len(parts) >= 2:
                try:
                    status_code = int(parts[1])
                    method = f"RESPONSE_{status_code}"
                except ValueError:
                    method = "RESPONSE_UNKNOWN"
        else:
            # Request method
            parts = first_line.split(' ', 1)
            method = parts[0] if parts else "UNKNOWN"
        
        # Parse headers
        headers = {}
        body_start = len(lines)
        
        for i, line in enumerate(lines[1:], 1):
            line = line.strip()
            if not line:  # Empty line indicates start of body
                body_start = i + 1
                break
            
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip()] = value.strip()
        
        # Get body
        body = '\\n'.join(lines[body_start:]).strip()
        
        return SipMessage(
            timestamp=timestamp,
            direction=direction,
            method=method,
            status_code=status_code,
            headers=headers,
            body=body,
            remote_addr=remote_addr
        )
    
    def _log_sip_details(self, msg: SipMessage, prefix: str):
        """Log detailed SIP message information."""
        self.logger.info(f"{prefix} Method: {msg.method}")
        if msg.status_code:
            self.logger.info(f"{prefix} Status: {msg.status_code}")
        
        # Log critical headers
        critical_headers = [
            'Call-ID', 'CSeq', 'From', 'To', 'Contact', 'Via',
            'Session-Expires', 'Min-SE', 'Supported', 'Require',
            'Authorization', 'WWW-Authenticate'
        ]
        
        for header in critical_headers:
            if header in msg.headers:
                self.logger.info(f"{prefix} {header}: {msg.headers[header]}")
        
        # Log all other headers
        other_headers = {k: v for k, v in msg.headers.items() if k not in critical_headers}
        if other_headers:
            self.logger.debug(f"{prefix} Other headers: {other_headers}")
        
        if msg.body:
            self.logger.debug(f"{prefix} Body: {msg.body[:200]}...")
    
    def _analyze_session_timers(self, msg: SipMessage):
        """Analyze session timer related headers."""
        session_expires = msg.headers.get('Session-Expires')
        min_se = msg.headers.get('Min-SE')
        supported = msg.headers.get('Supported', '')
        require = msg.headers.get('Require', '')
        
        if session_expires or min_se or 'timer' in supported or 'timer' in require:
            self.logger.warning(f"⏰ SESSION TIMER DETECTED!")
            self.logger.warning(f"⏰ Session-Expires: {session_expires}")
            self.logger.warning(f"⏰ Min-SE: {min_se}")
            self.logger.warning(f"⏰ Supported: {supported}")
            self.logger.warning(f"⏰ Require: {require}")
            
            if session_expires:
                try:
                    expires_seconds = int(session_expires.split(';')[0])
                    self.logger.warning(f"⏰ CALL WILL EXPIRE IN {expires_seconds} SECONDS!")
                    
                    # Schedule warning
                    remaining_time = expires_seconds - 5  # Warn 5 seconds before
                    if remaining_time > 0:
                        self.logger.warning(f"⏰ SESSION REFRESH NEEDED IN {remaining_time} SECONDS")
                        
                except ValueError:
                    pass
    
    def _analyze_call_termination(self, msg: SipMessage):
        """Analyze call termination reasons."""
        self.logger.error(f"☠️  CALL TERMINATION DETECTED!")
        self.logger.error(f"☠️  Method: {msg.method}")
        if msg.status_code:
            self.logger.error(f"☠️  Status: {msg.status_code}")
        
        # Look for termination reason
        reason_header = msg.headers.get('Reason')
        if reason_header:
            self.logger.error(f"☠️  Reason: {reason_header}")
        
        # Check for timeout-related status codes
        if msg.status_code in [408, 487, 491]:
            self.logger.error(f"☠️  TIMEOUT-RELATED TERMINATION!")
        
        # Log timing
        call_duration = self._calculate_call_duration(msg.call_id)
        if call_duration:
            self.logger.error(f"☠️  Call duration: {call_duration:.1f} seconds")
            if 29 <= call_duration <= 31:
                self.logger.error(f"☠️  30-SECOND TIMEOUT PATTERN DETECTED!")
    
    def _calculate_call_duration(self, call_id: Optional[str]) -> Optional[float]:
        """Calculate call duration if possible."""
        if not call_id or call_id not in self.call_sessions:
            return None
        
        session = self.call_sessions[call_id]
        if 'start_time' in session:
            return time.time() - session['start_time']
        
        return None
    
    def _save_event_json(self, event: Dict):
        """Save event to JSON log file."""
        try:
            with open(self.json_log, 'a') as f:
                json.dump(event, f)
                f.write('\\n')
        except Exception as e:
            self.logger.error(f"Failed to save JSON event: {e}")
    
    def analyze_30_second_pattern(self) -> Dict[str, Any]:
        """Analyze logs for 30-second timeout patterns."""
        analysis = {
            'calls_analyzed': len(self.call_sessions),
            'thirty_second_disconnects': [],
            'session_timer_usage': [],
            'termination_reasons': []
        }
        
        for call_id, session in self.call_sessions.items():
            # Check for 30-second pattern
            if 'start_time' in session:
                duration = time.time() - session['start_time']
                if 29 <= duration <= 31:
                    analysis['thirty_second_disconnects'].append({
                        'call_id': call_id,
                        'duration': duration,
                        'events': session['events']
                    })
        
        # Analyze session timer usage in messages
        for msg in self.messages:
            if 'Session-Expires' in msg.headers:
                analysis['session_timer_usage'].append({
                    'timestamp': msg.timestamp,
                    'direction': msg.direction,
                    'session_expires': msg.headers['Session-Expires'],
                    'call_id': msg.call_id
                })
        
        return analysis
    
    def generate_report(self) -> str:
        """Generate comprehensive analysis report."""
        analysis = self.analyze_30_second_pattern()
        
        report = f"""
🔍 SIP DEBUG ANALYSIS REPORT
{'='*50}

📊 SUMMARY:
- Total calls analyzed: {analysis['calls_analyzed']}
- 30-second disconnects: {len(analysis['thirty_second_disconnects'])}
- Total SIP messages: {len(self.messages)}
- Total events logged: {len(self.events)}

⏰ SESSION TIMER ANALYSIS:
- Session timer instances: {len(analysis['session_timer_usage'])}
"""
        
        if analysis['session_timer_usage']:
            report += "\\n🚨 SESSION TIMERS DETECTED:\\n"
            for timer in analysis['session_timer_usage']:
                report += f"  - {timer['direction']} at {timer['timestamp']}: {timer['session_expires']}\\n"
        
        if analysis['thirty_second_disconnects']:
            report += "\\n☠️  30-SECOND DISCONNECTS:\\n"
            for disconnect in analysis['thirty_second_disconnects']:
                report += f"  - Call {disconnect['call_id']}: {disconnect['duration']:.1f}s\\n"
        
        return report

# Global debug logger instance
debug_logger: Optional[SipDebugLogger] = None

def init_sip_debug_logger() -> SipDebugLogger:
    """Initialize global SIP debug logger."""
    global debug_logger
    debug_logger = SipDebugLogger()
    return debug_logger

def get_sip_debug_logger() -> Optional[SipDebugLogger]:
    """Get the global SIP debug logger."""
    return debug_logger 