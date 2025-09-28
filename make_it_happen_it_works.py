#!/usr/bin/env python3
"""
Voice Action Items to Harvey
Simple script that runs voice_assistant and passes only the action items to Harvey.
"""

import os
import sys
from pathlib import Path

# Add HarveyConversation project to path
harvey_conversation_path = Path(__file__).parent.parent / "HarveyConversation"
sys.path.insert(0, str(harvey_conversation_path))

# Add current Harvey project to path
harvey_project_path = Path(__file__).parent
sys.path.insert(0, str(harvey_project_path))


def main():
    """Run voice assistant and pass action items to Harvey"""
    print("🎤 Running voice assistant to get action items...")

    try:
        # Import and run voice assistant
        from voice_assistant import voice_assistant

        # Run voice conversation
        result = voice_assistant(
            record_seconds=8,
            auto_analyze=True,
            save_transcript=True,
            save_analysis=True,
        )

        print(f"\n✅ Voice conversation completed")

        # Get action items
        action_items = result.get("action_items", [])

        if not action_items:
            print("❌ No action items found in conversation")
            return

        print(f"🎯 Found {len(action_items)} action items:")
        for i, item in enumerate(action_items, 1):
            print(f"  {i}. {item}")

        # Combine all action items into one prompt for Harvey
        task = "Please complete the following tasks: " + "; ".join(action_items)
        print(f"\n🤖 Running Harvey with combined action items: {task}")
        print("-" * 40)

        from harvey import Harvey

        harvey = Harvey()
        harvey.run(task)

        print("\n🎉 Harvey completed the action item!")

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure HarveyConversation project is in the parent directory")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("❌ Please set GOOGLE_API_KEY or GEMINI_API_KEY")
        sys.exit(1)

    main()
