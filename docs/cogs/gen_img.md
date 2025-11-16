# GenImg Cog Documentation

## Overview

The GenImg cog provides AI-powered image generation capabilities using Google's Gemini API. It enables users to generate high-quality images from text descriptions through a simple Discord interface with support for multiple languages.

## Features

### Core Functionality
- **Text-to-Image Generation**: Convert text prompts into visual images
- **Multi-language Support**: Full localization for prompt interpretation
- **Discord Integration**: Seamless image sharing and display in Discord channels
- **Error Handling**: Robust error handling with user-friendly messages
- **Image Quality**: High-resolution output suitable for various use cases

### Key Components
- `GenImg` class - Main cog implementation
- Google Gemini API integration
- Image processing and Discord upload handling
- Multi-language prompt processing

## Commands

### `/generate_image`
Generates an image based on a text prompt.

**Parameters**:
- `prompt` (string, required): Description of the image to generate
- `negative_prompt` (string, optional): Description of what to avoid in the image
- `guidance_scale` (float, optional, default: 7.5): Controls how closely the image follows the prompt (2-20)
- `width` (int, optional, default: 1024): Output image width in pixels (512-1024)
- `height` (int, optional, default: 1024): Output image height in pixels (512-1024)

**Usage Examples**:
```
/generate_image prompt:"A sunset over mountains with a lake reflection"
/generate_image prompt:"Modern city skyline" guidance_scale:8.0 width:1024 height:768
```

**Required Permissions**: None (public access)

### `/describe_image`
Analyzes and describes an uploaded image using AI vision capabilities.

**Parameters**:
- `image` (attachment, required): Discord image attachment to analyze

**Usage Examples**:
```
/describe_image image:[upload_image]
```

**Required Permissions**: None (public access)

## Technical Implementation

### Class Structure
```python
class GenImg(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    
    # Command handlers
    async def generate_image_command(self, interaction: discord.Interaction, 
                                     prompt: str, negative_prompt: str = None,
                                     guidance_scale: float = None, 
                                     width: int = None, height: int = None)
    
    async def describe_image_command(self, interaction: discord.Interaction, 
                                    image: discord.Attachment)
```

### Gemini API Integration

#### Image Generation
```python
async def generate_image_command(self, interaction, prompt, negative_prompt=None, 
                                guidance_scale=None, width=None, height=None):
    # Validate parameters
    if width and height and width * height > 1048576:  # 1024*1024
        await interaction.response.send_message(
            "Image size too large. Maximum is 1024x1024 pixels."
        )
        return
    
    try:
        # Prepare generation parameters
        generation_config = {
            "temperature": 0.4,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
        }
        
        # Create generation request
        response = await self.model.generate_content_async(
            contents=[{
                "parts": [
                    {"text": f"Generate an image: {prompt}"}
                ]
            }],
            generation_config=generation_config
        )
        
        # Handle response and upload image
        image_data = response.content.parts[0].inline_data.data
        
    except Exception as e:
        await self.handle_error(interaction, e, "generate_image")
```

## Error Handling

### Comprehensive Error Management
```python
async def handle_error(self, interaction, error, context: str):
    """Handle and report errors with context-specific messages"""
    
    # Report error to logging system
    await func.report_error(error, context)
    
    # Send user-friendly error message
    error_messages = {
        "quota_exceeded": "Image generation quota exceeded. Please try again later.",
        "invalid_prompt": "Invalid prompt. Please check your input and try again.",
        "api_error": "Image generation service is temporarily unavailable.",
        "network_error": "Network error. Please check your connection and try again."
    }
    
    # Determine error type and send appropriate message
    error_type = self.classify_error(error)
    message = error_messages.get(error_type, "An unexpected error occurred.")
    
    await interaction.response.send_message(message, ephemeral=True)

def classify_error(self, error) -> str:
    """Classify error type for user-friendly messaging"""
    error_str = str(error).lower()
    
    if "quota" in error_str or "limit" in error_str:
        return "quota_exceeded"
    elif "prompt" in error_str or "invalid" in error_str:
        return "invalid_prompt"
    elif "api" in error_str or "gemini" in error_str:
        return "api_error"
    else:
        return "network_error"
```

## Usage Examples

### Basic Image Generation
```
User: /generate_image prompt:"A cute cartoon cat wearing a hat"
Bot: [Generates and displays image with embed]
```

### Advanced Generation with Parameters
```
User: /generate_image prompt:"Cyberpunk city at night" negative_prompt:"low quality" guidance_scale:9.0 width:1024 height:768
Bot: [Generates high-quality cyberpunk scene]
```

### Image Analysis
```
User: /describe_image image:[upload]
Bot: "This image shows a beautiful sunset over a calm ocean with seagulls flying in the distance. The sky has a gradient of orange, pink, and purple colors..."
```

## Related Files

- `cogs/gen_img.py` - Main implementation
- `data/generated_images/` - Generated image storage
- `LanguageManager` - Translation system
- `Google Gemini API` - Image generation service
- `addons.tokens` - API key management

## Future Enhancements

Potential improvements:
- Advanced prompt templates
- Image editing capabilities
- Style transfer functionality
- Batch generation processing
- Custom model training
- Advanced image analysis features