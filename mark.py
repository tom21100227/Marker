import sys
import os
import csv
import subprocess
import time
import numpy as np
import imageio
import cv2
from pynput import keyboard
from threading import Lock

# Include the unlabeled state (-1) alongside your normal states.
DEFAULT_STATES = {
    -1: "unlabeled",
    0: "not flying",
    1: "transition",
    2: "flying"
}
STATE_COLORS = {
    -1: (128, 128, 128),  # gray for unlabeled frames
    0: (0, 0, 255),       # red (BGR)
    1: (0, 255, 255),     # yellow
    2: (0, 255, 0)        # green
}

# Add these constants at the top with other constants
OVERVIEW_BAR_HEIGHT = 50
DETAIL_BAR_HEIGHT = 50
INITIAL_HOLD_DELAY = 0.2  # Time before fast labeling starts (200ms)
FAST_ADVANCE_DELAY = 0.03  # Delay between frames during fast labeling (~30fps)

def draw_progress_bars(frame, labels, current_frame, nframes, vid_width, fps):
    # Create overview progress bar
    overview_bar = np.zeros((OVERVIEW_BAR_HEIGHT, vid_width, 3), dtype=np.uint8)

    # Fill overview bar colors
    for x in range(vid_width):
        frame_idx = int((x / vid_width) * nframes)
        state = labels.get(frame_idx, -1)
        overview_bar[:, x] = STATE_COLORS[state]

    # Draw current frame indicator
    indicator_x = int((current_frame / nframes) * vid_width)
    cv2.line(overview_bar, (indicator_x, 0), (indicator_x, OVERVIEW_BAR_HEIGHT), (255, 255, 255), 2)

    # Create detail progress bar (5 seconds before/after)
    detail_bar = np.zeros((DETAIL_BAR_HEIGHT, vid_width, 3), dtype=np.uint8)
    start_frame = max(0, current_frame - int(5 * fps))
    end_frame = min(nframes, current_frame + int(5 * fps))
    window_size = end_frame - start_frame

    if window_size > 0:
        for x in range(vid_width):
            frame_idx = start_frame + int((x / vid_width) * window_size)
            state = labels.get(frame_idx, -1)
            detail_bar[:, x] = STATE_COLORS[state]

        # Draw current frame indicator
        detail_indicator_x = int(((current_frame - start_frame) / window_size) * vid_width)
        cv2.line(detail_bar, (detail_indicator_x, 0), (detail_indicator_x, DETAIL_BAR_HEIGHT), (255, 255, 255), 2)

        # Add time labels
        start_time = start_frame / fps
        end_time = end_frame / fps
        cv2.putText(detail_bar, f"{start_time:.1f}s", (10, DETAIL_BAR_HEIGHT-10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
        cv2.putText(detail_bar, f"{end_time:.1f}s", (vid_width-50, DETAIL_BAR_HEIGHT-10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)

    return np.vstack((frame, overview_bar, detail_bar))

def generate_review_video_ffmpeg(video_path, labels, fps, nframes, vid_width, vid_height):
    """
    Generate a review video using ffmpeg.
    A progress bar (with a dynamic white cursor) is added below the video.
    Unlabeled frames (state -1) are shown in gray.
    """
    progress_bar_height = 50  # Height of the progress bar in pixels
    duration = nframes / fps  # Total duration of the video in seconds

    # Generate the static progress bar image.
    progress_bar = np.zeros((progress_bar_height, vid_width, 3), dtype=np.uint8)
    for x in range(vid_width):
        frame_index = int(x / vid_width * nframes)
        # For frames that haven't been labeled, default to -1.
        state = labels.get(frame_index, -1)
        bgr_color = STATE_COLORS.get(state, (128, 128, 128))
        color = bgr_color[::-1]
        progress_bar[:, x, :] = color

    progress_bar_path = os.path.splitext(video_path)[0] + "_progress_bar.png"
    imageio.imwrite(progress_bar_path, progress_bar)
    print(f"Progress bar image saved to {progress_bar_path}")

    output_review = os.path.splitext(video_path)[0] + "_review.mp4"

    filter_complex = (
        f"[0:v]pad=iw:ih+{progress_bar_height}:0:0:color=black[bg]; "
        f"[bg][1:v]overlay=0:{vid_height}[ov]; "
        f"[ov]drawtext=text='|':"
        f"x=(w - tw) * (t / {duration}) - (tw/2):"  # Horizontal centering
        f"y={vid_height} + ({progress_bar_height}/2) - {progress_bar_height//8}:"  # Vertical centering
        f"fontsize={int(progress_bar_height * 1.1)}:"  # Convert to integer
        "fontcolor=white@0.8:"
        "box=1:boxcolor=black@0.5:"
        "borderw=2:"
        "line_spacing=0"
    )

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output file if it exists.
        "-hwaccel", "auto",  # Use GPU acceleration when possible.
        "-i", video_path,
        "-i", progress_bar_path,
        "-filter_complex", filter_complex,
        "-c:v", "h264_videotoolbox", # macOS specific,
        "-b:v", "5000k",  # Bitrate for the video stream.
        "-c:a", "copy",
        output_review
    ]
    print("Running ffmpeg command to generate review video:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Review video generated: {output_review}")

class KeyStateTracker:
    def __init__(self):
        self.lock = Lock()
        self.states = {
            # Main controls
            keyboard.Key.space: False,  # Auto-play
            keyboard.Key.left: False,   # Previous frame
            keyboard.Key.right: False,  # Next frame
            keyboard.Key.esc: False,    # Quit
            keyboard.KeyCode.from_char('q'): False,

            # Labeling keys
            keyboard.KeyCode.from_char('0'): False,
            keyboard.KeyCode.from_char('1'): False,
            keyboard.KeyCode.from_char('2'): False,

            # Jump controls
            keyboard.KeyCode.from_char(','): False,  # -5s
            keyboard.KeyCode.from_char('.'): False   # +5s
        }

    def on_press(self, key):
        with self.lock:
            if key in self.states:
                self.states[key] = True
            elif hasattr(key, 'char'):
                if key.char in ['0', '1', '2', ',', '.', 'q']:
                    self.states[keyboard.KeyCode.from_char(key.char)] = True

    def on_release(self, key):
        with self.lock:
            if key in self.states:
                self.states[key] = False
            elif hasattr(key, 'char'):
                if key.char in ['0', '1', '2', ',', '.', 'q']:
                    self.states[keyboard.KeyCode.from_char(key.char)] = False

    def get_state(self, key):
        with self.lock:
            return self.states.get(key, False)

def main():
    if len(sys.argv) < 2:
        print("Usage: python label_video.py path/to/video.mp4")
        sys.exit(1)
    video_path = sys.argv[1]

    # Open video with OpenCV
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error opening video file")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vid_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Initialize keyboard tracker
    key_tracker = KeyStateTracker()
    listener = keyboard.Listener(
        on_press=key_tracker.on_press,
        on_release=key_tracker.on_release
    )
    listener.start()

    labels = {}
    current_frame = 0
    last_frame_time = time.time()
    held_number = None
    hold_start_time = 0

    print("Controls:")
    print("  → / ← : Next/Previous frame")
    print("  ,/. : Jump 5 seconds")
    print("  Space: Hold to auto-play")
    print("  0-2: Label current frame (hold for auto-label)")
    print("  Q: Quit and export")

    cv2.namedWindow("Video Labeling Tool", cv2.WINDOW_NORMAL)
    while True:
        # Read and display frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:
            break

        # Update display
        display = frame.copy()
        text = f"Frame: {current_frame}/{nframes-1}"
        state = labels.get(current_frame, -1)
        text += f" | State: {state} ({DEFAULT_STATES[state]})"
        color = STATE_COLORS.get(state, (255, 255, 255))
        cv2.putText(display, text, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Add progress bars to frame
        combined_frame = draw_progress_bars(display, labels, current_frame, nframes, vid_width, fps)
        cv2.imshow("Video Labeling Tool", combined_frame)

        # Calculate timing
        now = time.time()
        elapsed = now - last_frame_time
        frame_delay = 1 / fps

        # Control flags
        should_advance = False
        fast_advance = False
        held_this_frame = False

        # Handle controls
        if key_tracker.get_state(keyboard.Key.esc) or key_tracker.get_state(keyboard.KeyCode.from_char('q')):
            break

        # Spacebar handling (normal speed)
        if key_tracker.get_state(keyboard.Key.space):
            should_advance = True

        # Number key handling (fast labeling)
        for num, key in enumerate([keyboard.KeyCode.from_char(str(n)) for n in range(3)]):
            if key_tracker.get_state(key):
                held_this_frame = True
                labels[current_frame] = num  # Label current frame

                if held_number != num:
                    # New key press - immediate advance
                    held_number = num
                    hold_start = now
                    current_frame = min(current_frame + 1, nframes - 1)
                    last_frame_time = now
                else:
                    # Continuing hold - check for fast advance
                    if now - hold_start > INITIAL_HOLD_DELAY:
                        fast_advance = True
                break

        # Reset states if no keys are pressed
        if not held_this_frame:
            held_number = None
            fast_advance = False

        # Handle frame advancement
        if fast_advance:
            # Ultra-fast labeling mode
            if (now - last_frame_time) >= FAST_ADVANCE_DELAY:
                current_frame = min(current_frame + 1, nframes - 1)
                labels[current_frame] = held_number  # Label while advancing
                last_frame_time = now
        elif should_advance:
            # Normal playback speed
            if elapsed >= frame_delay:
                current_frame = min(current_frame + 1, nframes - 1)
                last_frame_time = now

        # Handle other controls
        if key_tracker.get_state(keyboard.Key.right):
            current_frame = min(current_frame + 1, nframes - 1)
        if key_tracker.get_state(keyboard.Key.left):
            current_frame = max(0, current_frame - 1)
        if key_tracker.get_state(keyboard.KeyCode.from_char(',')):
            current_frame = max(0, current_frame - int(5 * fps))
        if key_tracker.get_state(keyboard.KeyCode.from_char('.')):
            current_frame = min(nframes - 1, current_frame + int(5 * fps))

        # Handle OpenCV events
        key = cv2.waitKey(1 if (fast_advance or should_advance) else 0)
        if key == ord('q'):
            break
    # Cleanup and export (same as original)
    cap.release()
    cv2.destroyAllWindows()

    # Fill unlabeled frames and export CSV
    not_labelled = 0
    not_labelled_frames = []
    for i in range(nframes):
        if i not in labels:
            not_labelled += 1
            not_labelled_frames.append(i)
            labels[i] = -1

    if not_labelled != 0:
        print(f"{not_labelled} frame(s) detected as not labelled.")
        print(not_labelled_frames)

    csv_filename = os.path.splitext(video_path)[0] + "_labels.csv"
    with open(csv_filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "state", "state_label"])
        for i in range(nframes):
            state = labels[i]
            writer.writerow([i, state, DEFAULT_STATES.get(state, "unlabeled")])
    print(f"Labels exported to {csv_filename}")

    # Generate review video
    print("Generating review video...")
    generate_review_video_ffmpeg(video_path, labels, fps, nframes, vid_width, vid_height)

if __name__ == "__main__":
    main()
