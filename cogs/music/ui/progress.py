import discord

class ProgressDisplay:
    """A class to handle the display of music playback progress"""
    
    @staticmethod
    def create_progress_bar(current, total, length=20):
        """Create a more aesthetic progress bar
        
        Args:
            current (int): Current position in seconds
            total (int): Total duration in seconds
            length (int): Length of the progress bar
            
        Returns:
            str: Formatted progress bar with timestamps
        """
        filled = int(length * current / total)
        # Using more aesthetic characters for the progress bar
        bar = "━" * filled + "─" * (length - filled)
        # Add a slider character at the current position
        if filled < length:
            bar = bar[:filled] + "⚪" + bar[filled+1:]
        
        minutes_current, seconds_current = divmod(current, 60)
        minutes_total, seconds_total = divmod(total, 60)
        
        # Format with emojis and better spacing
        return f"`{int(minutes_current):02d}:{int(seconds_current):02d}` ┃{bar}┃ `{int(minutes_total):02d}:{int(seconds_total):02d}`"

    @staticmethod
    def format_timestamp(seconds):
        """Format seconds into MM:SS format
        
        Args:
            seconds (int): Time in seconds
            
        Returns:
            str: Formatted timestamp
        """
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes):02d}:{int(seconds):02d}"
