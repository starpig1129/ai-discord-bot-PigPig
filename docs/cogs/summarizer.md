# Summarizer Cog Documentation

## Overview

The Summarizer cog provides intelligent conversation and content summarization capabilities for Discord users. It enables users to summarize long conversations, extract key points from messages, generate meeting notes, and create concise summaries of various types of content with AI-powered analysis and natural language processing.

## Features

### Core Functionality
- **Conversation Summarization**: Summarize Discord conversations and message threads
- **Content Analysis**: Extract key points, themes, and insights from text
- **Meeting Notes**: Generate structured meeting summaries with action items
- **Document Summarization**: Summarize long-form content like articles and documents
- **Multi-language Support**: Process and summarize content in multiple languages
- **Custom Summary Styles**: Various summary formats (bullet points, executive summary, detailed report)

### Key Components
- `Summarizer` class - Main cog implementation
- AI-powered text analysis engine
- Conversation context management
- Multi-format summary generators
- Language detection and processing

## Commands

### `/summarize`
Summarizes provided text or conversation context.

**Parameters**:
- `content` (string, required): Text content to summarize
- `style` (string, optional): Summary style (concise, detailed, bullet_points, executive)
- `length` (string, optional): Summary length (short, medium, long)
- `language` (string, optional): Target language for summary (auto, en, zh, ja)

**Usage Examples**:
```
/summarize content:"[long conversation text]" style:"concise" length:"short"
/summarize content:"[meeting transcript]" style:"executive" length:"medium"
/summarize content:"[document text]" style:"bullet_points" length:"long"
```

**Required Permissions**: None (public access)

### `/summarize_conversation`
Summarizes a Discord conversation or message thread.

**Parameters**:
- `channel_id` (string, optional): Discord channel ID to summarize
- `message_count` (int, optional): Number of recent messages to analyze (10-1000)
- `time_range` (string, optional): Time range (last_hour, last_day, last_week)
- `style` (string, optional): Summary style (summary, highlights, action_items)

**Usage Examples**:
```
/summarize_conversation channel_id:"123456789" message_count:100 style:"highlights"
/summarize_conversation time_range:"last_day" style:"action_items"
/summarize_conversation message_count:500 style:"summary"
```

**Required Permissions**: Read Messages permission in target channel

### `/extract_key_points`
Extracts key points and important information from content.

**Parameters**:
- `content` (string, required): Content to analyze
- `point_type` (string, optional): Type of key points (decisions, questions, topics, facts)
- `max_points` (int, optional): Maximum number of key points to extract (5-50)

**Usage Examples**:
```
/extract_key_points content:"[meeting discussion]" point_type:"decisions" max_points:10
/extract_key_points content:"[technical document]" point_type:"facts" max_points:15
/extract_key_points content:"[Q&A session]" point_type:"questions" max_points:20
```

**Required Permissions**: None (public access)

### `/meeting_summary`
Generates structured meeting summaries with action items and decisions.

**Parameters**:
- `meeting_content` (string, required): Meeting transcript or notes
- `attendees` (string, optional): List of meeting attendees (comma-separated)
- `meeting_date` (string, optional): Meeting date (YYYY-MM-DD)
- `template` (string, optional): Summary template (standard, formal, action_focused)

**Usage Examples**:
```
/meeting_summary meeting_content:"[meeting transcript]" attendees:"John, Jane, Bob" template:"action_focused"
/meeting_summary meeting_content:"[meeting notes]" meeting_date:"2024-12-20" template:"formal"
```

**Required Permissions**: None (public access)

## Technical Implementation

### Class Structure
```python
class Summarizer(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    
    # Command handlers
    async def summarize_command(self, interaction: discord.Interaction,
                               content: str, style: str = "concise", 
                               length: str = "medium", language: str = "auto")
    
    async def summarize_conversation_command(self, interaction: discord.Interaction,
                                           channel_id: str = None, message_count: int = 100,
                                           time_range: str = "last_day", style: str = "summary")
    
    async def extract_key_points_command(self, interaction: discord.Interaction,
                                        content: str, point_type: str = "topics", 
                                        max_points: int = 10)
    
    async def meeting_summary_command(self, interaction: discord.Interaction,
                                     meeting_content: str, attendees: str = None,
                                     meeting_date: str = None, template: str = "standard")
    
    # Core functionality
    async def summarize_text(self, content: str, style: str, length: str, language: str) -> str
    async def summarize_conversation(self, channel_id: str, message_count: int, time_range: str, style: str) -> str
    async def extract_keypoints(self, content: str, point_type: str, max_points: int) -> List[str]
    async def generate_meeting_summary(self, content: str, attendees: List[str], date: str, template: str) -> Dict[str, Any]
```

### Text Analysis Engine
```python
import re
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from nltk.tag import pos_tag

class TextAnalysisEngine:
    def __init__(self):
        # Download required NLTK data
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
        
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords')
        
        try:
            nltk.data.find('taggers/averaged_perceptron_tagger')
        except LookupError:
            nltk.download('averaged_perceptron_tagger')
        
        self.stop_words = set(stopwords.words('english'))

    def extract_key_phrases(self, text: str, max_phrases: int = 10) -> List[Tuple[str, float]]:
        """Extract key phrases using frequency and linguistic analysis"""
        
        # Tokenize and clean text
        sentences = sent_tokenize(text)
        words = word_tokenize(text.lower())
        
        # Remove stop words and short words
        filtered_words = [word for word in words 
                         if word.isalpha() and len(word) > 2 and word not in self.stop_words]
        
        # Calculate word frequencies
        word_freq = Counter(filtered_words)
        
        # Extract noun phrases (simple approach)
        pos_tags = pos_tag(filtered_words)
        noun_phrases = []
        
        current_phrase = []
        for word, tag in pos_tags:
            if tag.startswith('NN'):  # Noun tags
                current_phrase.append(word)
            else:
                if current_phrase:
                    phrase = ' '.join(current_phrase)
                    noun_phrases.append(phrase)
                    current_phrase = []
        
        # Add final phrase if exists
        if current_phrase:
            noun_phrases.append(' '.join(current_phrase))
        
        # Score phrases
        phrase_scores = {}
        for phrase in noun_phrases:
            phrase_words = phrase.split()
            score = sum(word_freq.get(word, 0) for word in phrase_words)
            phrase_scores[phrase] = score
        
        # Sort by score and return top phrases
        sorted_phrases = sorted(phrase_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_phrases[:max_phrases]

    def identify_decisions(self, text: str) -> List[Dict[str, Any]]:
        """Identify decisions made in the text"""
        
        decisions = []
        sentences = sent_tokenize(text)
        
        decision_patterns = [
            r'\b(decided?|decision|agreed?|agreement|resolved?|solution|chose|choose|select|approve|approved?)\b',
            r'\b(will|shall|going to|plan to|intend to)\b',
            r'\b(action|task|assignment|responsibility)\b'
        ]
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            # Check for decision patterns
            for pattern in decision_patterns:
                if re.search(pattern, sentence_lower):
                    # Extract context around the decision
                    context_start = max(0, sentences.index(sentence) - 1)
                    context_end = min(len(sentences), sentences.index(sentence) + 2)
                    context = ' '.join(sentences[context_start:context_end])
                    
                    decisions.append({
                        'sentence': sentence,
                        'context': context,
                        'confidence': self._calculate_confidence(sentence, pattern)
                    })
                    break
        
        return decisions

    def identify_questions(self, text: str) -> List[str]:
        """Extract questions from the text"""
        
        questions = []
        sentences = sent_tokenize(text)
        
        question_patterns = [
            r'\?',
            r'\b(what|when|where|who|why|how|which|whose)\b.*\?',
            r'\b(can|could|should|would|may|might)\b.*\?'
        ]
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            
            # Check for question patterns
            for pattern in question_patterns:
                if re.search(pattern, sentence_lower):
                    questions.append(sentence.strip())
                    break
        
        return questions

    def _calculate_confidence(self, sentence: str, pattern: str) -> float:
        """Calculate confidence score for pattern match"""
        
        match = re.search(pattern, sentence.lower())
        if not match:
            return 0.0
        
        # Base confidence on pattern specificity
        if 'decided' in pattern or 'agreed' in pattern:
            return 0.9
        elif 'will' in pattern or 'shall' in pattern:
            return 0.7
        else:
            return 0.5

    def detect_language(self, text: str) -> str:
        """Simple language detection based on common words"""
        
        languages = {
            'en': ['the', 'and', 'is', 'are', 'was', 'were', 'this', 'that'],
            'zh': ['的', '了', '在', '是', '我', '你', '他', '她'],
            'ja': ['の', 'は', 'が', 'を', 'に', 'で', 'と', 'も'],
            'es': ['el', 'la', 'de', 'que', 'y', 'en', 'un', 'es'],
            'fr': ['le', 'la', 'de', 'et', 'un', 'une', 'des', 'du']
        }
        
        text_lower = text.lower()
        language_scores = {}
        
        for lang, indicators in languages.items():
            score = sum(1 for word in indicators if word in text_lower)
            language_scores[lang] = score
        
        # Return language with highest score
        return max(language_scores, key=language_scores.get)
```

### Conversation Context Management
```python
import discord
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

class ConversationContext:
    def __init__(self, bot):
        self.bot = bot
        self.max_messages = 1000
        self.context_window = 100  # Number of messages to keep in context
    
    async def get_conversation_content(self, channel_id: str, message_count: int = 100, 
                                      time_range: str = "last_day") -> str:
        """Retrieve and format conversation content"""
        
        try:
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                return "Channel not found or bot lacks access."
            
            # Calculate time filter
            time_filter = self._calculate_time_filter(time_range)
            
            # Fetch messages
            messages = []
            async for message in channel.history(limit=message_count, after=time_filter):
                if not message.author.bot:  # Exclude bot messages
                    messages.append({
                        'author': message.author.display_name,
                        'content': message.content,
                        'timestamp': message.created_at,
                        'attachments': [att.filename for att in message.attachments]
                    })
            
            # Sort by timestamp (oldest first)
            messages.sort(key=lambda x: x['timestamp'])
            
            # Format conversation
            return self._format_conversation(messages)
            
        except Exception as e:
            await func.report_error(e, "get_conversation_content")
            return "Error retrieving conversation content."
    
    def _calculate_time_filter(self, time_range: str) -> Optional[datetime]:
        """Calculate datetime filter based on time range"""
        
        now = datetime.now()
        
        if time_range == "last_hour":
            return now - timedelta(hours=1)
        elif time_range == "last_day":
            return now - timedelta(days=1)
        elif time_range == "last_week":
            return now - timedelta(weeks=1)
        elif time_range == "last_month":
            return now - timedelta(days=30)
        else:
            return None
    
    def _format_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages into readable conversation text"""
        
        formatted_parts = []
        
        for msg in messages:
            timestamp = msg['timestamp'].strftime("%Y-%m-%d %H:%M")
            
            # Format message
            message_text = f"[{timestamp}] {msg['author']}: {msg['content']}"
            
            # Add attachment info
            if msg['attachments']:
                attachments = ", ".join(msg['attachments'])
                message_text += f" [Attachments: {attachments}]"
            
            formatted_parts.append(message_text)
        
        return '\n'.join(formatted_parts)
```

## Error Handling

### Summarization Error Management
```python
async def handle_summarization_error(self, interaction, error, context: str, content_length: int = 0):
    """Handle summarization errors with user-friendly messages"""
    
    error_messages = {
        "content_too_short": "Content is too short to generate a meaningful summary. Please provide more text.",
        "content_too_long": "Content is too long for summarization. Please provide shorter content or use conversation summarization.",
        "no_content": "No content provided for summarization.",
        "channel_access_denied": "Unable to access the specified channel. Please check permissions.",
        "api_error": "Summarization service is temporarily unavailable. Please try again later.",
        "language_not_supported": "Content language is not supported for summarization.",
        "invalid_parameters": "Invalid parameters provided for summarization.",
        "rate_limit_exceeded": "Summarization rate limit exceeded. Please wait before trying again."
    }
    
    # Determine error type and provide appropriate message
    error_str = str(error).lower()
    
    if content_length < 50:
        message = error_messages["content_too_short"]
    elif content_length > 10000:
        message = error_messages["content_too_long"]
    elif "access denied" in error_str or "permission" in error_str:
        message = error_messages["channel_access_denied"]
    elif "rate limit" in error_str or "quota" in error_str:
        message = error_messages["rate_limit_exceeded"]
    elif "language" in error_str:
        message = error_messages["language_not_supported"]
    elif "api" in error_str or "service" in error_str:
        message = error_messages["api_error"]
    else:
        message = error_messages["invalid_parameters"]
    
    await interaction.response.send_message(message, ephemeral=True)
    await func.report_error(error, f"summarizer_{context}")
```

## Usage Examples

### Basic Text Summarization
```
User: /summarize content:"[long article text]" style:"concise" length:"short"
Bot: ## Summary

This article discusses the impact of artificial intelligence on modern workplace productivity. Key points include:

• AI automation reducing repetitive tasks
• Enhanced decision-making through data analysis  
• New skills required for human-AI collaboration
• Implementation challenges and solutions

**Length:** 89 words (short summary)
```

### Conversation Summarization
```
User: /summarize_conversation channel_id:"123456789" message_count:50 style:"highlights"
Bot: ## Conversation Summary

**Channel:** #general-discussion
**Messages Analyzed:** 50
**Time Span:** 2 hours
**Participants:** 8 users

### Key Highlights:
• **Project Status Update**: Team discussed Q4 progress and upcoming deadlines
• **Resource Allocation**: Decision made to hire 2 additional developers
• **Technical Challenges**: Database migration issues identified
• **Next Steps**: Action items assigned for infrastructure improvements

### Action Items:
• John to finalize database migration plan by Friday
• Jane to coordinate with HR for developer hiring
• Team to review infrastructure requirements by next week
```

### Meeting Summary Generation
```
User: /meeting_summary meeting_content:"[meeting transcript]" attendees:"Alice, Bob, Charlie" template:"action_focused"
Bot: ## Action Items Summary - 2024-12-20

### Meeting Overview:
Meeting resulted in 3 key decisions and 8 action items requiring follow-up.

### Priority Actions (High/Medium):
• **HIGH**: Alice to finalize project timeline by Friday
• **MEDIUM**: Bob to coordinate with stakeholders for budget approval  
• **HIGH**: Charlie to investigate technical requirements

### Decisions Impacting Actions:
• Approved additional budget for Q1 initiatives
• Resolved technical architecture disputes
• Confirmed project delivery timeline

### Responsibility Breakdown:
• **Alice**: Timeline coordination, stakeholder management
• **Bob**: Budget planning, resource allocation
• **Charlie**: Technical research, implementation planning
```

### Key Points Extraction
```
User: /extract_key_points content:"[technical discussion]" point_type:"decisions" max_points:10
Bot: ## Key Decisions Extracted

### Identified Decisions:
1. **Database Migration Strategy**: Adopted incremental migration approach
2. **Team Restructuring**: Confirmed new team lead assignments
3. **Budget Approval**: Approved $50K additional funding for infrastructure
4. **Timeline Adjustment**: Extended deadline by 2 weeks for quality assurance
5. **Technology Stack**: Selected React for frontend development

**Confidence Scores:** Decisions identified with 85% average confidence
```

## Configuration Options

### Bot Settings
```python
# Configuration in addons/settings.py
SUMMARIZER_CONFIG = {
    "max_content_length": 10000,
    "min_content_length": 50,
    "max_conversation_messages": 1000,
    "default_summary_style": "concise",
    "supported_styles": ["concise", "detailed", "bullet_points", "executive"],
    "supported_languages": ["en", "zh", "ja", "es", "fr"],
    "batch_processing": {
        "enabled": True,
        "max_batch_size": 10,
        "rate_limit": 60  # requests per minute
    }
}
```

## Integration Points

### With Other Cogs
```python
# Integration with user data for preferences
from cogs.userdata import UserData

# Integration with language manager for processing
from cogs.language_manager import LanguageManager

# Integration with memory systems for context
from cogs.episodic_memory import EpisodicMemory
```

### External Services
- **Natural Language Processing**: NLTK, spaCy for advanced text analysis
- **AI Services**: OpenAI, Google Cloud Natural Language for enhanced summaries
- **Translation Services**: Google Translate for multi-language support
- **Document Processing**: Libraries for PDF, DOCX content extraction

## Related Files

- `cogs/summarizer.py` - Main implementation
- `translations/en_US/commands/summarizer.json` - English translations
- `LanguageManager` - Translation system
- `addons.settings` - Configuration management

## Future Enhancements

Potential improvements:
- **Advanced AI Integration**: Use large language models for better summaries
- **Real-time Summarization**: Live conversation summarization as it happens
- **Visual Summarization**: Generate charts and graphs from meeting data
- **Sentiment Analysis**: Analyze emotional tone in conversations
- **Topic Modeling**: Automatically identify themes and subjects
- **Collaborative Features**: Share and collaboratively edit summaries
- **Export Options**: Export summaries to various formats (PDF, Word, etc.)
- **Voice Summarization**: Summarize voice messages and audio content
- **Custom Templates**: User-defined summary templates for specific use cases
- **Integration APIs**: API endpoints for external system integration