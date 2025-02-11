import sys
import os
import csv
import subprocess
import time
import numpy as np
import imageio
import pygame

# Include the unlabeled state (-1) alongside your normal states.
DEFAULT_STATES = {
    -1: "unlabeled",
    0: "not flying",
    1: "transition",
    2: "flying"
}
STATE_COLORS = {
    -1: (128, 128, 128),  # gray for unlabeled frames
    0: (255, 0, 0),       # red
    1: (255, 255, 0),     # yellow
    2: (0, 255, 0)        # green
}

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
        color = STATE_COLORS.get(state, (128, 128, 128))
        progress_bar[:, x, :] = color

    progress_bar_path = os.path.splitext(video_path)[0] + "_progress_bar.png"
    imageio.imwrite(progress_bar_path, progress_bar)
    print(f"Progress bar image saved to {progress_bar_path}")

    output_review = os.path.splitext(video_path)[0] + "_review.mp4"

    filter_complex = (
        f"[0:v]pad=iw:ih+{progress_bar_height}:0:0:color=black[bg]; "
        f"[bg][1:v]overlay=0:{vid_height}[ov]; "
        f"[ov]drawtext=fontfile=/path/to/font.ttf:text='▏':"
        f"x=(w - tw) * (t / {duration}):"
        f"y={vid_height} + ({progress_bar_height} - th) / 2:"
        f"fontsize={progress_bar_height}:"
        f"fontcolor=white@0.8"
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

def draw_progress_bars(screen, labels, current_frame, nframes, vid_width, overview_height, detail_height, fps, display_height, font):
    # Draw the overview progress bar
    overview_bar = np.zeros((overview_height, vid_width, 3), dtype=np.uint8)
    for x in range(vid_width):
        frame_index = int(x / vid_width * nframes)
        state = labels.get(frame_index, -1)
        color = STATE_COLORS.get(state, (128, 128, 128))
        overview_bar[:, x, :] = color

    overview_surface = pygame.surfarray.make_surface(np.transpose(overview_bar, (1, 0, 2)))
    screen.blit(overview_surface, (0, display_height))

    # Draw the current frame indicator on the overview bar
    indicator_x = int(current_frame / nframes * vid_width)
    pygame.draw.line(screen, (255, 255, 255), (indicator_x, display_height), (indicator_x, display_height + overview_height), 2)

    # Draw the detail progress bar
    detail_bar = np.zeros((detail_height, vid_width, 3), dtype=np.uint8)
    start_frame = max(0, current_frame - int(5 * fps))
    end_frame = min(nframes, current_frame + int(5 * fps))
    for x in range(vid_width):
        frame_index = start_frame + int(x / vid_width * (end_frame - start_frame))
        if frame_index < nframes:
            state = labels.get(frame_index, -1)
            color = STATE_COLORS.get(state, (128, 128, 128))
            detail_bar[:, x, :] = color

    detail_surface = pygame.surfarray.make_surface(np.transpose(detail_bar, (1, 0, 2)))
    screen.blit(detail_surface, (0, display_height + overview_height))

    # Draw the current frame indicator on the detail bar
    detail_indicator_x = int((current_frame - start_frame) / (end_frame - start_frame) * vid_width)
    pygame.draw.line(screen, (255, 255, 255), (detail_indicator_x, display_height + overview_height), (detail_indicator_x, display_height + overview_height + detail_height), 2)

    # Draw the time ticks on the detail bar
    for i in range(11):
        tick_x = int(i / 10 * vid_width)
        tick_time = (start_frame + i / 10 * (end_frame - start_frame)) / fps
        tick_label = f"{tick_time:.1f}s"
        tick_surface = font.render(tick_label, True, (255, 255, 255))
        screen.blit(tick_surface, (tick_x, display_height + overview_height + detail_height))

def main():
    if len(sys.argv) < 2:
        print("Usage: python label_video.py path/to/video.mp4")
        sys.exit(1)
    video_path = sys.argv[1]

    # Open the video using imageio.
    reader = imageio.get_reader(video_path, 'ffmpeg')
    meta = reader.get_meta_data()
    fps = meta.get('fps', 30)
    nframes = meta.get('nframes')
    if nframes is None or nframes == float('inf'):
        duration = meta.get('duration', 0)
        nframes = int(duration * fps)

    print(f"Video loaded: {nframes} frames at {fps} fps")

    # Get video dimensions from the first frame.
    frame0 = reader.get_data(0)
    vid_height, vid_width, _ = frame0.shape

    # Initialize pygame and scale the window to fit the display.
    pygame.init()
    display_info = pygame.display.Info()
    max_width = display_info.current_w
    max_height = display_info.current_h

    scale = min(max_width / vid_width, max_height / vid_height, 0.75)
    display_width = int(vid_width * scale)
    display_height = int(vid_height * scale)
    overview_height = 50
    detail_height = 50
    total_height = display_height + overview_height + detail_height
    screen = pygame.display.set_mode((display_width, total_height))
    pygame.display.set_caption("Video Labeling Tool")
    font = pygame.font.SysFont(None, 24)

    # Variables to manage labeling.
    labels = {}  # frame index -> state (0, 1, or 2); unlabeled frames are left unset.
    current_frame = 0

    auto_play = False  # Triggered by holding space.
    held_state = None         # The number key being held (0, 1, or 2).
    held_state_start = None   # Time when the key was pressed.
    held_state_last_advance = None  # Time of the last auto-advance.

    clock = pygame.time.Clock()
    running = True

    print("Controls:")
    print("  → / ← : Next / Previous frame")
    print("  , (<) / . (>) : Jump backward/forward 5 seconds")
    print("  Space : Hold to auto-play")
    print("  0, 1, 2 : Tap to label current frame; hold for auto-advance after 0.3 sec")
    print("  Q or ESC or close window: Quit and export current labels (unlabeled frames get -1)")

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # Process keydown events.
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_RIGHT:
                    current_frame = min(nframes - 1, current_frame + 1)
                elif event.key == pygame.K_LEFT:
                    current_frame = max(0, current_frame - 1)
                elif event.key in (pygame.K_COMMA, pygame.K_LESS):
                    jump = int(5 * fps)
                    current_frame = max(0, current_frame - jump)
                elif event.key in (pygame.K_PERIOD, pygame.K_GREATER):
                    jump = int(5 * fps)
                    current_frame = min(nframes - 1, current_frame + jump)
                elif event.key == pygame.K_SPACE:
                    auto_play = True
                elif event.key in (pygame.K_0, pygame.K_1, pygame.K_2):
                    key_state = event.key - pygame.K_0
                    # Start tracking the held number key.
                    if held_state is None:
                        held_state = key_state
                        held_state_start = pygame.time.get_ticks()
                        held_state_last_advance = None
                        labels[current_frame] = held_state
                        print(f"Labeled frame {current_frame} as {held_state} ({DEFAULT_STATES[held_state]})")

            # Process keyup events for the number keys.
            elif event.type == pygame.KEYUP:
                if event.key in (pygame.K_0, pygame.K_1, pygame.K_2):
                    released_state = event.key - pygame.K_0
                    if held_state is not None and held_state == released_state:
                        held_state = None
                        held_state_start = None
                        held_state_last_advance = None

        keys = pygame.key.get_pressed()
        if not keys[pygame.K_SPACE]:
            auto_play = False

        # Held number key auto-advance.
        if held_state is not None:
            current_ticks = pygame.time.get_ticks()
            if held_state_last_advance is None:
                if current_ticks - held_state_start >= 300:
                    held_state_last_advance = current_ticks
                    labels[current_frame] = held_state
                    print(f"Auto-labeled frame {current_frame} as {held_state} ({DEFAULT_STATES[held_state]}) [triggered after hold delay]")
                    current_frame += 1
                    if current_frame >= nframes:
                        running = False
                    clock.tick(fps)
                    continue
            else:
                interval = 1000 / fps
                if current_ticks - held_state_last_advance >= interval:
                    held_state_last_advance = current_ticks
                    labels[current_frame] = held_state
                    print(f"Auto-labeled frame {current_frame} as {held_state} ({DEFAULT_STATES[held_state]})")
                    current_frame += 1
                    if current_frame >= nframes:
                        running = False
                    clock.tick(fps)
                    continue

        # Space bar auto-play.
        if auto_play:
            current_frame += 1
            if current_frame >= nframes:
                running = False
            clock.tick(fps)
            continue

        # Display the current frame.
        try:
            frame = reader.get_data(current_frame)
        except IndexError:
            running = False
            break

        # Convert frame (from imageio: height x width x 3) for pygame (width x height x 3)
        frame_surface = pygame.surfarray.make_surface(np.transpose(frame, (1, 0, 2)))
        frame_surface = pygame.transform.scale(frame_surface, (display_width, display_height))
        screen.blit(frame_surface, (0, 0))

        # Display frame information.
        text_str = f"Frame: {current_frame}"
        if current_frame in labels:
            state = labels[current_frame]
            text_str += f" | Label: {state} ({DEFAULT_STATES[state]})"
        else:
            text_str += " | Unlabeled"
        text_surface = font.render(text_str, True, (255, 255, 255))
        screen.blit(text_surface, (10, 10))

        draw_progress_bars(screen, labels, current_frame, nframes, display_width, overview_height, detail_height, fps, display_height, font)

        pygame.display.flip()

        clock.tick(30)

    pygame.quit()

    # For frames that weren't labeled, assign -1.
    for i in range(int(nframes)):
        if i not in labels:
            labels[i] = -1
            print(f"Frame {i} left unlabeled (assigned -1).")

    # Export the results to CSV.
    csv_filename = os.path.splitext(video_path)[0] + "_labels.csv"
    with open(csv_filename, mode="w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["frame", "state", "state_label"])
        for i in range(nframes):
            state = labels.get(i, -1)
            writer.writerow([i, state, DEFAULT_STATES.get(state, "unlabeled")])
    print(f"Labels exported to {csv_filename}")

    # Generate the review video with the progress bar.
    print("Generating review video with progress bar overlay using ffmpeg...")
    generate_review_video_ffmpeg(video_path, labels, fps, nframes, vid_width, vid_height)

if __name__ == "__main__":
    main()
