#!/usr/bin/env python3
"""
Convert MP4 video to individual picture frames.

This script extracts frames from an MP4 video file and saves them as images.
Supports various image formats (PNG, JPG, JPEG) and frame extraction options.

Examples:
    # Extract all frames
    python mp4_to_frames.py input.mp4

    # Extract frames at specific interval (every 1 second)
    python mp4_to_frames.py input.mp4 --interval 1.0

    # Extract specific number of frames
    python mp4_to_frames.py input.mp4 --max-frames 100

    # Extract frames starting from specific time
    python mp4_to_frames.py input.mp4 --start-time 10.0

    # Extract frames with custom output directory and format
    python mp4_to_frames.py input.mp4 --output-dir frames --format jpg --quality 95
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        # Fallback for older Python versions
        os.environ['PYTHONIOENCODING'] = 'utf-8'

try:
    import cv2
except ImportError:
    print("OpenCV (cv2) is required. Install with: pip install opencv-python", file=sys.stderr)
    sys.exit(1)


def extract_frames(
    video_path: str,
    output_dir: str = "frames",
    format: str = "png",
    interval: Optional[float] = None,
    max_frames: Optional[int] = None,
    start_time: float = 0.0,
    end_time: Optional[float] = None,
    quality: int = 95,
    prefix: str = "frame",
) -> int:
    """
    Extract frames from MP4 video file.

    Args:
        video_path: Path to input MP4 video file
        output_dir: Directory to save extracted frames
        format: Image format (png, jpg, jpeg)
        interval: Extract frame every N seconds (None = all frames)
        max_frames: Maximum number of frames to extract (None = all)
        start_time: Start time in seconds
        end_time: End time in seconds (None = end of video)
        quality: JPEG quality (1-100, only for jpg/jpeg)
        prefix: Prefix for output filenames

    Returns:
        Number of frames extracted
    """
    # Validate input file
    if not os.path.exists(video_path):
        print(f"❌ Error: Video file not found: {video_path}", file=sys.stderr)
        return 0

    # Normalize format
    format = format.lower()
    if format == "jpg":
        format = "jpeg"
    
    if format not in ["png", "jpeg"]:
        print(f"❌ Error: Unsupported format: {format}. Use 'png' or 'jpg'", file=sys.stderr)
        return 0

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Open video file
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"❌ Error: Could not open video file: {video_path}", file=sys.stderr)
        return 0

    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"📹 Video Info:")
    print(f"   File: {video_path}")
    print(f"   Resolution: {width}x{height}")
    print(f"   FPS: {fps:.2f}")
    print(f"   Duration: {duration:.2f} seconds")
    print(f"   Total frames: {total_frames}")
    print(f"   Output: {output_dir}/")
    print(f"   Format: {format.upper()}")
    print()

    # Calculate frame extraction parameters
    start_frame = int(start_time * fps) if start_time > 0 else 0
    end_frame = int(end_time * fps) if end_time else total_frames
    
    # Clamp values
    start_frame = max(0, min(start_frame, total_frames - 1))
    end_frame = max(start_frame + 1, min(end_frame, total_frames))

    # Determine frame step
    if interval:
        frame_step = max(1, int(interval * fps))
    else:
        frame_step = 1

    # Set starting position
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    # Extract frames
    frame_count = 0
    saved_count = 0
    current_frame = start_frame

    print(f"📤 Extracting frames...")
    print(f"   Start frame: {start_frame}")
    print(f"   End frame: {end_frame}")
    print(f"   Frame step: {frame_step}")
    if max_frames:
        print(f"   Max frames: {max_frames}")
    print()

    try:
        while current_frame < end_frame:
            ret, frame = cap.read()
            
            if not ret:
                break

            # Extract frame if it matches our criteria
            if frame_count % frame_step == 0:
                # Generate filename
                frame_number = current_frame
                filename = f"{prefix}_{frame_number:06d}.{format}"
                filepath = output_path / filename

                # Save frame
                if format == "png":
                    cv2.imwrite(str(filepath), frame)
                else:  # jpeg
                    cv2.imwrite(
                        str(filepath),
                        frame,
                        [cv2.IMWRITE_JPEG_QUALITY, quality]
                    )

                saved_count += 1
                print(f"   ✓ Saved: {filename} ({saved_count}/{end_frame - start_frame if not max_frames else '?'})")

                # Check max frames limit
                if max_frames and saved_count >= max_frames:
                    break

            frame_count += 1
            current_frame += 1

    except KeyboardInterrupt:
        print(f"\n\n⏹️  Extraction interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Error during extraction: {e}", file=sys.stderr)
        return saved_count

    finally:
        cap.release()

    print(f"\n✅ Extraction complete!")
    print(f"   Frames saved: {saved_count}")
    print(f"   Output directory: {output_path.absolute()}")

    return saved_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract frames from MP4 video file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract all frames
  python mp4_to_frames.py video.mp4

  # Extract every 1 second
  python mp4_to_frames.py video.mp4 --interval 1.0

  # Extract first 100 frames
  python mp4_to_frames.py video.mp4 --max-frames 100

  # Extract frames from 10s to 30s
  python mp4_to_frames.py video.mp4 --start-time 10.0 --end-time 30.0
        """
    )

    parser.add_argument(
        "video",
        help="Path to input MP4 video file"
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        default="frames",
        help="Output directory for extracted frames (default: frames)"
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=["png", "jpg", "jpeg"],
        default="png",
        help="Output image format (default: png)"
    )

    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        help="Extract frame every N seconds (e.g., 1.0 for 1 frame per second)"
    )

    parser.add_argument(
        "--max-frames",
        "-n",
        type=int,
        help="Maximum number of frames to extract"
    )

    parser.add_argument(
        "--start-time",
        type=float,
        default=0.0,
        help="Start time in seconds (default: 0.0)"
    )

    parser.add_argument(
        "--end-time",
        type=float,
        help="End time in seconds (extract until end if not specified)"
    )

    parser.add_argument(
        "--quality",
        "-q",
        type=int,
        default=95,
        choices=range(1, 101),
        metavar="1-100",
        help="JPEG quality (1-100, only for jpg/jpeg, default: 95)"
    )

    parser.add_argument(
        "--prefix",
        "-p",
        default="frame",
        help="Prefix for output filenames (default: frame)"
    )

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> bool:
    if not os.path.exists(args.video):
        print(f"❌ Error: Video file not found: {args.video}", file=sys.stderr)
        return False

    if args.start_time < 0:
        print("❌ Error: start-time must be >= 0", file=sys.stderr)
        return False

    if args.end_time and args.end_time <= args.start_time:
        print("❌ Error: end-time must be > start-time", file=sys.stderr)
        return False

    if args.interval and args.interval <= 0:
        print("❌ Error: interval must be > 0", file=sys.stderr)
        return False

    if args.max_frames and args.max_frames <= 0:
        print("❌ Error: max-frames must be > 0", file=sys.stderr)
        return False

    return True


def main() -> int:
    args = parse_args()
    
    if not validate_args(args):
        return 1

    saved_count = extract_frames(
        video_path=args.video,
        output_dir=args.output_dir,
        format=args.format,
        interval=args.interval,
        max_frames=args.max_frames,
        start_time=args.start_time,
        end_time=args.end_time,
        quality=args.quality,
        prefix=args.prefix,
    )

    return 0 if saved_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

