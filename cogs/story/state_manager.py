from addons.logging import get_logger
from .models import StoryInstance, GMActionPlan

log = get_logger(server_id="Bot", source=__name__)

class StoryStateManager:
    """Manages story state updates based on structured GM Action Plans."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = log

    async def update_state_from_gm_plan(
        self, instance: StoryInstance, gm_plan: GMActionPlan
    ) -> StoryInstance:
        """
        Updates the story state based on a structured GMActionPlan.
        """
        # 1. Update core world state if provided
        if gm_plan.state_update:
            state_data = gm_plan.state_update
            if state_data.location:
                instance.current_location = state_data.location
                self.logger.info(f"State Update: Location changed to {state_data.location}")
            if state_data.date:
                instance.current_date = state_data.date
                self.logger.info(f"State Update: Date changed to {state_data.date}")
            if state_data.time:
                instance.current_time = state_data.time
                self.logger.info(f"State Update: Time changed to {state_data.time}")

        # 2. Handle relationship updates (This part needs coordination with the DB manager)
        if gm_plan.relationships_update:
            # This logic will likely be moved to or called from StoryManager
            # where DB access is managed. For now, we log it.
            for rel_update in gm_plan.relationships_update:
                self.logger.info(
                    f"Relationship Update Queued: {rel_update.user_name} and "
                    f"{rel_update.character_name} -> {rel_update.description}"
                )
                # In a full implementation, you would call something like:
                # db.update_relationship(story_id, character_id, user_id, new_description)

        # 3. Manage event log
        # The event title/summary is now added in StoryManager before calling this.
        if len(instance.event_log) > 20:
            instance.event_log = instance.event_log[-20:]

        return instance

    def initialize_default_state(self, instance: StoryInstance) -> StoryInstance:
        """Initialize default state for a new story instance."""
        # This method might be deprecated if all state is handled by StoryInstance fields directly
        if not instance.current_state:
            instance.current_state = {}
        
        instance.current_state.setdefault('weather', '晴朗')
        
        return instance