#!/usr/bin/env python3

import os
import sys
import time
import subprocess
import math
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent.screenshot import capture_to_bytes
from agent.llm import get_gemini_client

# Optional TTS support for spoken rationales
_TTS_AVAILABLE = True
try:
    # Import the speak helper from TTS_STT
    from TTS_STT.speak import speak as tts_speak
except Exception:
    _TTS_AVAILABLE = False

try:
    from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGHIDEventTap, kCGEventLeftMouseDown, kCGEventLeftMouseUp, CGEventCreateKeyboardEvent, kCGEventKeyDown, kCGEventKeyUp, CGEventSetFlags, kCGEventFlagMaskCommand, kCGEventMouseMoved
    from Quartz.CoreGraphics import CGMainDisplayID, CGDisplayBounds, CGEventCreate, CGEventGetLocation, CGContextRef, CGColorSpaceCreateDeviceRGB, CGContextSetRGBStrokeColor, CGContextStrokePath, CGContextMoveToPoint, CGContextAddLineToPoint, CGContextSetLineWidth
    from Quartz import CGWindowListCreateImage, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    import Quartz.CoreGraphics as CG
    _QUARTZ_AVAILABLE = True
except ImportError:
    _QUARTZ_AVAILABLE = False

# Mouse trail configuration
_MOUSE_TRAIL_ENABLED = os.getenv("HARVEY_MOUSE_TRAIL", "1") in ("1", "true", "True")
_TRAIL_POINTS = []  # Store recent mouse positions
_MAX_TRAIL_POINTS = 15  # Maximum trail points to keep
_TRAIL_FADE_SPEED = 0.8  # How quickly trail points fade

def get_screen_info():
    """Get screen size in points and pixels to determine the exact scaling factor."""
    if _QUARTZ_AVAILABLE:
        from Quartz.CoreGraphics import (
            CGMainDisplayID,
            CGDisplayBounds,
            CGDisplayCopyDisplayMode,
            CGDisplayModeGetPixelWidth,
            CGDisplayModeGetPixelHeight,
        )

        display_id = CGMainDisplayID()

        # Logical dimensions (points)
        bounds = CGDisplayBounds(display_id)
        logical_width = int(bounds.size.width)
        logical_height = int(bounds.size.height)

        # Physical dimensions (pixels)
        mode = CGDisplayCopyDisplayMode(display_id)
        pixel_width = int(CGDisplayModeGetPixelWidth(mode)) if mode else logical_width
        pixel_height = int(CGDisplayModeGetPixelHeight(mode)) if mode else logical_height

        # Precise scale factor (e.g., 2.0 on Retina)
        scale = (pixel_width / logical_width) if logical_width else 1.0

        # Return logical size for event coordinates, plus scale for diagnostics
        return logical_width, logical_height, scale
    # Fallback for non-macOS systems
    return 1920, 1080, 1.0

def get_screen_size():
    """Get screen size (for backward compatibility)."""
    width, height, _ = get_screen_info()
    return width, height

def _transform_coords(x_ratio, y_ratio):
    """Transform ratios (top-left origin) to Quartz screen coordinates (top-left origin)."""
    width, height, scale = get_screen_info()

    # Clamp ratios
    x_ratio = max(0.0, min(1.0, float(x_ratio)))
    y_ratio = max(0.0, min(1.0, float(y_ratio)))

    # Convert to points (no Y flip; CGEvent global coords use top-left origin)
    x = int(round(x_ratio * (width - 1)))
    y = int(round(y_ratio * (height - 1)))

    print(f"🎯 Ratio ({x_ratio:.3f}, {y_ratio:.3f}) -> Screen ({x}, {y}) [Points: {width}x{height}, Scale: {scale:.1f}x]")
    return x, y

def _add_trail_point(x, y):
    """Add a point to the mouse trail."""
    global _TRAIL_POINTS
    if not _MOUSE_TRAIL_ENABLED or not _QUARTZ_AVAILABLE:
        return
    
    # Add new point with full opacity
    _TRAIL_POINTS.append({'x': x, 'y': y, 'opacity': 1.0, 'size': 8})
    
    # Remove old points and fade existing ones
    _TRAIL_POINTS = [p for p in _TRAIL_POINTS if p['opacity'] > 0.1]
    if len(_TRAIL_POINTS) > _MAX_TRAIL_POINTS:
        _TRAIL_POINTS = _TRAIL_POINTS[-_MAX_TRAIL_POINTS:]
    
    # Fade existing points
    for point in _TRAIL_POINTS[:-1]:  # Don't fade the newest point
        point['opacity'] *= _TRAIL_FADE_SPEED
        point['size'] *= 0.95

def _draw_trail_overlay():
    """Draw the mouse trail overlay on screen using a simple visual method."""
    if not _MOUSE_TRAIL_ENABLED or not _QUARTZ_AVAILABLE or not _TRAIL_POINTS:
        return
    
    try:
        # Use AppleScript to create a simple visual indicator
        # This is a lightweight approach that doesn't require complex graphics context
        script = f'''
        tell application "System Events"
            -- Create a brief visual flash at the current mouse position
            set mousePos to (current application's NSEvent's mouseLocation() as record)
        end tell
        '''
        
        # For now, we'll use a simpler approach - just add visual feedback via terminal
        if len(_TRAIL_POINTS) > 1:
            latest = _TRAIL_POINTS[-1]
            print(f"🐭 Trail: ({latest['x']}, {latest['y']}) [{len(_TRAIL_POINTS)} points]")
    except Exception as e:
        # Trail drawing is optional, don't break automation if it fails
        pass

def get_current_mouse_position():
    if _QUARTZ_AVAILABLE:
        event = CGEventCreate(None)
        pos = CGEventGetLocation(event)
        x, y = int(pos.x), int(pos.y)
        _add_trail_point(x, y)
        return x, y
    return 100, 100

def smooth_move_mouse(start_x, start_y, end_x, end_y):
    if not _QUARTZ_AVAILABLE:
        return
    distance = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
    if distance < 5:
        return
    steps = max(10, int(distance / 15))
    
    print(f"🐭 Moving mouse from ({start_x}, {start_y}) to ({end_x}, {end_y}) in {steps} steps")
    
    for i in range(steps + 1):
        t = i / steps
        t_smooth = t * t * (3 - 2 * t)

        control_x = (start_x + end_x) / 2 + (end_y - start_y) * 0.1
        control_y = (start_y + end_y) / 2 - (end_x - start_x) * 0.1

        x = int((1 - t_smooth) ** 2 * start_x + 2 * (1 - t_smooth) * t_smooth * control_x + t_smooth ** 2 * end_x)
        y = int((1 - t_smooth) ** 2 * start_y + 2 * (1 - t_smooth) * t_smooth * control_y + t_smooth ** 2 * end_y)

        # Add trail point for this movement
        _add_trail_point(x, y)
        
        event = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (x, y), 0)
        CGEventPost(kCGHIDEventTap, event)
        time.sleep(0.01)
    
    # Draw trail overlay after movement
    _draw_trail_overlay()

def move_mouse(x_ratio, y_ratio):
    if not _QUARTZ_AVAILABLE:
        return
    x, y = _transform_coords(x_ratio, y_ratio)
    current_x, current_y = get_current_mouse_position()
    smooth_move_mouse(current_x, current_y, x, y)

def _is_spotlight_active():
    try:
        result = subprocess.run(['osascript', '-e', 'tell application "System Events" to get name of first process whose frontmost is true'], 
                              capture_output=True, text=True, check=True)
        frontmost = result.stdout.strip()
        return frontmost == "Spotlight" or "Spotlight" in frontmost
    except:
        return False

def _handle_spotlight_click(x_ratio, y_ratio):
    print("🔍 Spotlight: Using Enter to select first result (simplest path)")
    hotkey("return")

def calibrate_click_position(x, y):
    """Apply optional calibration offsets via HARVEY_X_OFFSET and HARVEY_Y_OFFSET (points)."""
    try:
        offset_x = float(os.getenv("HARVEY_X_OFFSET", "0"))
        offset_y = float(os.getenv("HARVEY_Y_OFFSET", "0"))
    except Exception:
        offset_x, offset_y = 0.0, 0.0
    return int(x + offset_x), int(y + offset_y)

def _write_env_offsets(offset_x: int, offset_y: int) -> bool:
    """Create or update .env with HARVEY_X_OFFSET/Y_OFFSET values."""
    try:
        env_path = Path(".env")
        lines = []
        if env_path.exists():
            lines = env_path.read_text().splitlines()

        def set_or_replace(lines, key, value):
            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={value}")
            return lines

        lines = set_or_replace(lines, "HARVEY_X_OFFSET", str(int(offset_x)))
        lines = set_or_replace(lines, "HARVEY_Y_OFFSET", str(int(offset_y)))

        # Ensure trailing newline
        env_path.write_text("\n".join(lines) + "\n")
        return True
    except Exception as e:
        print(f"❌ Could not write .env: {e}")
        return False

def clear_mouse_trail():
    """Clear the mouse trail."""
    global _TRAIL_POINTS
    _TRAIL_POINTS = []
    print("🐭 Mouse trail cleared")

def calibrate_interactive():
    """Interactive calibration: align to visual center and record offsets."""
    if not _QUARTZ_AVAILABLE:
        print("❌ Calibration requires macOS Quartz events.")
        return

    print("🧭 Calibration mode\n- We'll move the cursor to the computed screen center.\n- If it's not visually centered, manually move the cursor to the true center, then press Enter.\n- We'll compute offsets and optionally save them to .env.")

    # Move to computed center
    expected_x, expected_y = _transform_coords(0.5, 0.5)
    cur_x, cur_y = get_current_mouse_position()
    smooth_move_mouse(cur_x, cur_y, expected_x, expected_y)
    print(f"🎯 Moved to computed center at ({expected_x}, {expected_y}).")

    resp = input("Is the cursor exactly at the screen center? [y/N]: ").strip().lower()
    if resp == "y":
        print("✅ No offsets needed. If you previously set HARVEY_X_OFFSET/Y_OFFSET, you may remove them from .env.")
        return

    input("👉 Manually move the cursor to the true visual center, then press Enter to capture...")
    final_x, final_y = get_current_mouse_position()
    off_x = int(final_x - expected_x)
    off_y = int(final_y - expected_y)

    print(f"📐 Computed offsets: HARVEY_X_OFFSET={off_x}, HARVEY_Y_OFFSET={off_y}")

    # Preview: apply offsets and re-center
    preview_x = expected_x + off_x
    preview_y = expected_y + off_y
    cur_x, cur_y = get_current_mouse_position()
    smooth_move_mouse(cur_x, cur_y, preview_x, preview_y)
    print(f"👀 Preview applied at ({preview_x}, {preview_y}).")
    confirm = input("Does this look perfectly centered now? Save to .env? [y/N]: ").strip().lower()
    if confirm == "y":
        if _write_env_offsets(off_x, off_y):
            print("💾 Saved to .env. These offsets will be applied on the next run (dotenv loads on startup).")
        else:
            print("⚠️ Failed to write .env. Set these manually or rerun calibration.")
    else:
        print("📝 Offsets not saved. Re-run calibration if needed.")

def ultra_precise_click(x_ratio, y_ratio):
    """Ultra-precise click with position verification and calibration."""
    if not _QUARTZ_AVAILABLE:
        x, y = _transform_coords(x_ratio, y_ratio)
        print(f"🖱️ Click at ({x}, {y}) (simulated)")
        return
    
    if _is_spotlight_active():
        print("🔍 Spotlight active - using Enter instead of clicking")
        hotkey("return")
        return
    
    # Transform and calibrate coordinates
    x, y = _transform_coords(x_ratio, y_ratio)
    x, y = calibrate_click_position(x, y)
    
    print(f"🎯 Ultra-precise clicking at ({x}, {y})")
    
    # Move to position with higher precision
    current_x, current_y = get_current_mouse_position()
    smooth_move_mouse(current_x, current_y, x, y)
    time.sleep(0.15)  # Slightly longer pause for precision
    
    # Verify we're at the right position and DON'T move again if close enough
    final_x, final_y = get_current_mouse_position()
    if abs(final_x - x) > 5 or abs(final_y - y) > 5:  # Increased tolerance
        print(f"⚠️  Position drift detected: expected ({x}, {y}), got ({final_x}, {final_y})")
        # Only correct if drift is significant
        smooth_move_mouse(final_x, final_y, x, y)
        time.sleep(0.05)  # Shorter wait
    
    # Get final position for click event
    click_x, click_y = get_current_mouse_position()
    
    # Perform the click with error handling
    try:
        down_event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, (click_x, click_y), 0)
        up_event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, (click_x, click_y), 0)
        
        CGEventPost(kCGHIDEventTap, down_event)
        time.sleep(0.05)
        CGEventPost(kCGHIDEventTap, up_event)
        
        print(f"✅ Ultra-precise click completed at ({click_x}, {click_y})")
    except Exception as e:
        print(f"❌ Click failed: {e}")

def precise_click(x_ratio, y_ratio):
    """Main precise click function - uses ultra-precise system."""
    ultra_precise_click(x_ratio, y_ratio)

def left_click(x_ratio, y_ratio):
    """Main click function - uses ultra-precise clicking system."""
    ultra_precise_click(x_ratio, y_ratio)

def double_click(x_ratio, y_ratio):
    """Perform an ultra-precise double-click."""
    if not _QUARTZ_AVAILABLE:
        x, y = _transform_coords(x_ratio, y_ratio)
        print(f"🖱️ Double-click at ({x}, {y}) (simulated)")
        return
    
    # Transform and calibrate coordinates
    x, y = _transform_coords(x_ratio, y_ratio)
    x, y = calibrate_click_position(x, y)
    
    print(f"⚡ Ultra-precise double-clicking at ({x}, {y})")
    
    # Move to position with precision
    current_x, current_y = get_current_mouse_position()
    smooth_move_mouse(current_x, current_y, x, y)
    time.sleep(0.2)
    
    # Verify position
    final_x, final_y = get_current_mouse_position()
    if abs(final_x - x) > 2 or abs(final_y - y) > 2:
        print(f"⚠️  Position correction for double-click")
        smooth_move_mouse(final_x, final_y, x, y)
        time.sleep(0.1)
    
    # Perform double-click
    try:
        for _ in range(2):
            down_event = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, (x, y), 0)
            up_event = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, (x, y), 0)
            CGEventPost(kCGHIDEventTap, down_event)
            time.sleep(0.05)
            CGEventPost(kCGHIDEventTap, up_event)
            time.sleep(0.1)  # Brief pause between clicks
        print(f"⚡ Ultra-precise double-click completed at ({x}, {y})")
    except Exception as e:
        print(f"❌ Double-click failed: {e}")

def hover(x_ratio, y_ratio):
    """Move mouse to position and hover (for tooltips, menus, etc.)."""
    if not _QUARTZ_AVAILABLE:
        x, y = _transform_coords(x_ratio, y_ratio)
        print(f"👆 Hover at ({x}, {y}) (simulated)")
        return
    
    x, y = _transform_coords(x_ratio, y_ratio)
    print(f"👆 Hovering at ({x}, {y})")
    
    current_x, current_y = get_current_mouse_position()
    smooth_move_mouse(current_x, current_y, x, y)
    time.sleep(0.5)  # Hold position for hover effects
    print(f"✅ Hover completed at ({x}, {y})")

def type_text(text):
    if not _QUARTZ_AVAILABLE:
        print(f"⌨️ Typed: {text} (simulated)")
        return
        
    print(f"⌨️ Typing: {text}")
    
    key_map = {
        ' ': 49, 'a': 0, 'b': 11, 'c': 8, 'd': 2, 'e': 14, 'f': 3, 'g': 5, 'h': 4, 'i': 34, 'j': 38,
        'k': 40, 'l': 37, 'm': 46, 'n': 45, 'o': 31, 'p': 35, 'q': 12, 'r': 15, 's': 1,
        't': 17, 'u': 32, 'v': 9, 'w': 13, 'x': 7, 'y': 16, 'z': 6,
        '1': 18, '2': 19, '3': 20, '4': 21, '5': 23, '6': 22, '7': 26, '8': 28, '9': 25, '0': 29,
        '.': 47, '/': 44, '-': 27, '=': 24, ',': 43, '(': None, ')': None, '+': None, ';': 41,
        "'": 39, '[': 33, ']': 30, '\\': 42, '`': 50
    }
    
    for char in text:
        char_lower = char.lower()
        if char_lower in key_map:
            key_code = key_map[char_lower]
            
            # Skip characters that can't be typed directly
            if key_code is None:
                print(f"⌨️ Skipping unsupported character '{char}'")
                continue
            
            try:
                down = CGEventCreateKeyboardEvent(None, key_code, True)
                up = CGEventCreateKeyboardEvent(None, key_code, False)
                
                # Only apply shift for actual uppercase letters, not for typing in general
                if char.isupper() and char.isalpha():
                    CGEventSetFlags(down, 131072)  # shift flag only for caps
                    CGEventSetFlags(up, 0)  # clear flags on release
                else:
                    CGEventSetFlags(down, 0)  # no flags for lowercase
                    CGEventSetFlags(up, 0)
                    
                CGEventPost(kCGHIDEventTap, down)
                time.sleep(0.02)
                CGEventPost(kCGHIDEventTap, up)
                time.sleep(0.03)
            except Exception as e:
                print(f"⌨️ Error typing '{char}': {e}")
        else:
            print(f"⌨️ Character '{char}' not mapped")
        time.sleep(0.02)

def scroll(direction, clicks=5):
    """Scroll the mouse wheel up, down, left, or right using a true scroll event."""
    if not _QUARTZ_AVAILABLE:
        print(f"📜 Scrolled {direction} (simulated)")
        return
        
    from Quartz import CGEventCreateScrollWheelEvent, kCGScrollEventUnitLine

    scroll_direction = { "down": (clicks, 0), "up": (-clicks, 0), "right": (0, clicks), "left": (0, -clicks) }
    
    if direction.lower() not in scroll_direction:
        print(f"❌ Invalid scroll direction: {direction}")
        return

    vertical, horizontal = scroll_direction[direction.lower()]
    print(f"📜 Scrolling {direction}...")
    try:
        scroll_event = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 2, vertical, horizontal)
        CGEventPost(kCGHIDEventTap, scroll_event)
        print(f"✅ Scrolled {direction}")
    except Exception as e:
        print(f"❌ Scroll failed: {e}")

def hotkey(key_combo):
    if not _QUARTZ_AVAILABLE:
        print(f"🔥 Hotkey: {key_combo} (simulated)")
        return
        
    key_codes = {
        'space': 49, 'return': 36, 'enter': 36, 'tab': 48,
        'a': 0, 'b': 11, 'c': 8, 'd': 2, 'e': 14, 'f': 3, 'g': 5, 'h': 4, 'i': 34, 'j': 38,
        'k': 40, 'l': 37, 'm': 46, 'n': 45, 'o': 31, 'p': 35, 'q': 12, 'r': 15, 's': 1,
        't': 17, 'u': 32, 'v': 9, 'w': 13, 'x': 7, 'y': 16, 'z': 6,
        '1': 18, '2': 19, '3': 20, '4': 21, '5': 23, '6': 22, '7': 26, '8': 28, '9': 25, '0': 29
    }
    
    try:
        if "+" in key_combo:
            parts = key_combo.split("+")
            modifiers = parts[:-1]
            key = parts[-1].lower()
            
            if key in key_codes:
                key_code = key_codes[key]
                
                down = CGEventCreateKeyboardEvent(None, key_code, True)
                up = CGEventCreateKeyboardEvent(None, key_code, False)
                
                flags = 0
                if "cmd" in modifiers or "command" in modifiers:
                    flags |= kCGEventFlagMaskCommand
                if "shift" in modifiers:
                    flags |= 131072  # shift flag
                if "alt" in modifiers or "option" in modifiers:
                    flags |= 524288  # option flag
                if "ctrl" in modifiers or "control" in modifiers:
                    flags |= 262144  # control flag
                
                if flags:
                    CGEventSetFlags(down, flags)
                    CGEventSetFlags(up, 0)  # Clear flags on key release
                
                CGEventPost(kCGHIDEventTap, down)
                time.sleep(0.02)
                CGEventPost(kCGHIDEventTap, up)
                print(f"🔥 Hotkey: {key_combo}")
            else:
                print(f"🔥 Hotkey: {key_combo} (key not mapped)")
        elif key_combo.lower() in key_codes:
            key_code = key_codes[key_combo.lower()]
            down = CGEventCreateKeyboardEvent(None, key_code, True)
            up = CGEventCreateKeyboardEvent(None, key_code, False)
            CGEventPost(kCGHIDEventTap, down)
            time.sleep(0.02)
            CGEventPost(kCGHIDEventTap, up)
            print(f"🔥 Hotkey: {key_combo}")
        else:
            print(f"🔥 Hotkey: {key_combo} (not implemented)")
    except Exception as e:
        print(f"❌ Hotkey failed: {e}")

class Harvey:
    def __init__(self):
        self.client = get_gemini_client()
        self.model = "gemini-flash-latest"
        self.last_see = ""
        self.bulk_typing_mode = False
        self.pending_text = []
        self.last_environment = ""
        
    def think(self, task, screenshot_data):
        prompt = f"""You are Harvey, an intelligent macOS assistant. Your job is to break down a user's task into logical steps and choose the best tool for each step.

TASK: {task}

---
## Tool Hierarchy: High-Level First

You have two types of tools: high-level workflows and low-level actions.
**ALWAYS prefer a high-level tool if it perfectly matches the user's goal.** Only use low-level actions for tasks that the high-level tools can't handle.

---
## High-Level Tools (Your Preferred Tools)

-   `open_app("App Name")`: Use this to open any application (e.g., "System Settings", "Notes", "Safari"). This is the ONLY reliable way to open apps.
-   `web_search("Search Term")`: Use this to perform a web search. This tool automatically handles opening Safari, making a new tab, typing, and searching.

## Low-Level Tools (For Custom Actions)

-   `left_click(ratio_x, ratio_y)`: To click buttons, links, etc.
-   `type_text("text to type")`: To type inside an already-focused text field.
-   `hotkey("modifier+key")`: For shortcuts like "cmd+w" to close a window.
-   `scroll("direction")`: To scroll the active window.
-   `done()`: When the entire task is complete.

---
## Your Logic: See -> Think -> Act

1.  **See:** Describe the screen.
2.  **Think:** Analyze the user's overall goal. Determine the very next sub-task. Choose the best tool (`open_app`, `web_search`, `left_click`, etc.) for that specific sub-task.
3.  **Action:** State the single command to execute.

---
## Example Plan

**TASK:** "open system settings using spot light and then move mouse to search bar to search for large text"

**Correct Thought Process:**
1.  **See:** Desktop.
2.  **Think:** The first sub-task is to open "System Settings". The high-level tool `open_app` is perfect for this.
3.  **Action:** `open_app("System Settings")`

*(After that action runs, the code will take a new screenshot showing System Settings is open)*

4.  **See:** System Settings window is open.
5.  **Think:** The first part of the task is done. The next sub-task is to move the mouse to the search bar. This is a custom action, so I need a low-level tool. I see the search bar at the top of the window. I will use `left_click` to focus it.
6.  **Action:** `left_click(0.45, 0.12)`

---
## Your Response Format

See: [description of screen]
Think: [your reasoning and tool choice]
Action: [command]"""

        try:
            from google.genai import types
            
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(
                            data=base64.b64decode(screenshot_data),
                            mime_type="image/jpeg"
                        ),
                    ],
                ),
            ]
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
            )
            
            response_text = response.text.strip()
            
            # Parse the response to extract observation, thinking, and action
            lines = response_text.split('\n')
            see_line = ""
            think_line = ""
            action = ""
            
            for line in lines:
                line = line.strip()
                if line.startswith("See:"):
                    see_line = line[4:].strip()
                elif line.startswith("Think:"):
                    think_line = line[6:].strip()
                elif line.startswith("Action:"):
                    action = line[7:].strip()
                    break  # Stop after finding action to avoid parsing extra text
                elif line.startswith("**See:**"):
                    see_line = line[8:].strip()
                elif line.startswith("**Think:**"):
                    think_line = line[9:].strip()
                elif line.startswith("**Action:**"):
                    action = line[11:].strip()
                    break
                elif not see_line and not think_line and not action and line and not line.startswith("**"):
                    # Fallback - treat as action if it looks like a command
                    if any(cmd in line for cmd in ["left_click", "type_text", "bulk_type", "hotkey", "done", "wait", "scroll"]):
                        action = line
                        break
            
            # Clean up action - remove any markdown formatting
            if action:
                action = action.replace("`", "").strip()
            
            # Print what Harvey observes and thinks
            if see_line:
                print(f"👁️  Harvey sees: {see_line}")
            if think_line:
                print(f"🧠 Harvey thinks: {think_line}")
            # Remember for rationale speech
            self.last_see = see_line
            
            return action if action else "wait(1000)"  # Default fallback to prevent loops
            
        except Exception as e:
            error_str = str(e)
            print(f"LLM Error: {e}")
            
            # Handle rate limiting
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                print("⏳ Rate limit hit - waiting before retry...")
                import re
                # Extract retry delay if available
                retry_match = re.search(r'Please retry in (\d+\.?\d*)s', error_str)
                if retry_match:
                    delay = float(retry_match.group(1))
                    print(f"⏳ Waiting {delay:.1f} seconds...")
                    time.sleep(delay + 1)  # Add 1 second buffer
                else:
                    time.sleep(10)  # Default 10 second wait
                
                # For browser workflows, provide smart fallback
                if "safari" in task.lower() or "browser" in task.lower():
                    if "search" in task.lower():
                        return 'hotkey("cmd+t")'  # Open new tab for search
                    
            return "done()"
    
    def execute(self, action_text):
        print(f"🤖 Harvey: {action_text}")
        
        try:
            # High-level tool execution
            if action_text.startswith("open_app"):
                app_name = self._extract_text(action_text)
                if app_name:
                    self._open_app_workflow(app_name)
                return False # Task is not done, just a step

            elif action_text.startswith("web_search"):
                search_term = self._extract_text(action_text)
                if search_term:
                    self._web_search_workflow(search_term)
                return False # Task is not done, just a step
            
            # Low-level actions
            elif action_text.startswith("move_mouse"):
                coords = self._extract_coords(action_text)
                if coords:
                    print(f"   → Moving cursor to position")
                    move_mouse(coords[0], coords[1])
                    
            elif action_text.startswith("left_click"):
                coords = self._extract_coords(action_text)
                if coords:
                    print(f"   → Precise clicking to select/activate")
                    left_click(coords[0], coords[1])
                    
            elif action_text.startswith("double_click"):
                coords = self._extract_coords(action_text)
                if coords:
                    print(f"   → Double-clicking to open/activate")
                    double_click(coords[0], coords[1])
                    
            elif action_text.startswith("hover"):
                coords = self._extract_coords(action_text)
                if coords:
                    print(f"   → Hovering to reveal menu/tooltip")
                    hover(coords[0], coords[1])
                    
            elif action_text.startswith("bulk_type"):
                text = self._extract_text(action_text)
                if text:
                    print(f"   → Bulk typing multi-line content")
                    self._bulk_type_text(text)
                    
            elif action_text.startswith("type_text"):
                text = self._extract_text(action_text)
                if text:
                    print(f"   → Typing '{text}' to input text")
                    type_text(text)
                    
            elif action_text.startswith("scroll"):
                direction = self._extract_text(action_text)
                if direction:
                    print(f"   → Scrolling {direction}")
                    scroll(direction)
                    
            elif action_text.startswith("hotkey"):
                key = self._extract_text(action_text)
                if key:
                    if key == "cmd+space":
                        print(f"   → Opening Spotlight search")
                    elif key == "cmd+t":
                        print(f"   → Opening new tab")
                    elif key == "cmd+l":
                        print(f"   → Focusing address bar")
                    elif key == "enter" or key == "return":
                        print(f"   → Confirming/executing action")
                    else:
                        print(f"   → Pressing {key} shortcut")
                    hotkey(key)
                    
                    # Add strategic pause for actions that trigger slow UI animations
                    if key in ["cmd+space", "cmd+t"]:
                        pause_duration = 1.5
                        print(f"⏱️  Pausing for {pause_duration}s to allow UI to settle...")
                        time.sleep(pause_duration)
                    
            elif action_text.startswith("wait"):
                ms = self._extract_number(action_text)
                if ms:
                    print(f"   → Waiting {ms}ms for page/app to load")
                    time.sleep(ms / 1000)
                    
            elif action_text.startswith("focus_address_bar"):
                print("   → Focusing browser address bar")
                print("🔍 Focusing address bar with cmd+l")
                hotkey("cmd+l")
                time.sleep(0.3)
                    
            elif action_text.startswith("done"):
                print("   → Task completed successfully")
                return True
                
        except Exception as e:
            print(f"Action error: {e}")
            
        return False

    def _bulk_type_text(self, text: str):
        """Type longer text with line breaks efficiently."""
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if line.strip():  # Skip empty lines
                type_text(line)
            if i < len(lines) - 1:  # Don't add extra line break after last line
                hotkey("enter")
                time.sleep(0.1)  # Brief pause between lines
    
    def _open_app_workflow(self, app_name: str):
        """Executes the complete, reliable sequence for opening a macOS application."""
        print(f"   Workflow: Opening application '{app_name}'")
        hotkey("cmd+space")
        time.sleep(1.5)  # Wait for Spotlight animation
        
        type_text(app_name)
        time.sleep(0.5)
        
        hotkey("enter")
        time.sleep(2.0)  # Wait for App to launch
        print(f"   ✅ Workflow complete: '{app_name}' should be open.")

    def _web_search_workflow(self, search_term: str):
        """Executes the complete, reliable sequence for a web search in Safari."""
        print(f"   Workflow: Web search for '{search_term}'")
        self._open_app_workflow("Safari") # Use our reliable app opener
        
        hotkey("cmd+t")
        time.sleep(1.5) # Wait for new tab animation
        
        # Add a trailing space to avoid autocomplete issues
        type_text(search_term + " ")
        time.sleep(0.5)
        
        hotkey("enter")
        time.sleep(2.5) # Wait for search results to load
        print(f"   ✅ Workflow complete: Web search finished.")
    
    def _speak_rationale(self, action_text: str, see_line: str, task: str):
        """Speak what Harvey is going to do and what target it's aiming for."""
        try:
            if not _TTS_AVAILABLE:
                print("🔇 TTS not available - TTS_STT module not found")
                return
            
            tts_setting = os.getenv("HARVEY_TTS", "1")
            if tts_setting in ("0", "false", "False"):
                print(f"🔇 TTS disabled via HARVEY_TTS={tts_setting}")
                return
                
            if not action_text:
                print("🔇 No action text to speak")
                return

            print(f"🎤 TTS enabled, generating speech for: {action_text[:50]}...")
            action = action_text.strip()
            reason = None

            if action.startswith("hotkey"):
                key = self._extract_text(action) or "shortcut"
                if key == "cmd+space":
                    reason = "Opening Spotlight."
                elif key == "cmd+t":
                    reason = "Opening new tab."
                elif key in ("enter", "return"):
                    reason = "Pressing Enter."
                elif key == "cmd+l":
                    reason = "Focusing address bar."
                else:
                    reason = f"Pressing {key}."
            elif action.startswith("bulk_type"):
                txt = self._extract_text(action) or "text"
                line_count = len(txt.split('\n'))
                reason = f"Typing {line_count} lines of content."
            elif action.startswith("type_text"):
                txt = self._extract_text(action) or "text"
                if len(txt) > 20:
                    txt = txt[:17] + "..."
                reason = f"Typing {txt}."
            elif action.startswith("left_click"):
                coords = self._extract_coords(action)
                # Extract specific target from see_line for better narration
                if see_line:
                    target_lower = see_line.lower()
                    if "compose" in target_lower:
                        reason = "Clicking compose button."
                    elif "subject" in target_lower:
                        reason = "Clicking subject field."
                    elif "message" in target_lower or "body" in target_lower:
                        reason = "Clicking message body."
                    elif "button" in target_lower:
                        reason = "Clicking button."
                    elif "icon" in target_lower:
                        reason = "Clicking icon."
                    else:
                        reason = f"Clicking target."
                else:
                    reason = "Clicking target."
            elif action.startswith("double_click"):
                reason = "Double-clicking to open."
            elif action.startswith("hover"):
                reason = "Hovering over element."
            elif action.startswith("scroll"):
                direction = self._extract_text(action) or "down"
                reason = f"Scrolling {direction}."
            elif action.startswith("wait"):
                ms = self._extract_number(action) or 1000
                sec = ms / 1000
                reason = f"Waiting {sec:.1f} seconds."
            elif action.startswith("done"):
                reason = "Task complete."

            if reason:
                print(f"🎵 Speaking: '{reason}'")
                # Generate audio file then play it via macOS afplay
                try:
                    audio_path = tts_speak(reason)
                    if audio_path:
                        print(f"🔊 Playing audio from: {audio_path}")
                        result = subprocess.run(["afplay", audio_path], capture_output=True, text=True)
                        if result.returncode != 0:
                            print(f"❌ afplay failed: {result.stderr}")
                        else:
                            print("✅ Audio played successfully")
                    else:
                        print("❌ TTS failed to generate audio")
                except Exception as e:
                    print(f"❌ TTS error: {e}")
        except Exception:
            # Never let TTS errors break core automation
            pass
    
    def _extract_coords(self, text):
        """Extract and validate (ratio_x, ratio_y) from action text."""
        import re
        match = re.search(r'\(([0-9.]+),\s*([0-9.]+)\)', text)
        if match:
            ratio_x = float(match.group(1))
            ratio_y = float(match.group(2))
            
            # Validate coordinates are within bounds
            ratio_x = max(0.0, min(1.0, ratio_x))
            ratio_y = max(0.0, min(1.0, ratio_y))
            
            print(f"🎯 Using coordinates: ({ratio_x:.3f}, {ratio_y:.3f})")
            return ratio_x, ratio_y
        return None
    
    def _extract_text(self, text):
        import re
        match = re.search(r'"([^"]*)"', text)
        if match:
            return match.group(1)
        return None
    
    def _extract_number(self, text):
        import re
        match = re.search(r'\((\d+)\)', text)
        if match:
            return int(match.group(1))
        return None
    
    def run(self, task):
        print(f"🚀 Harvey starting: {task}")
        
        for step in range(20):
            print(f"📸 Taking screenshot to analyze current state...")
            screenshot_data = capture_to_bytes()
            
            # DEBUG: Save the first screenshot to see what Harvey is seeing
            if step == 0 and screenshot_data:
                print(f"💾 Screenshot data length: {len(screenshot_data)} characters")
                print("💾 Saving debug screenshot as 'harvey_debug.jpg'")
                with open("harvey_debug.jpg", "wb") as f:
                    f.write(base64.b64decode(screenshot_data))
                print("✅ Debug screenshot saved! Check harvey_debug.jpg to see what Harvey sees.")
                
                # Also check image dimensions
                try:
                    from PIL import Image
                    import io
                    img_bytes = base64.b64decode(screenshot_data)
                    img = Image.open(io.BytesIO(img_bytes))
                    print(f"🖼️  Image dimensions: {img.size[0]}x{img.size[1]} pixels")
                except Exception as e:
                    print(f"❌ Error reading image: {e}")
                # Log screen points and scale for mapping verification
                try:
                    sw, sh, sc = get_screen_info()
                    print(f"🖥️  Screen points: {sw}x{sh}, scale: {sc:.1f}x")
                except Exception:
                    pass
            
            if not screenshot_data:
                print("❌ Failed to capture screenshot")
                break
                
            action = self.think(task, screenshot_data)
            # Speak a short rationale before executing the action
            self._speak_rationale(action, getattr(self, "last_see", ""), task)
            done = self.execute(action)
            
            if done:
                print("✅ Task complete!")
                break
        
        print("🏁 Harvey finished")

def main():
    # Load environment variables first (needed for offsets, API key)
    from dotenv import load_dotenv
    load_dotenv()
    
    # Show trail status
    if _MOUSE_TRAIL_ENABLED:
        print("🐭 Mouse trail enabled (set HARVEY_MOUSE_TRAIL=0 to disable)")
    else:
        print("🐭 Mouse trail disabled (set HARVEY_MOUSE_TRAIL=1 to enable)")

    # Simple CLI: either calibration or a single task string
    if len(sys.argv) < 2:
        print("Usage:\n  python harvey.py \"your task here\"\n  python harvey.py --calibrate    # interactive pointer calibration\n  python harvey.py calibrate      # same as --calibrate")
        sys.exit(1)

    arg1 = sys.argv[1].strip()
    if arg1 in ("--calibrate", "calibrate"):
        calibrate_interactive()
        return

    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        print("❌ Please set GOOGLE_API_KEY in .env file")
        sys.exit(1)

    task = arg1
    harvey = Harvey()
    harvey.run(task)

if __name__ == "__main__":
    main()