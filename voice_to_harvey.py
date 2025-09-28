#!/usr/bin/env python3
"""
Voice to Harvey Bridge
Runs the voice assistant from HarveyConversation project and passes the result to Harvey agent.
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

try:
    # Import voice assistant from HarveyConversation
    from voice_assistant import voice_assistant

    print("✅ Successfully imported voice_assistant from HarveyConversation")
except ImportError as e:
    print(f"❌ Failed to import voice_assistant: {e}")
    print("Make sure HarveyConversation project is in the parent directory")
    sys.exit(1)

try:
    # Import Harvey agent
    from harvey import Harvey

    print("✅ Successfully imported Harvey agent")
except ImportError as e:
    print(f"❌ Failed to import Harvey agent: {e}")
    sys.exit(1)


def extract_task_from_conversation(voice_result):
    """
    Extract a clear task from the voice conversation result.

    Args:
        voice_result (dict): Result from voice_assistant function

    Returns:
        str: Formatted task for Harvey agent
    """
    if not voice_result or voice_result.get("status") != "success":
        return "No valid conversation data available"

    # Get action items if available
    action_items = voice_result.get("action_items", [])
    transcript = voice_result.get("transcript", [])

    # If we have action items, use the first one as the main task
    if action_items and len(action_items) > 0:
        main_task = action_items[0]
        print(f"🎯 Using action item as task: {main_task}")
        return main_task

    # Otherwise, extract from the last user message in transcript
    if transcript:
        # Find the last user message
        user_messages = [
            entry for entry in transcript if entry.get("speaker") == "User"
        ]
        if user_messages:
            last_user_message = user_messages[-1]["message"]
            print(f"🎯 Using last user message as task: {last_user_message}")
            return last_user_message

    # Fallback to a generic message
    return "Please help me with a computer task"


def run_voice_to_harvey_pipeline():
    """
    Main pipeline: Voice conversation -> Harvey agent execution
    """
    print("🚀 Starting Voice-to-Harvey Pipeline")
    print("=" * 50)

    # Step 1: Run voice assistant
    print("🎤 Step 1: Starting voice conversation...")
    print("Speak your task clearly when prompted.")
    print("-" * 30)

    try:
        voice_result = voice_assistant(
            record_seconds=10,  # Allow longer recordings
            auto_analyze=True,
            save_transcript=True,
            save_analysis=True,
        )

        print("\n✅ Voice conversation completed!")
        print(f"Status: {voice_result.get('status', 'unknown')}")
        print(f"Transcript entries: {len(voice_result.get('transcript', []))}")

        if voice_result.get("action_items"):
            print(f"Action items found: {len(voice_result['action_items'])}")
            for i, item in enumerate(voice_result["action_items"], 1):
                print(f"  {i}. {item}")

    except Exception as e:
        print(f"❌ Error in voice conversation: {e}")
        return

    # Step 2: Extract task for Harvey
    print("\n🤖 Step 2: Preparing task for Harvey agent...")
    print("-" * 30)

    task = extract_task_from_conversation(voice_result)
    print(f"📋 Task for Harvey: {task}")

    # Step 3: Run Harvey agent
    print("\n🎯 Step 3: Harvey agent execution...")
    print("-" * 30)

    try:
        harvey = Harvey()
        harvey.run(task)
        print("\n✅ Harvey agent completed the task!")

    except Exception as e:
        print(f"❌ Error in Harvey agent: {e}")
        return

    print("\n🎉 Voice-to-Harvey pipeline completed successfully!")
    print("=" * 50)


def main():
    """Main entry point"""
    # Check for required environment variables
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("❌ Please set GOOGLE_API_KEY or GEMINI_API_KEY in your environment")
        print("You can create a .env file with: GOOGLE_API_KEY=your_key_here")
        return

    # Check if we're on macOS (Harvey requires macOS for automation)
    if sys.platform != "darwin":
        print("⚠️  Warning: Harvey agent is designed for macOS automation")
        print(
            "Voice conversation will work, but Harvey automation may not function properly"
        )
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != "y":
            print("Exiting...")
            return

    # Run the pipeline
    run_voice_to_harvey_pipeline()


if __name__ == "__main__":
    main()
