"""
Example script demonstrating the Protected Prompt Management System.

Run this to test the system.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from llm.prompting.protected_prompt_manager import get_protected_prompt_manager


def main():
    print("\n" + "=" * 60)
    print("  PROTECTED PROMPT MANAGEMENT SYSTEM - DEMO")
    print("=" * 60 + "\n")
    
    manager = get_protected_prompt_manager()
    
    # Show module info
    info = manager.get_module_info()
    print("📋 Protected Modules:")
    for module in info['protected_modules']:
        print(f"  🔒 {module}")
    
    print("\n📋 Customizable Modules:")
    for module in info['customizable_modules']:
        print(f"  ✏️  {module}")
    
    # Try to customize a protected module
    print("\n" + "=" * 60)
    print("Attempt ing to customize protected module 'output_format'...")
    result = manager.set_custom_module('output_format', 'CUSTOM')
    print(f"Result: {'✅ Success' if result else '❌ Rejected (as expected)'}")
    
    # Customize an allowed module
    print("\n" + "=" * 60)
    print("Customizing allowed module 'identity'...")
    result = manager.set_custom_module('identity', '## Test Identity')
    print(f"Result: {'✅ Success' if result else '❌ Failed'}")
    
    # Compose prompt
    print("\n" + "=" * 60)
    print("Composing system prompt...")
    prompt = manager.compose_system_prompt()
    print(f"Prompt length: {len(prompt)} characters")
    print(f"First 200 chars:\n{prompt[:200]}...")
    
    print("\n" + "=" * 60)
    print("  ✅ DEMO COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
