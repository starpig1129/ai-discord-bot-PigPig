import logging
import re
from typing import Dict, Any
from .models import StoryInstance

class StoryStateManager:
    """Manages story state updates based on LLM responses."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def update_state_from_llm(self, instance: StoryInstance, llm_response: str) -> StoryInstance:
        """
        Updates the story state based on the LLM's response.
        This is a simplified implementation that could be expanded with more sophisticated parsing.
        """
        # Simple state extraction from LLM response
        # In a more advanced implementation, we could use structured prompts or parse specific markers
        
        # Look for location changes
        location_match = re.search(r'(?:到了|前往|來到|進入了?)\s*([^。！？\n]+)', llm_response)
        if location_match:
            new_location = location_match.group(1).strip()
            instance.current_state['location'] = new_location
            self.logger.debug(f"Updated location to: {new_location}")

        # Look for time changes
        time_match = re.search(r'(?:時間|現在是|到了)\s*([^。！？\n]*(?:早上|中午|下午|晚上|夜晚|凌晨)[^。！？\n]*)', llm_response)
        if time_match:
            new_time = time_match.group(1).strip()
            instance.current_state['time'] = new_time
            self.logger.debug(f"Updated time to: {new_time}")

        # Add the event to the log
        event_summary = self._create_event_summary(llm_response)
        instance.event_log.append(f"GM: {event_summary}")
        
        # Keep event log manageable (last 20 events)
        if len(instance.event_log) > 20:
            instance.event_log = instance.event_log[-20:]

        return instance

    def _create_event_summary(self, llm_response: str) -> str:
        """Creates a concise summary of the LLM response for the event log."""
        # Simple truncation - could be improved with summarization
        if len(llm_response) <= 100:
            return llm_response
        else:
            # Find a good break point
            truncated = llm_response[:97]
            last_space = truncated.rfind(' ')
            if last_space > 50:  # Only break at space if it's not too early
                return truncated[:last_space] + "..."
            else:
                return truncated + "..."

    def initialize_default_state(self, instance: StoryInstance) -> StoryInstance:
        """Initialize default state for a new story instance."""
        if not instance.current_state:
            instance.current_state = {}
        
        # Set default values if not already present
        instance.current_state.setdefault('location', '未知地點')
        instance.current_state.setdefault('time', '未知時間')
        instance.current_state.setdefault('weather', '晴朗')
        
        return instance