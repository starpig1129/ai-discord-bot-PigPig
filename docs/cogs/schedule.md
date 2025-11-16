# Schedule Cog Documentation

## Overview

The Schedule cog provides comprehensive scheduling and event management capabilities for Discord users. It enables users to create, manage, and track events, appointments, and recurring schedules with advanced features like time zone handling, reminder integration, and collaborative scheduling.

## Features

### Core Functionality
- **Event Creation**: Create events with detailed information and scheduling
- **Recurring Events**: Set up repeating events (daily, weekly, monthly, custom patterns)
- **Time Zone Support**: Handle multiple time zones for global scheduling
- **Event Management**: View, edit, delete, and manage existing events
- **Reminder Integration**: Link events with reminder system for notifications
- **Calendar Integration**: Sync with external calendar services
- **Multi-user Events**: Collaborative scheduling with multiple participants

### Key Components
- `Schedule` class - Main cog implementation
- Event database and management system
- Time zone conversion utilities
- Recurring pattern engine
- Calendar integration adapters

## Commands

### `/schedule_create`
Creates a new scheduled event or appointment.

**Parameters**:
- `title` (string, required): Event title/name
- `description` (string, optional): Detailed event description
- `date` (string, required): Event date (YYYY-MM-DD format)
- `time` (string, required): Event time (HH:MM format)
- `duration` (int, optional): Event duration in minutes (default: 60)
- `timezone` (string, optional): Time zone for the event
- `recurring` (string, optional): Recurrence pattern (none, daily, weekly, monthly)

**Usage Examples**:
```
/schedule_create title:"Team Meeting" description:"Weekly team sync" date:"2024-12-20" time:"14:00" duration:30
/schedule_create title:"Gym Session" recurring:"daily" time:"18:00"
/schedule_create title:"Project Deadline" date:"2024-12-31" time:"23:59" timezone:"Asia/Taipei"
```

**Required Permissions**: None (personal scheduling)

### `/schedule_list`
Displays user's scheduled events and appointments.

**Parameters**:
- `view_type` (string, optional): View type (today, week, month, all)
- `filter` (string, optional): Filter events by type (work, personal, reminder)
- `include_past` (boolean, optional, default: false): Include past events

**Usage Examples**:
```
/schedule_list view_type:"week" filter:"work"
/schedule_list view_type:"today"
/schedule_list include_past:true
```

**Required Permissions**: None (user's own schedule)

### `/schedule_edit`
Edits an existing scheduled event.

**Parameters**:
- `event_id` (string, required): ID of the event to edit
- `field` (string, required): Field to edit (title, description, date, time, duration)
- `value` (string, required): New value for the field

**Usage Examples**:
```
/schedule_edit event_id:"evt_12345" field:"title" value:"Updated Team Meeting"
/schedule_edit event_id:"evt_12345" field:"time" value:"15:00"
```

**Required Permissions**: None (user's own events)

### `/schedule_delete`
Removes a scheduled event.

**Parameters**:
- `event_id` (string, required): ID of the event to delete
- `confirm` (boolean, required): Confirmation flag (must be true)

**Usage Examples**:
```
/schedule_delete event_id:"evt_12345" confirm:true
```

**Required Permissions**: None (user's own events)

### `/schedule_remind`
Links an existing schedule event with the reminder system.

**Parameters**:
- `event_id` (string, required): ID of the schedule event
- `reminder_time` (string, required): When to send reminder (e.g., "30 minutes", "1 hour")
- `custom_message` (string, optional): Custom reminder message

**Usage Examples**:
```
/schedule_remind event_id:"evt_12345" reminder_time:"15 minutes" custom_message:"Meeting starting soon!"
/schedule_remind event_id:"evt_12345" reminder_time:"1 day"
```

**Required Permissions**: None (user's own events)

## Technical Implementation

### Class Structure
```python
class Schedule(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    
    # Command handlers
    async def schedule_create_command(self, interaction: discord.Interaction,
                                     title: str, description: str = None,
                                     date: str = None, time: str = None,
                                     duration: int = 60, timezone: str = None,
                                     recurring: str = "none")
    
    async def schedule_list_command(self, interaction: discord.Interaction,
                                   view_type: str = "week", filter: str = None,
                                   include_past: bool = False)
    
    async def schedule_edit_command(self, interaction: discord.Interaction,
                                   event_id: str, field: str, value: str)
    
    async def schedule_delete_command(self, interaction: discord.Interaction,
                                     event_id: str, confirm: bool)
    
    async def schedule_remind_command(self, interaction: discord.Interaction,
                                     event_id: str, reminder_time: str,
                                     custom_message: str = None)
    
    # Core functionality
    async def create_event(self, user_id: str, event_data: dict) -> Event
    async def get_user_events(self, user_id: str, filters: dict = None) -> List[Event]
    async def update_event(self, event_id: str, user_id: str, updates: dict) -> bool
    async def delete_event(self, event_id: str, user_id: str) -> bool
    async def get_event_reminders(self, event_id: str) -> List[Reminder]
```

### Event Data Models
```python
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from enum import Enum

class EventType(Enum):
    PERSONAL = "personal"
    WORK = "work"
    REMINDER = "reminder"
    MEETING = "meeting"
    DEADLINE = "deadline"
    RECURRING = "recurring"

class RecurrencePattern(Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"

class EventStatus(Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    OVERDUE = "overdue"

@dataclass
class Event:
    id: str
    user_id: str
    title: str
    description: Optional[str]
    start_datetime: datetime
    end_datetime: datetime
    timezone: str
    event_type: EventType
    recurrence_pattern: RecurrencePattern
    recurrence_data: Optional[Dict[str, Any]]
    status: EventStatus
    created_at: datetime
    updated_at: datetime
    
    # Optional fields
    location: Optional[str] = None
    participants: List[str] = None  # List of user IDs
    reminders: List[str] = None     # List of reminder IDs
    tags: List[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'description': self.description,
            'start_datetime': self.start_datetime.isoformat(),
            'end_datetime': self.end_datetime.isoformat(),
            'timezone': self.timezone,
            'event_type': self.event_type.value,
            'recurrence_pattern': self.recurrence_pattern.value,
            'recurrence_data': self.recurrence_data,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'location': self.location,
            'participants': self.participants or [],
            'reminders': self.reminders or [],
            'tags': self.tags or [],
            'metadata': self.metadata or {}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        return cls(
            id=data['id'],
            user_id=data['user_id'],
            title=data['title'],
            description=data.get('description'),
            start_datetime=datetime.fromisoformat(data['start_datetime']),
            end_datetime=datetime.fromisoformat(data['end_datetime']),
            timezone=data['timezone'],
            event_type=EventType(data['event_type']),
            recurrence_pattern=RecurrencePattern(data['recurrence_pattern']),
            recurrence_data=data.get('recurrence_data'),
            status=EventStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            location=data.get('location'),
            participants=data.get('participants', []),
            reminders=data.get('reminders', []),
            tags=data.get('tags', []),
            metadata=data.get('metadata', {})
        )
```

### Event Database Management
```python
import sqlite3
import uuid
from typing import List, Optional, Dict, Any

class EventDatabase:
    def __init__(self, db_path: str = "data/schedule.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize schedule database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    start_datetime DATETIME NOT NULL,
                    end_datetime DATETIME NOT NULL,
                    timezone TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    recurrence_pattern TEXT NOT NULL,
                    recurrence_data TEXT,
                    status TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    location TEXT,
                    tags TEXT,
                    metadata TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_participants (
                    event_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT DEFAULT 'attendee',
                    status TEXT DEFAULT 'invited',
                    FOREIGN KEY (event_id) REFERENCES events(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    PRIMARY KEY (event_id, user_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_user_date 
                ON events (user_id, start_datetime)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_status 
                ON events (status)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_recurring 
                ON events (recurrence_pattern) WHERE recurrence_pattern != 'none'
            """)
    
    def create_event(self, event: Event) -> bool:
        """Create a new event in the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO events 
                    (id, user_id, title, description, start_datetime, end_datetime,
                     timezone, event_type, recurrence_pattern, recurrence_data,
                     status, location, tags, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.id,
                    event.user_id,
                    event.title,
                    event.description,
                    event.start_datetime.isoformat(),
                    event.end_datetime.isoformat(),
                    event.timezone,
                    event.event_type.value,
                    event.recurrence_pattern.value,
                    json.dumps(event.recurrence_data) if event.recurrence_data else None,
                    event.status.value,
                    event.location,
                    json.dumps(event.tags) if event.tags else None,
                    json.dumps(event.metadata) if event.metadata else None
                ))
                
                # Add participants if any
                if event.participants:
                    for participant_id in event.participants:
                        conn.execute("""
                            INSERT OR REPLACE INTO event_participants 
                            (event_id, user_id, role, status)
                            VALUES (?, ?, ?, ?)
                        """, (event.id, participant_id, 'attendee', 'invited'))
                
                return True
                
        except Exception as e:
            await func.report_error(e, "create_event")
            return False
    
    def get_user_events(self, user_id: str, filters: Dict[str, Any] = None) -> List[Event]:
        """Get all events for a user with optional filters"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Build query with filters
                query = """
                    SELECT events.*, GROUP_CONCAT(event_participants.user_id) as participants
                    FROM events
                    LEFT JOIN event_participants ON events.id = event_participants.event_id
                    WHERE events.user_id = ?
                """
                params = [user_id]
                
                # Add date filters
                if filters:
                    if 'date_from' in filters:
                        query += " AND events.start_datetime >= ?"
                        params.append(filters['date_from'].isoformat())
                    
                    if 'date_to' in filters:
                        query += " AND events.start_datetime <= ?"
                        params.append(filters['date_to'].isoformat())
                    
                    if 'event_type' in filters:
                        query += " AND events.event_type = ?"
                        params.append(filters['event_type'])
                    
                    if 'status' in filters:
                        query += " AND events.status = ?"
                        params.append(filters['status'])
                
                query += " GROUP BY events.id ORDER BY events.start_datetime ASC"
                
                cursor = conn.execute(query, params)
                
                events = []
                for row in cursor:
                    event_data = dict(row)
                    
                    # Parse JSON fields
                    if event_data['recurrence_data']:
                        event_data['recurrence_data'] = json.loads(event_data['recurrence_data'])
                    if event_data['tags']:
                        event_data['tags'] = json.loads(event_data['tags'])
                    if event_data['metadata']:
                        event_data['metadata'] = json.loads(event_data['metadata'])
                    
                    # Handle participants
                    if row['participants']:
                        event_data['participants'] = row['participants'].split(',')
                    else:
                        event_data['participants'] = []
                    
                    events.append(Event.from_dict(event_data))
                
                return events
                
        except Exception as e:
            await func.report_error(e, "get_user_events")
            return []
    
    def update_event(self, event_id: str, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing event"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Verify ownership
                cursor = conn.execute(
                    "SELECT id FROM events WHERE id = ? AND user_id = ?",
                    (event_id, user_id)
                )
                
                if not cursor.fetchone():
                    return False  # Event not found or not owned by user
                
                # Build update query
                set_clauses = []
                params = []
                
                for field, value in updates.items():
                    if field == 'start_datetime' or field == 'end_datetime':
                        set_clauses.append(f"{field} = ?")
                        params.append(value.isoformat())
                    elif field == 'recurrence_data' or field == 'tags' or field == 'metadata':
                        set_clauses.append(f"{field} = ?")
                        params.append(json.dumps(value) if value else None)
                    else:
                        set_clauses.append(f"{field} = ?")
                        params.append(value)
                
                set_clauses.append("updated_at = ?")
                params.append(datetime.now().isoformat())
                
                params.extend([event_id, user_id])
                
                query = f"""
                    UPDATE events 
                    SET {', '.join(set_clauses)}
                    WHERE id = ? AND user_id = ?
                """
                
                conn.execute(query, params)
                return True
                
        except Exception as e:
            await func.report_error(e, "update_event")
            return False
    
    def delete_event(self, event_id: str, user_id: str) -> bool:
        """Delete an event"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Verify ownership
                cursor = conn.execute(
                    "SELECT id FROM events WHERE id = ? AND user_id = ?",
                    (event_id, user_id)
                )
                
                if not cursor.fetchone():
                    return False  # Event not found or not owned by user
                
                # Delete event and related data
                conn.execute("DELETE FROM event_participants WHERE event_id = ?", (event_id,))
                conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
                
                return True
                
        except Exception as e:
            await func.report_error(e, "delete_event")
            return False
    
    def get_upcoming_events(self, user_id: str, hours_ahead: int = 24) -> List[Event]:
        """Get events happening within the specified timeframe"""
        now = datetime.now()
        future_time = now + timedelta(hours=hours_ahead)
        
        return self.get_user_events(user_id, {
            'date_from': now,
            'date_to': future_time
        })
```

### Recurrence Engine
```python
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import calendar

class RecurrenceEngine:
    def __init__(self):
        self.patterns = {
            'daily': self.generate_daily_events,
            'weekly': self.generate_weekly_events,
            'monthly': self.generate_monthly_events,
            'yearly': self.generate_yearly_events,
            'custom': self.generate_custom_events
        }
    
    def generate_occurrences(self, base_event: Event, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Generate all occurrences of a recurring event within a date range"""
        
        if base_event.recurrence_pattern == RecurrencePattern.NONE:
            return [base_event.start_datetime] if start_date <= base_event.start_datetime <= end_date else []
        
        pattern_func = self.patterns.get(base_event.recurrence_pattern.value)
        if not pattern_func:
            return []
        
        return pattern_func(base_event, start_date, end_date)
    
    def generate_daily_events(self, base_event: Event, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Generate daily recurring events"""
        
        occurrences = []
        current_date = base_event.start_datetime.date()
        end_date_only = end_date.date()
        
        # Find first occurrence after start_date
        while current_date < start_date.date():
            current_date += timedelta(days=1)
        
        # Generate all occurrences
        while current_date <= end_date_only:
            # Create datetime with original time
            occurrence = datetime.combine(current_date, base_event.start_datetime.time())
            occurrence = occurrence.replace(tzinfo=base_event.start_datetime.tzinfo)
            
            occurrences.append(occurrence)
            current_date += timedelta(days=1)
        
        return occurrences
    
    def generate_weekly_events(self, base_event: Event, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Generate weekly recurring events"""
        
        occurrences = []
        base_weekday = base_event.start_datetime.weekday()
        
        # Find first week containing start_date
        week_start = start_date - timedelta(days=start_date.weekday())
        
        while week_start.date() <= end_date.date():
            # Calculate occurrence for this week
            occurrence_date = week_start + timedelta(days=base_weekday)
            
            # Create datetime with original time
            occurrence = datetime.combine(occurrence_date.date(), base_event.start_datetime.time())
            occurrence = occurrence.replace(tzinfo=base_event.start_datetime.tzinfo)
            
            if start_date <= occurrence <= end_date:
                occurrences.append(occurrence)
            
            week_start += timedelta(weeks=1)
        
        return occurrences
    
    def generate_monthly_events(self, base_event: Event, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Generate monthly recurring events"""
        
        occurrences = []
        base_day = base_event.start_datetime.day
        base_time = base_event.start_datetime.time()
        
        # Start from the month of start_date
        current_month = start_date.replace(day=1)
        
        while current_month.date() <= end_date.date():
            try:
                # Create occurrence with original day and time
                occurrence_date = current_month.replace(day=base_day)
                occurrence = datetime.combine(occurrence_date, base_time)
                occurrence = occurrence.replace(tzinfo=base_event.start_datetime.tzinfo)
                
                if start_date <= occurrence <= end_date:
                    occurrences.append(occurrence)
                
            except ValueError:
                # Handle months with fewer days (e.g., February 30)
                # Use the last day of the month
                last_day = calendar.monthrange(current_month.year, current_month.month)[1]
                occurrence_date = current_month.replace(day=last_day)
                occurrence = datetime.combine(occurrence_date, base_time)
                occurrence = occurrence.replace(tzinfo=base_event.start_datetime.tzinfo)
                
                if start_date <= occurrence <= end_date:
                    occurrences.append(occurrence)
            
            # Move to next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)
        
        return occurrences
    
    def generate_custom_events(self, base_event: Event, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Generate custom recurring events based on recurrence_data"""
        
        if not base_event.recurrence_data:
            return []
        
        occurrences = []
        pattern = base_event.recurrence_data.get('pattern')
        interval = base_event.recurrence_data.get('interval', 1)
        
        if pattern == 'every_n_days':
            current_date = base_event.start_datetime
            while current_date <= end_date:
                if start_date <= current_date <= end_date:
                    occurrences.append(current_date)
                current_date += timedelta(days=interval)
        
        elif pattern == 'every_n_weeks':
            current_date = base_event.start_datetime
            while current_date <= end_date:
                if start_date <= current_date <= end_date:
                    occurrences.append(current_date)
                current_date += timedelta(weeks=interval)
        
        elif pattern == 'weekday_of_month':
            # e.g., "first Monday of every month"
            weekday = base_event.recurrence_data.get('weekday', 0)  # 0=Monday
            position = base_event.recurrence_data.get('position', 1)  # 1=first, 2=second, etc.
            
            current_month = start_date.replace(day=1)
            while current_month.date() <= end_date.date():
                # Find the nth weekday of the month
                first_day = current_month.replace(day=1)
                days_to_add = (weekday - first_day.weekday()) % 7
                nth_weekday = first_day + timedelta(days=days_to_add)
                
                occurrence_date = nth_weekday + timedelta(weeks=position - 1)
                
                # Check if occurrence is still in the same month
                if occurrence_date.month == current_month.month:
                    occurrence = datetime.combine(occurrence_date.date(), base_event.start_datetime.time())
                    occurrence = occurrence.replace(tzinfo=base_event.start_datetime.tzinfo)
                    
                    if start_date <= occurrence <= end_date:
                        occurrences.append(occurrence)
                
                # Move to next month
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)
        
        return occurrences
```

### Time Zone Management
```python
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional

class TimeZoneManager:
    def __init__(self):
        self.common_timezones = {
            'UTC': 'UTC',
            'US/Eastern': 'America/New_York',
            'US/Central': 'America/Chicago', 
            'US/Mountain': 'America/Denver',
            'US/Pacific': 'America/Los_Angeles',
            'Europe/London': 'Europe/London',
            'Europe/Paris': 'Europe/Paris',
            'Europe/Berlin': 'Europe/Berlin',
            'Asia/Tokyo': 'Asia/Tokyo',
            'Asia/Shanghai': 'Asia/Shanghai',
            'Asia/Taipei': 'Asia/Taipei',
            'Asia/Seoul': 'Asia/Seoul',
            'Australia/Sydney': 'Australia/Sydney'
        }
    
    def parse_timezone(self, timezone_str: str) -> ZoneInfo:
        """Parse timezone string and return ZoneInfo object"""
        
        # Handle common timezone abbreviations
        if timezone_str in self.common_timezones:
            timezone_str = self.common_timezones[timezone_str]
        
        try:
            return ZoneInfo(timezone_str)
        except:
            # Fallback to UTC if invalid timezone
            return ZoneInfo('UTC')
    
    def convert_datetime(self, dt: datetime, from_tz: str, to_tz: str) -> datetime:
        """Convert datetime from one timezone to another"""
        
        from_zone = self.parse_timezone(from_tz)
        to_zone = self.parse_timezone(to_tz)
        
        # If dt is naive, assume it's in from_tz
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=from_zone)
        
        # Convert to target timezone
        converted_dt = dt.astimezone(to_zone)
        return converted_dt
    
    def get_user_timezone(self, user_id: str) -> str:
        """Get user's preferred timezone (would integrate with user preferences)"""
        # This would typically fetch from user preferences database
        # For now, return a default
        return 'UTC'
    
    def format_datetime_for_user(self, dt: datetime, user_timezone: str, format_str: str = "%Y-%m-%d %H:%M") -> str:
        """Format datetime in user's timezone"""
        
        user_tz = self.parse_timezone(user_timezone)
        user_dt = dt.astimezone(user_tz)
        
        return user_dt.strftime(format_str)
    
    def calculate_duration(self, start_dt: datetime, end_dt: datetime) -> int:
        """Calculate duration in minutes between two datetimes"""
        
        duration = end_dt - start_dt
        return int(duration.total_seconds() // 60)
```

## Error Handling

### Schedule Error Management
```python
async def handle_schedule_error(self, interaction, error, context: str, event_id: str = None):
    """Handle schedule-related errors with user-friendly messages"""
    
    error_messages = {
        "event_not_found": f"Event not found or you don't have permission to access it.",
        "invalid_date_format": "Invalid date format. Please use YYYY-MM-DD format.",
        "invalid_time_format": "Invalid time format. Please use HH:MM format (24-hour).",
        "date_in_past": "Event date cannot be in the past.",
        "duration_invalid": "Event duration must be a positive number of minutes.",
        "timezone_invalid": "Invalid timezone. Please use a valid timezone identifier.",
        "recurrence_invalid": "Invalid recurrence pattern. Use: none, daily, weekly, monthly, yearly.",
        "permission_denied": "You don't have permission to modify this event.",
        "overlapping_events": "This event overlaps with another of your scheduled events.",
        "database_error": "Database error occurred. Please try again later."
    }
    
    # Determine error type and provide appropriate message
    error_str = str(error).lower()
    
    if "not found" in error_str or "no such" in error_str:
        message = error_messages["event_not_found"]
    elif "date" in error_str and "format" in error_str:
        message = error_messages["invalid_date_format"]
    elif "time" in error_str and "format" in error_str:
        message = error_messages["invalid_time_format"]
    elif "past" in error_str or "before" in error_str:
        message = error_messages["date_in_past"]
    elif "duration" in error_str or "invalid" in error_str:
        message = error_messages["duration_invalid"]
    elif "timezone" in error_str:
        message = error_messages["timezone_invalid"]
    elif "recurrence" in error_str:
        message = error_messages["recurrence_invalid"]
    elif "permission" in error_str or "denied" in error_str:
        message = error_messages["permission_denied"]
    elif "overlap" in error_str:
        message = error_messages["overlapping_events"]
    else:
        message = error_messages["database_error"]
    
    await interaction.response.send_message(message, ephemeral=True)
    await func.report_error(error, f"schedule_{context}_{event_id or 'unknown'}")
```

## Usage Examples

### Creating Events
```
User: /schedule_create title:"Doctor Appointment" description:"Annual checkup" date:"2024-12-25" time:"14:30" duration:60
Bot: ✅ Event created successfully!
Event ID: evt_12345
📅 Doctor Appointment
📍 Date: 2024-12-25 at 14:30 (60 minutes)
📝 Annual checkup

User: /schedule_create title:"Gym Session" recurring:"daily" time:"18:00"
Bot: ✅ Recurring event created!
Event ID: evt_12346
🔄 Daily recurring event
📍 Every day at 18:00 (60 minutes)
```

### Viewing Schedule
```
User: /schedule_list view_type:"week" filter:"work"
Bot: 📅 Your Work Schedule (Dec 16-22, 2024)

Monday, Dec 16:
• 09:00 - Team Meeting (evt_12347)
• 14:30 - Doctor Appointment (evt_12345)

Tuesday, Dec 17:
• 10:00 - Project Review (evt_12348)

Wednesday, Dec 18:
• 18:00 - Gym Session (evt_12346) [Daily Recurring]
```

### Editing Events
```
User: /schedule_edit event_id:"evt_12345" field:"time" value:"15:00"
Bot: ✅ Event updated successfully!
Doctor Appointment now scheduled for 15:00

User: /schedule_edit event_id:"evt_12346" field:"duration" value:"90"
Bot: ✅ Event updated successfully!
Gym Session now 90 minutes long
```

### Event Reminders
```
User: /schedule_remind event_id:"evt_12345" reminder_time:"1 hour" custom_message:"Doctor appointment in 1 hour!"
Bot: ✅ Reminder linked to event successfully!
You'll receive a reminder 1 hour before the event.

User: /schedule_remind event_id:"evt_12346" reminder_time:"15 minutes"
Bot: ✅ Reminder linked to event successfully!
You'll receive a reminder 15 minutes before each gym session.
```

## Advanced Features

### Conflict Detection
```python
def detect_conflicts(self, user_id: str, new_event: Event) -> List[Event]:
    """Detect conflicts with existing user events"""
    
    user_events = self.get_user_events(user_id)
    conflicts = []
    
    for event in user_events:
        if event.id == new_event.id:  # Skip same event
            continue
        
        # Check for time overlap
        if (new_event.start_datetime < event.end_datetime and 
            new_event.end_datetime > event.start_datetime):
            conflicts.append(event)
    
    return conflicts

async def resolve_conflicts(self, interaction, conflicts: List[Event]) -> bool:
    """Handle event conflicts with user options"""
    
    if not conflicts:
        return True
    
    # Create interactive message with conflict resolution options
    embed = discord.Embed(
        title="⚠️ Event Conflict Detected",
        description=f"This event conflicts with {len(conflicts)} existing event(s):"
    )
    
    for conflict in conflicts:
        embed.add_field(
            name=f"❌ {conflict.title}",
            value=f"🕐 {conflict.start_datetime.strftime('%Y-%m-%d %H:%M')} - {conflict.end_datetime.strftime('%H:%M')}",
            inline=False
        )
    
    embed.add_field(
        name="Actions",
        value="1️⃣ Force create (ignore conflict)\n2️⃣ Modify time\n3️⃣ Cancel",
        inline=False
    )
    
    # Send interactive message for conflict resolution
    # Implementation would involve Discord buttons/interactions
    
    return False  # Waiting for user response
```

### Calendar Integration
```python
class CalendarIntegration:
    def __init__(self):
        self.providers = {
            'google': self.google_calendar_sync,
            'outlook': self.outlook_calendar_sync,
            'apple': self.apple_calendar_sync
        }
    
    async def sync_to_external_calendar(self, event: Event, provider: str) -> bool:
        """Sync event to external calendar service"""
        
        sync_func = self.providers.get(provider)
        if not sync_func:
            return False
        
        return await sync_func(event)
    
    async def google_calendar_sync(self, event: Event) -> bool:
        """Sync event to Google Calendar"""
        
        # Implementation would use Google Calendar API
        try:
            # Prepare calendar event data
            calendar_event = {
                'summary': event.title,
                'description': event.description or '',
                'start': {
                    'dateTime': event.start_datetime.isoformat(),
                    'timeZone': event.timezone,
                },
                'end': {
                    'dateTime': event.end_datetime.isoformat(),
                    'timeZone': event.timezone,
                },
                'recurrence': [self._generate_rrule(event)]
            }
            
            # API call would go here
            # calendar_service.events().insert(calendarId='primary', body=calendar_event).execute()
            
            return True
            
        except Exception as e:
            await func.report_error(e, "google_calendar_sync")
            return False
    
    def _generate_rrule(self, event: Event) -> str:
        """Generate RRULE string for recurring events"""
        
        if event.recurrence_pattern == RecurrencePattern.NONE:
            return None
        
        if event.recurrence_pattern == RecurrencePattern.DAILY:
            return "RRULE:FREQ=DAILY"
        elif event.recurrence_pattern == RecurrencePattern.WEEKLY:
            return "RRULE:FREQ=WEEKLY"
        elif event.recurrence_pattern == RecurrencePattern.MONTHLY:
            return "RRULE:FREQ=MONTHLY"
        elif event.recurrence_pattern == RecurrencePattern.YEARLY:
            return "RRULE:FREQ=YEARLY"
        
        return None
```

## Performance Optimization

### Database Optimization
- **Indexing**: Proper indexing on user_id, start_datetime, and status
- **Query Optimization**: Efficient queries with proper WHERE clauses
- **Connection Pooling**: Efficient database connection management
- **Background Cleanup**: Regular cleanup of old completed events

### Event Processing
- **Lazy Loading**: Load event details only when needed
- **Caching**: Cache frequently accessed user events
- **Batch Operations**: Process multiple events efficiently
- **Background Sync**: Sync recurring events in background

## Configuration Options

### Bot Settings
```python
# Configuration in addons/settings.py
SCHEDULE_CONFIG = {
    "max_events_per_user": 1000,
    "max_recurrence_depth": 52,  # weeks in a year
    "default_duration": 60,      # minutes
    "supported_timezones": ["UTC", "US/Eastern", "Europe/London", "Asia/Taipei"],
    "calendar_sync": {
        "enabled": True,
        "providers": ["google", "outlook"],
        "sync_interval": 300  # 5 minutes
    },
    "reminder_integration": {
        "enabled": True,
        "default_reminder_times": ["15 minutes", "1 hour", "1 day"]
    }
}
```

## Integration Points

### With Other Cogs
```python
# Integration with reminder system for event notifications
from cogs.remind import Remind

# Integration with user data for timezone preferences
from cogs.userdata import UserData

# Integration with language manager for localization
from cogs.language_manager import LanguageManager

# Integration with channel manager for event permissions
from cogs.channel_manager import ChannelManager
```

### External Services
- **Google Calendar API**: Calendar synchronization
- **Microsoft Graph API**: Outlook calendar integration
- **Apple Calendar**: iCloud calendar sync
- **ICS Export**: Standard calendar file format
- **Webhook Services**: Real-time calendar updates

## Related Files

- `cogs/schedule.py` - Main implementation
- `data/schedule.db` - SQLite database for events
- `translations/en_US/commands/schedule.json` - English translations
- `LanguageManager` - Translation system
- `addons.settings` - Configuration management

## Future Enhancements

Potential improvements:
- **Group Events**: Collaborative event creation with multiple participants
- **Location Integration**: Add location services and maps
- **Video Conferencing**: Automatic meeting links (Zoom, Teams, etc.)
- **RSVP System**: Event invitations and response tracking
- **Weather Integration**: Weather-based event suggestions
- **AI Scheduling**: Smart scheduling suggestions based on preferences
- **Event Analytics**: Usage statistics and pattern analysis
- **Mobile Notifications**: Push notifications for mobile users
- **Holiday Detection**: Automatic holiday consideration in scheduling
- **Template System**: Pre-defined event templates for common types