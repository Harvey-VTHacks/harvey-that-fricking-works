#!/usr/bin/env python3
"""
Voice Assistant - Single Exportable Function
A complete voice conversation system with Gemini AI, automatic analysis, and action extraction.
"""

import os
import json
import numpy as np
import sounddevice as sd
import soundfile as sf
from datetime import datetime
from typing import List, Dict, Any, Optional
import tempfile
import wave

# Gemini imports
from google import genai
from google.genai import types

# Import analysis functions
from analyzer import analyze_conversation, display_analysis, save_analysis

# Load environment variables
from dotenv import load_dotenv

load_dotenv()


def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    """Helper function to save PCM audio data as a WAV file."""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def voice_assistant(
    api_key: str = "AIzaSyDEpKgpwdgCem96MNiBJjjK4Dx6ISogHZA",
    voice_name: str = "Charon",
    record_seconds: int = 5,
    auto_analyze: bool = True,
    save_transcript: bool = True,
    save_analysis: bool = True,
) -> Dict[str, Any]:
    """
    Complete voice assistant function that handles everything in one call.

    Args:
        api_key (str): Gemini API key
        voice_name (str): Voice to use ('Charon', 'Puck', 'Kore', etc.)
        record_seconds (int): Maximum recording time per utterance
        auto_analyze (bool): Whether to automatically analyze conversation
        save_transcript (bool): Whether to save conversation transcript
        save_analysis (bool): Whether to save analysis results

    Returns:
        Dict containing:
        - transcript: List of conversation messages
        - transcript_file: Path to saved transcript (if saved)
        - analysis: Analysis results (if analyzed)
        - action_items: Extracted action items (if analyzed)
        - status: Success/failure status
    """

    result = {
        "transcript": [],
        "transcript_file": None,
        "analysis": None,
        "action_items": None,
        "status": "success",
    }

    try:
        # Initialize Gemini client
        client = genai.Client(api_key=api_key)

        # Audio configuration
        audio_config = {
            "sample_rate": 16000,
            "channels": 1,
            "dtype": np.int16,
            "record_seconds": record_seconds,
        }

        # System prompt for conversational behavior
        system_prompt = """You are a conversational AI assistant focused on understanding user intentions through natural dialogue. When users give you specific, clear instructions about computer tasks, confirm and execute them quickly. Only ask clarifying questions if the request is genuinely vague or ambiguous.

Examples of CLEAR requests that need NO clarification:
- "Open Gmail and check my latest email" → "I'll open Gmail and show you your latest email. [END_CONVERSATION]"
- "Go to Amazon and search for wireless mice under $30" → "I'll take you to Amazon and search for wireless mice under $30. [END_CONVERSATION]"
- "Open my browser and navigate to YouTube" → "I'll open your browser and go to YouTube. [END_CONVERSATION]"

Examples of VAGUE requests that need clarification:
- "I want to buy something" → "What would you like to buy?"
- "Help me with email" → "What would you like to do with your email?"

When the user gives a clear, actionable request, respond with: "I'll [specific action]. [END_CONVERSATION]"

When the user confirms with "yes" or "do it" after clarification, respond positively and say "[END_CONVERSATION]"

Be decisive and helpful, not overly cautious. If someone says "open Gmail inbox and check latest email" that's crystal clear - just do it!"""

        # Conversation transcript
        transcript = []

        def add_to_transcript(speaker: str, message: str) -> None:
            """Add a message to the conversation transcript."""
            timestamp = datetime.now().isoformat()
            transcript.append(
                {"timestamp": timestamp, "speaker": speaker, "message": message}
            )

        def record_audio() -> np.ndarray:
            """Record audio from microphone and return audio data."""
            print("🎤 Listening... (Press Ctrl+C to stop recording)")

            try:
                audio_data = sd.rec(
                    int(audio_config["record_seconds"] * audio_config["sample_rate"]),
                    samplerate=audio_config["sample_rate"],
                    channels=audio_config["channels"],
                    dtype=audio_config["dtype"],
                )
                sd.wait()
                return audio_data.flatten()
            except KeyboardInterrupt:
                print("\n🛑 Recording stopped by user")
                sd.stop()
                return np.array([])

        def speech_to_text_with_gemini(audio_data: np.ndarray) -> str:
            """Convert audio data to text using Gemini's native audio understanding."""
            if len(audio_data) == 0:
                return ""

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                sf.write(temp_file.name, audio_data, audio_config["sample_rate"])
                temp_audio_path = temp_file.name

            try:
                with open(temp_audio_path, "rb") as audio_file:
                    audio_bytes = audio_file.read()

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        "Provide a transcript of this speech. Only return the transcript text, nothing else.",
                        types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                    ],
                )

                os.unlink(temp_audio_path)

                if response.text:
                    transcript_text = response.text.strip()
                    print(f"👤 You said: {transcript_text}")
                    return transcript_text
                else:
                    print(
                        "🤷 Sorry, I couldn't understand what you said. Please try again."
                    )
                    return ""
            except Exception as e:
                print(f"❌ Error in speech recognition: {e}")
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
                return ""

        def text_to_speech(text: str) -> None:
            """Convert text to speech using Gemini's native TTS."""
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-preview-tts",
                    contents=f"Say cheerfully: {text}",
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice_name,
                                )
                            )
                        ),
                    ),
                )

                audio_data = response.candidates[0].content.parts[0].inline_data.data

                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as temp_file:
                    wave_file(temp_file.name, audio_data)
                    temp_audio_path = temp_file.name

                try:
                    audio_array, sample_rate = sf.read(temp_audio_path)
                    sd.play(audio_array, sample_rate)
                    sd.wait()
                except Exception as play_error:
                    print(f"⚠️  Error playing audio: {play_error}")
                    print(f"🔊 Gemini: {text}")
                finally:
                    if os.path.exists(temp_audio_path):
                        os.unlink(temp_audio_path)
            except Exception as e:
                print(f"❌ Error in text-to-speech: {e}")
                print(f"🔊 Gemini: {text}")

        def get_gemini_response(user_input: str) -> str:
            """Get response from Gemini AI with system prompt."""
            try:
                full_prompt = f"{system_prompt}\n\nUser: {user_input}\nAssistant:"
                response = client.models.generate_content(
                    model="gemini-2.5-flash", contents=[full_prompt]
                )
                return response.text
            except Exception as e:
                print(f"❌ Error getting Gemini response: {e}")
                return (
                    "I'm sorry, I encountered an error while processing your request."
                )

        # Main conversation flow
        print("🚀 Voice Assistant with Gemini")
        print("=" * 40)
        print("📋 Instructions:")
        print("- Speak after you see '🎤 Listening...'")
        print("- Wait for Gemini to respond")
        print("- Be specific with your requests for faster results")
        print("- Say 'goodbye', 'exit', 'quit', or 'bye' to end")
        print("- Or press Ctrl+C during recording to stop")
        if auto_analyze:
            print("- Analysis will run automatically when conversation ends")
        print("=" * 40)

        # Gemini's opening greeting
        greeting = "Hello! I'm here to help you with tasks on your computer. What would you like to do today?"
        print(f"🤖 Gemini: {greeting}")
        add_to_transcript("Gemini", greeting)
        text_to_speech(greeting)

        # Main conversation loop
        while True:
            try:
                print("\n" + "-" * 40)

                # Record user input
                audio_data = record_audio()
                user_text = speech_to_text_with_gemini(audio_data)

                if not user_text:
                    continue

                add_to_transcript("User", user_text)

                # Check for exit conditions
                if any(
                    word in user_text.lower()
                    for word in ["goodbye", "exit", "quit", "bye"]
                ):
                    farewell = (
                        "Goodbye! It was great talking with you. Have a wonderful day!"
                    )
                    print(f"🤖 Gemini: {farewell}")
                    add_to_transcript("Gemini", farewell)
                    text_to_speech(farewell)
                    break

                # Get Gemini's response
                print("🤔 Gemini is thinking...")
                gemini_response = get_gemini_response(user_text)

                # Check if conversation should end (task confirmed)
                if "[END_CONVERSATION]" in gemini_response:
                    clean_response = gemini_response.replace(
                        "[END_CONVERSATION]", ""
                    ).strip()
                    print(f"🤖 Gemini: {clean_response}")
                    add_to_transcript("Gemini", clean_response)
                    text_to_speech(clean_response)
                    print(
                        "\n🎯 Task confirmed! Conversation ending for analysis and task execution."
                    )
                    break
                else:
                    print(f"🤖 Gemini: {gemini_response}")
                    add_to_transcript("Gemini", gemini_response)
                    text_to_speech(gemini_response)

            except KeyboardInterrupt:
                print("\n\n👋 Conversation ended by user.")
                break
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                result["status"] = "error"
                result["error"] = str(e)
                break

        # Save transcript
        result["transcript"] = transcript

        if save_transcript and transcript:
            print("\n" + "=" * 50)
            print("💾 SAVING TRANSCRIPT...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_transcript_{timestamp}.json"

            try:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(transcript, f, indent=2, ensure_ascii=False)
                print(f"💾 Conversation transcript saved to: {filename}")
                result["transcript_file"] = filename
            except Exception as e:
                print(f"❌ Error saving transcript: {e}")

        # Analyze conversation
        if auto_analyze and transcript and len(transcript) > 1:
            print("\n🔍 ANALYZING CONVERSATION...")

            # Extract conversation text
            conversation_text = "\n".join(
                [f"{entry['speaker']}: {entry['message']}" for entry in transcript]
            )
            word_count = len(conversation_text.split())
            print(
                f"📊 Analyzing conversation with {word_count} words and {len(transcript)} exchanges..."
            )

            try:
                analysis = analyze_conversation(conversation_text)
                if analysis:
                    print("\n🎯 ACTION ITEMS EXTRACTED:")
                    display_analysis(analysis)
                    result["analysis"] = analysis
                    result["action_items"] = analysis.get("action_items", [])

                    # Save analysis if requested
                    if save_analysis and result["transcript_file"]:
                        try:
                            save_analysis(analysis, result["transcript_file"])
                        except Exception as e:
                            print(f"⚠️  Error saving analysis: {e}")
                else:
                    print("❌ Failed to extract action items")
            except Exception as e:
                print(f"❌ Error during analysis: {e}")

        print("\n🎉 Voice Assistant session completed!")
        return result

    except Exception as e:
        print(f"❌ Error in voice assistant: {e}")
        result["status"] = "error"
        result["error"] = str(e)
        return result


# Example usage
if __name__ == "__main__":
    # Simple usage
    result = voice_assistant()

    # Advanced usage with custom parameters
    # result = voice_assistant(
    #     api_key="your_api_key_here",
    #     voice_name="Puck",
    #     record_seconds=7,
    #     auto_analyze=True,
    #     save_transcript=True,
    #     save_analysis=True
    # )

    print(f"\n📊 Session Results:")
    print(f"Status: {result['status']}")
    print(f"Transcript entries: {len(result['transcript'])}")
    if result["transcript_file"]:
        print(f"Transcript saved: {result['transcript_file']}")
    if result["action_items"]:
        print(f"Action items found: {len(result['action_items'])}")
        for i, item in enumerate(result["action_items"], 1):
            print(f"  {i}. {item}")
