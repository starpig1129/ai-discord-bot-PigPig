# Remind Cog Documentation

## Overview

The Remind cog provides comprehensive reminder and scheduling capabilities for Discord users. It enables users to set personal reminders, schedule future actions, and receive notifications at specified times with multi-language support and flexible scheduling options.

## Features

### Core Functionality
- **Personal Reminders**: Set reminders for specific times and dates
- **Flexible Scheduling**: Support for relative and absolute time expressions
- **Recurring Reminders**: Set up periodic reminders (daily, weekly, monthly)
- **Reminder Management**: View, edit, and delete existing reminders
- **Notification System**: Discord-based notification delivery
- **Multi-language Support**: Full localization of time expressions and messages

### Key Components
- `Remind` class - Main cog implementation
- Time expression parser and validator
- Reminder storage and management system
- Background task scheduler
- Multi-language time formatting

## Commands

### `/remind`
Creates a new reminder with flexible time scheduling.

**Parameters**:
- `message` (string, required): The reminder message
- `time` (string, required): When to remind (supports natural language)
- `repeat` (string, optional): Recurrence pattern (daily, weekly, monthly, none)

**Time Format Examples**:
- Absolute: "2024-01-01 14:30", "in 2 hours", "next monday at 3pm"
- Relative: "5 minutes", "2 hours 30 minutes", "tomorrow"
- Natural: "every day at 9am", "weekly on friday at 6pm"

**Usage Examples**:
```
/remind message:"Team meeting" time:"tomorrow at 2pm"
/remind message:"Take medicine" time:"every day at 8am" repeat:"daily"
/remind message:"Weekly report" time:"next monday 9am" repeat:"weekly"
```

**Required Permissions**: None (per-user reminders)

### `/list_reminders`
Displays all active reminders for the user.

**Parameters**:
- `show_completed` (boolean, optional, default: false): Include completed/reminded reminders

**Usage Examples**:
```
/list_reminders
/list_reminders show_completed:true
```

**Required Permissions**: None (user's own reminders only)

### `/delete_reminder`
Removes a specific reminder.

**Parameters**:
- `reminder_id` (string, required): The ID of the reminder to delete

**Usage Examples**:
```
/delete_reminder reminder_id:"rem_12345"
```

**Required Permissions**: None (user's own reminders only)

## Technical Implementation

### Class Structure
```python
class Remind(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    async def _schedule_background_task(self)
    
    # Command handlers
    async def remind_command(self, interaction: discord.Interaction, 
                            message: str, time: str, repeat: str = "none")
    async def list_reminders_command(self, interaction: discord.Interaction, 
                                    show_completed: bool = False)
    async def delete_reminder_command(self, interaction: discord.Interaction,
                                     reminder_id: str)
    
    # Background processing
    async def reminder_scheduler(self)
    async def process_due_reminders(self)
    async def send_reminder_notification(self, reminder: dict)
```

### Time Expression Parser
```python
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

class TimeExpressionParser:
    def __init__(self):
        # Time unit patterns
        self.time_patterns = {
            'seconds': r'(\d+)\s*(?:sec|second|secs|seconds)?',
            'minutes': r'(\d+)\s*(?:min|minute|mins|minutes)?',
            'hours': r'(\d+)\s*(?:hour|hours|hr|hrs)?',
            'days': r'(\d+)\s*(?:day|days|d)?',
            'weeks': r'(\d+)\s*(?:week|weeks|wk|wks)?',
            'months': r'(\d+)\s*(?:month|months|mon|mons)?',
            'years': r'(\d+)\s*(?:year|years|yr|yrs|y)?'
        }
        
        # Relative time keywords
        self.relative_keywords = {
            'now': lambda: datetime.now(timezone.utc),
            'today': lambda: datetime.now(timezone.utc).replace(hour=23, minute=59, second=59),
            'tomorrow': lambda: datetime.now(timezone.utc) + timedelta(days=1),
            'yesterday': lambda: datetime.now(timezone.utc) - timedelta(days=1),
            'next week': lambda: datetime.now(timezone.utc) + timedelta(weeks=1),
            'next month': lambda: datetime.now(timezone.utc).replace(month=datetime.now().month % 12 + 1)
        }

    def parse_time_expression(self, expression: str, user_timezone: timezone = timezone.utc) -> datetime:
        """Parse natural language time expressions"""
        
        expression = expression.strip().lower()
        
        # Handle "in X time" format
        relative_match = re.search(r'in\s+(.+)$', expression)
        if relative_match:
            duration_str = relative_match.group(1)
            return self.parse_relative_time(duration_str)
        
        # Handle direct time specification (e.g., "tomorrow at 3pm")
        if 'at' in expression:
            return self.parse_time_with_at(expression, user_timezone)
        
        # Handle day-based expressions (e.g., "next monday")
        if any(day in expression for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
            return self.parse_day_expression(expression, user_timezone)
        
        # Handle "every day/week/month" patterns
        if expression.startswith(('every day', 'daily', 'weekly', 'monthly')):
            return self.parse_recurring_expression(expression, user_timezone)
        
        # Default to relative time from now
        return self.parse_relative_time(expression)

    def parse_relative_time(self, duration_str: str) -> datetime:
        """Parse relative time expressions like '2 hours', '5 minutes', etc."""
        
        total_seconds = 0
        current_time = datetime.now(timezone.utc)
        
        # Parse all time units in the string
        for unit, pattern in self.time_patterns.items():
            matches = re.findall(pattern, duration_str)
            if matches:
                amount = sum(int(match) for match in matches)
                multiplier = {
                    'seconds': 1,
                    'minutes': 60,
                    'hours': 3600,
                    'days': 86400,
                    'weeks': 604800,
                    'months': 2629746,  # Average days per month
                    'years': 31556952   # Average days per year
                }
                total_seconds += amount * multiplier[unit]
        
        if total_seconds > 0:
            return current_time + timedelta(seconds=total_seconds)
        else:
            # Fallback: try to parse as datetime string
            try:
                return datetime.fromisoformat(duration_str.replace('Z', '+00:00'))
            except:
                raise ValueError(f"Cannot parse time expression: {duration_str}")

    def parse_time_with_at(self, expression: str, user_timezone: timezone) -> datetime:
        """Parse expressions like 'tomorrow at 3pm' or 'monday at 9:30'"""
        
        parts = expression.split(' at ')
        date_part = parts[0].strip()
        time_part = parts[1].strip() if len(parts) > 1 else "00:00"
        
        # Parse date part
        if date_part in ['today', 'now']:
            target_date = datetime.now(user_timezone).date()
        elif date_part in ['tomorrow', 'next day']:
            target_date = (datetime.now(user_timezone) + timedelta(days=1)).date()
        else:
            target_date = self.parse_date_part(date_part)
        
        # Parse time part
        time_obj = self.parse_time_part(time_part)
        
        return datetime.combine(target_date, time_obj, tzinfo=user_timezone)

    def parse_recurring_expression(self, expression: str, user_timezone: timezone) -> datetime:
        """Parse recurring expressions like 'every day at 9am'"""
        
        # For now, set to next occurrence of the pattern
        now = datetime.now(user_timezone)
        
        if expression.startswith(('every day', 'daily')):
            next_occurrence = now + timedelta(days=1)
            next_occurrence = next_occurrence.replace(hour=9, minute=0, second=0, microsecond=0)
            return next_occurrence
        elif expression.startswith(('weekly', 'every week')):
            days_ahead = 7 - now.weekday()  # Next Monday
            if days_ahead <= 0:  # If today is Monday, next Monday is 7 days away
                days_ahead += 7
            next_occurrence = now + timedelta(days=days_ahead)
            next_occurrence = next_occurrence.replace(hour=9, minute=0, second=0, microsecond=0)
            return next_occurrence
        else:
            # Default to tomorrow at 9am
            next_occurrence = now + timedelta(days=1)
            next_occurrence = next_occurrence.replace(hour=9, minute=0, second=0, microsecond=0)
            return next_occurrence
```

### Reminder Storage System
```python
import sqlite3
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class Reminder:
    id: str
    user_id: str
    message: str
    remind_time: datetime
    created_time: datetime
    repeat_pattern: str = "none"
    is_active: bool = True
    times_triggered: int = 0
    max_triggers: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'message': self.message,
            'remind_time': self.remind_time.isoformat(),
            'created_time': self.created_time.isoformat(),
            'repeat_pattern': self.repeat_pattern,
            'is_active': self.is_active,
            'times_triggered': self.times_triggered,
            'max_triggers': self.max_triggers
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Reminder':
        return cls(
            id=data['id'],
            user_id=data['user_id'],
            message=data['message'],
            remind_time=datetime.fromisoformat(data['remind_time']),
            created_time=datetime.fromisoformat(data['created_time']),
            repeat_pattern=data.get('repeat_pattern', 'none'),
            is_active=data.get('is_active', True),
            times_triggered=data.get('times_triggered', 0),
            max_triggers=data.get('max_triggers')
        )

class ReminderDatabase:
    def __init__(self, db_path: str = "data/reminders.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize reminder database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    remind_time DATETIME NOT NULL,
                    created_time DATETIME NOT NULL,
                    repeat_pattern TEXT DEFAULT 'none',
                    is_active BOOLEAN DEFAULT TRUE,
                    times_triggered INTEGER DEFAULT 0,
                    max_triggers INTEGER,
                    reminder_data TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_remind_time 
                ON reminders (remind_time) WHERE is_active = 1
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_id 
                ON reminders (user_id)
            """)
    
    def save_reminder(self, reminder: Reminder):
        """Save reminder to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO reminders 
                (id, user_id, message, remind_time, created_time, 
                 repeat_pattern, is_active, times_triggered, max_triggers, reminder_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reminder.id,
                reminder.user_id,
                reminder.message,
                reminder.remind_time.isoformat(),
                reminder.created_time.isoformat(),
                reminder.repeat_pattern,
                reminder.is_active,
                reminder.times_triggered,
                reminder.max_triggers,
                json.dumps(reminder.to_dict())
            ))
    
    def get_user_reminders(self, user_id: str, include_inactive: bool = False) -> List[Reminder]:
        """Get all reminders for a user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = """
                SELECT reminder_data FROM reminders 
                WHERE user_id = ?
            """
            if not include_inactive:
                query += " AND is_active = 1"
            query += " ORDER BY remind_time ASC"
            
            cursor = conn.execute(query, (user_id,))
            reminders = []
            
            for row in cursor:
                data = json.loads(row['reminder_data'])
                reminders.append(Reminder.from_dict(data))
            
            return reminders
    
    def get_due_reminders(self, current_time: datetime) -> List[Reminder]:
        """Get all reminders that are due now"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute("""
                SELECT reminder_data FROM reminders 
                WHERE is_active = 1 AND remind_time <= ?
            """, (current_time.isoformat(),))
            
            reminders = []
            for row in cursor:
                data = json.loads(row['reminder_data'])
                reminders.append(Reminder.from_dict(data))
            
            return reminders
    
    def delete_reminder(self, reminder_id: str, user_id: str) -> bool:
        """Delete a specific reminder"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM reminders 
                WHERE id = ? AND user_id = ?
            """, (reminder_id, user_id))
            
            return cursor.rowcount > 0
    
    def update_reminder(self, reminder: Reminder):
        """Update an existing reminder"""
        self.save_reminder(reminder)
```

### Background Scheduler
```python
import asyncio
from datetime import datetime, timezone, timedelta

class ReminderScheduler:
    def __init__(self, bot, reminder_db: ReminderDatabase):
        self.bot = bot
        self.db = reminder_db
        self.running = False
        self.scheduler_task = None
    
    async def start_scheduler(self):
        """Start the background reminder scheduler"""
        if self.running:
            return
        
        self.running = True
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
    
    async def stop_scheduler(self):
        """Stop the background reminder scheduler"""
        self.running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
    
    async def _scheduler_loop(self):
        """Main scheduler loop - runs every minute"""
        while self.running:
            try:
                current_time = datetime.now(timezone.utc)
                due_reminders = self.db.get_due_reminders(current_time)
                
                for reminder in due_reminders:
                    await self._process_due_reminder(reminder, current_time)
                
                # Sleep for 30 seconds to check more frequently
                await asyncio.sleep(30)
                
            except Exception as e:
                # Log error but continue scheduling
                await func.report_error(e, "reminder_scheduler")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _process_due_reminder(self, reminder: Reminder, current_time: datetime):
        """Process a reminder that's due"""
        try:
            # Send notification
            await self._send_reminder_notification(reminder)
            
            # Update reminder statistics
            reminder.times_triggered += 1
            
            # Handle recurring reminders
            if reminder.repeat_pattern != "none":
                next_time = self._calculate_next_occurrence(reminder, current_time)
                
                # Check if we should continue recurring
                if (reminder.max_triggers is None or 
                    reminder.times_triggered < reminder.max_triggers):
                    
                    reminder.remind_time = next_time
                    self.db.save_reminder(reminder)
                else:
                    # Max triggers reached, deactivate reminder
                    reminder.is_active = False
                    self.db.save_reminder(reminder)
            else:
                # One-time reminder, deactivate it
                reminder.is_active = False
                self.db.save_reminder(reminder)
            
        except Exception as e:
            await func.report_error(e, f"reminder_processing_{reminder.id}")
    
    def _calculate_next_occurrence(self, reminder: Reminder, current_time: datetime) -> datetime:
        """Calculate next occurrence for recurring reminders"""
        
        if reminder.repeat_pattern == "daily":
            return current_time + timedelta(days=1)
        elif reminder.repeat_pattern == "weekly":
            return current_time + timedelta(weeks=1)
        elif reminder.repeat_pattern == "monthly":
            # Handle month boundaries
            next_month = current_time.month + 1
            next_year = current_time.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            
            try:
                return current_time.replace(year=next_year, month=next_month)
            except ValueError:
                # Handle month with fewer days (e.g., February 30)
                return current_time.replace(year=next_year, month=next_month, day=28)
        else:
            # Default to daily
            return current_time + timedelta(days=1)
    
    async def _send_reminder_notification(self, reminder: Reminder):
        """Send reminder notification to user"""
        try:
            user = self.bot.get_user(int(reminder.user_id))
            if not user:
                return
            
            # Create embed for reminder
            embed = discord.Embed(
                title="🔔 Reminder",
                description=reminder.message,
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Add recurrence info if applicable
            if reminder.repeat_pattern != "none":
                embed.add_field(
                    name="Repeat Pattern",
                    value=reminder.repeat_pattern.title(),
                    inline=True
                )
            
            if reminder.times_triggered > 0:
                embed.add_field(
                    name="Times Triggered",
                    value=str(reminder.times_triggered),
                    inline=True
                )
            
            embed.set_footer(text=f"Reminder ID: {reminder.id}")
            
            await user.send(embed=embed)
            
        except discord.Forbidden:
            # User has DMs disabled
            pass
        except Exception as e:
            await func.report_error(e, f"reminder_notification_{reminder.id}")
```

## Error Handling

### Time Expression Validation
```python
def validate_time_expression(self, expression: str) -> bool:
    """Validate time expression before parsing"""
    
    # Check for potentially malicious content
    dangerous_patterns = [
        r'eval\(',
        r'exec\(',
        r'__import__',
        r'globals\(',
        r'locals\('
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, expression, re.IGNORECASE):
            return False
    
    # Check for reasonable length
    if len(expression) > 200:
        return False
    
    return True

async def handle_reminder_error(self, interaction, error, context: str):
    """Handle reminder-related errors with user-friendly messages"""
    
    error_messages = {
        "invalid_time_format": "Invalid time format. Try '2 hours', 'tomorrow at 3pm', or '2024-01-01 14:30'.",
        "time_in_past": "Reminder time cannot be in the past.",
        "time_too_far": "Reminder time cannot be more than 1 year in the future.",
        "reminder_too_long": "Reminder message is too long (max 500 characters).",
        "too_many_reminders": "You have too many active reminders. Please delete some first.",
        "reminder_not_found": "Reminder not found or you don't have permission to delete it."
    }
    
    # Classify error and send appropriate message
    error_str = str(error).lower()
    
    if "past" in error_str or "before" in error_str:
        message = error_messages['time_in_past']
    elif "format" in error_str or "parse" in error_str:
        message = error_messages['invalid_time_format']
    elif "too far" in error_str or "year" in error_str:
        message = error_messages['time_too_far']
    elif "length" in error_str or "long" in error_str:
        message = error_messages['reminder_too_long']
    elif "not found" in error_str or "permission" in error_str:
        message = error_messages['reminder_not_found']
    else:
        message = error_messages['invalid_time_format']
    
    await interaction.response.send_message(message, ephemeral=True)
    await func.report_error(error, f"reminder_{context}")
```

## Performance Optimization

### Database Optimization
- **Indexing**: Proper indexing on reminder_time and user_id
- **Pagination**: Load reminders in batches for large lists
- **Cleanup**: Automatic cleanup of old completed reminders
- **Connection Pooling**: Efficient database connections

### Scheduling Optimization
- **Smart Scheduling**: Only check reminders that could be due soon
- **Batch Processing**: Process multiple due reminders efficiently
- **Memory Management**: Clean up old reminders from memory

## Usage Examples

### Basic Reminders
```
User: /remind message:"Call mom" time:"in 2 hours"
Bot: Reminder set! I'll remind you in 2 hours.
Reminder ID: rem_12345

User: /remind message:"Team meeting" time:"tomorrow at 2pm"
Bot: Reminder set! I'll remind you tomorrow at 2:00 PM.
Reminder ID: rem_12346
```

### Recurring Reminders
```
User: /remind message:"Take vitamins" time:"every day at 8am" repeat:"daily"
Bot: Daily reminder set! I'll remind you every day at 8:00 AM.

User: /remind message:"Gym workout" time:"next monday at 6am" repeat:"weekly"
Bot: Weekly reminder set! I'll remind you every Monday at 6:00 AM.
```

### Reminder Management
```
User: /list_reminders
Bot: Your active reminders:
• Tomorrow 2:00 PM - Team meeting (ID: rem_12346)
• Every day 8:00 AM - Take vitamins (ID: rem_12347)

User: /delete_reminder reminder_id:"rem_12345"
Bot: Reminder deleted successfully!
```

## Advanced Features

### Natural Language Support
- **Relative Time**: "in 2 hours", "5 minutes ago", "next week"
- **Relative Days**: "tomorrow", "next monday", "friday"
- **Relative Dates**: "next month", "next year", "christmas"
- **Complex Expressions**: "2 hours 30 minutes", "every other day"

### Recurring Patterns
- **Daily**: Every day at specified time
- **Weekly**: Every week on specified day
- **Monthly**: Every month on specified date
- **Custom**: Flexible recurring patterns

### Smart Scheduling
- **Timezone Support**: Automatic timezone detection and handling
- **DST Handling**: Automatic daylight saving time adjustments
- **Holiday Awareness**: Skip reminders on holidays (future enhancement)

## Integration Points

### With Other Cogs
```python
# Integration with user data for reminder preferences
from cogs.userdata import UserData

# Integration with language manager for time formatting
from cogs.language_manager import LanguageManager

# Integration with channel manager for reminder permissions
from cogs.channel_manager import ChannelManager
```

### External Services
- **Database Systems**: SQLite for local storage, PostgreSQL for cloud deployment
- **Time Services**: NTP synchronization for accurate time
- **Notification Services**: Discord webhooks for backup notifications

## Configuration Options

### Bot Settings
```python
# Configuration in addons/settings.py
REMINDER_CONFIG = {
    "max_reminders_per_user": 100,
    "max_reminder_time_days": 365,
    "default_reminder_time": "1 hour",
    "notification_timeout": 30,
    "database_backup_interval": 86400
}
```

### User Preferences
```python
# User-configurable reminder settings
USER_PREFERENCES = {
    "default_reminder_time": "5 minutes",
    "notification_method": "dm",  # dm, channel, webhook
    "timezone": "auto",  # auto, UTC, user-specified
    "reminder_advance_minutes": 0
}
```

## Security Considerations

### Data Protection
- **User Isolation**: Each user's reminders are completely isolated
- **Input Sanitization**: All reminder messages are sanitized
- **Rate Limiting**: Prevent spam reminder creation
- **Permission Checks**: Ensure users can only manage their own reminders

### Privacy Protection
- **Encrypted Storage**: Sensitive reminder content encryption
- **Data Retention**: Automatic cleanup of old reminders
- **Access Control**: Secure database access patterns

## Related Files

- `cogs/remind.py` - Main implementation
- `data/reminders.db` - SQLite database for reminders
- `translations/en_US/commands/remind.json` - English translations
- `LanguageManager` - Translation system
- `addons.settings` - Configuration management

## Future Enhancements

Potential improvements:
- **Location-based reminders**: "Remind me when I get home"
- **Weather-aware reminders**: Skip outdoor reminders during bad weather
- **Group reminders**: Share reminders with team members
- **Reminder templates**: Pre-defined reminder patterns
- **Smart reminders**: AI-powered reminder suggestions
- **Integration reminders**: Connect with calendar and task management apps
- **Advanced notification methods**: Email, SMS, push notifications
- **Reminder analytics**: Track reminder effectiveness and completion rates