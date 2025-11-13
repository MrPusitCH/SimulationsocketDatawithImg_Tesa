#!/usr/bin/env python3
"""
Resize images in a directory to a specific resolution.

This script resizes all images in a directory to a target width (maintaining aspect ratio)
or to a square resolution.

Examples:
    # Resize to 620px width (maintain aspect ratio)
    python resize_images.py P3_VIDEO_frames --width 620

    # Resize to 620x620 square
    python resize_images.py P3_VIDEO_frames --size 620 620

    # Resize to 620px width and save to new folder
    python resize_images.py P3_VIDEO_frames --width 620 --output-dir P3_VIDEO_frames_620
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        os.environ['PYTHONIOENCODING'] = 'utf-8'

try:
    from PIL import Image
except ImportError:
    print("Pillow (PIL) is required. Install with: pip install Pillow", file=sys.stderr)
    sys.exit(1)


def resize_image(
    input_path: Path,
    output_path: Path,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    target_size: Optional[Tuple[int, int]] = None,
    quality: int = 95
) -> bool:
    """
    Resize an image.

    Args:
        input_path: Path to input image
        output_path: Path to save resized image
        target_width: Target width (maintains aspect ratio)
        target_height: Target height (maintains aspect ratio)
        target_size: Target size as (width, height) tuple
        quality: JPEG quality (1-100, only for JPEG)

    Returns:
        True if successful, False otherwise
    """
    try:
        with Image.open(input_path) as img:
            original_size = img.size
            original_format = img.format

            # Determine target size
            if target_size:
                new_size = target_size
            elif target_width:
                # Calculate height maintaining aspect ratio
                ratio = target_width / original_size[0]
                new_height = int(original_size[1] * ratio)
                new_size = (target_width, new_height)
            elif target_height:
                # Calculate width maintaining aspect ratio
                ratio = target_height / original_size[1]
                new_width = int(original_size[0] * ratio)
                new_size = (new_width, target_height)
            else:
                return False

            # Resize image
            resized_img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Save resized image
            if original_format == 'JPEG' or output_path.suffix.lower() in ['.jpg', '.jpeg']:
                resized_img.save(output_path, 'JPEG', quality=quality, optimize=True)
            else:
                resized_img.save(output_path, original_format or 'PNG', optimize=True)

            return True

    except Exception as e:
        print(f"   ❌ Error processing {input_path.name}: {e}", file=sys.stderr)
        return False


def resize_images_in_directory(
    input_dir: str,
    output_dir: Optional[str] = None,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    target_size: Optional[Tuple[int, int]] = None,
    quality: int = 95,
    image_extensions: Tuple[str, ...] = ('.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG')
) -> int:
    """
    Resize all images in a directory.

    Args:
        input_dir: Input directory path
        output_dir: Output directory path (None = overwrite originals)
        target_width: Target width
        target_height: Target height
        target_size: Target size as (width, height)
        quality: JPEG quality
        image_extensions: Supported image extensions

    Returns:
        Number of images successfully resized
    """
    input_path = Path(input_dir)
    
    if not input_path.exists() or not input_path.is_dir():
        print(f"❌ Error: Directory not found: {input_dir}", file=sys.stderr)
        return 0

    # Get all image files
    image_files = [
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix in image_extensions
    ]

    if not image_files:
        print(f"❌ Error: No image files found in {input_dir}", file=sys.stderr)
        return 0

    # Setup output directory
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        overwrite = False
    else:
        output_path = input_path
        overwrite = True

    # Determine target size description
    if target_size:
        size_desc = f"{target_size[0]}x{target_size[1]}"
    elif target_width:
        size_desc = f"{target_width}px width (maintain aspect ratio)"
    elif target_height:
        size_desc = f"{target_height}px height (maintain aspect ratio)"
    else:
        print("❌ Error: Must specify --width, --height, or --size", file=sys.stderr)
        return 0

    print(f"🖼️  Resizing images...")
    print(f"   Input directory: {input_path.absolute()}")
    print(f"   Output directory: {output_path.absolute()}")
    print(f"   Target size: {size_desc}")
    print(f"   Images found: {len(image_files)}")
    print()

    # Resize each image
    success_count = 0
    for i, img_file in enumerate(sorted(image_files), 1):
        if overwrite:
            output_file = img_file
        else:
            output_file = output_path / img_file.name

        # Get original size
        try:
            with Image.open(img_file) as img:
                original_size = img.size
        except:
            original_size = (0, 0)

        if resize_image(img_file, output_file, target_width, target_height, target_size, quality):
            # Get new size
            try:
                with Image.open(output_file) as img:
                    new_size = img.size
            except:
                new_size = (0, 0)

            print(f"   ✓ [{i}/{len(image_files)}] {img_file.name}")
            print(f"      {original_size[0]}x{original_size[1]} → {new_size[0]}x{new_size[1]}")
            success_count += 1

    print()
    print(f"✅ Resizing complete!")
    print(f"   Successfully resized: {success_count}/{len(image_files)} images")
    print(f"   Output directory: {output_path.absolute()}")

    return success_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resize images in a directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Resize to 620px width (maintain aspect ratio)
  python resize_images.py P3_VIDEO_frames --width 620

  # Resize to 620x620 square
  python resize_images.py P3_VIDEO_frames --size 620 620

  # Resize and save to new folder
  python resize_images.py P3_VIDEO_frames --width 620 --output-dir P3_VIDEO_frames_620
        """
    )

    parser.add_argument(
        "input_dir",
        help="Input directory containing images"
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        help="Output directory (default: overwrite originals)"
    )

    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument(
        "--width",
        "-w",
        type=int,
        help="Target width in pixels (maintains aspect ratio)"
    )
    size_group.add_argument(
        "--height",
        type=int,
        help="Target height in pixels (maintains aspect ratio)"
    )
    size_group.add_argument(
        "--size",
        "-s",
        type=int,
        nargs=2,
        metavar=("WIDTH", "HEIGHT"),
        help="Target size as width height (e.g., 620 620)"
    )

    parser.add_argument(
        "--quality",
        "-q",
        type=int,
        default=95,
        choices=range(1, 101),
        metavar="1-100",
        help="JPEG quality (1-100, default: 95)"
    )

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> bool:
    if not os.path.exists(args.input_dir):
        print(f"❌ Error: Input directory not found: {args.input_dir}", file=sys.stderr)
        return False

    if not os.path.isdir(args.input_dir):
        print(f"❌ Error: Not a directory: {args.input_dir}", file=sys.stderr)
        return False

    if not (args.width or args.height or args.size):
        print("❌ Error: Must specify --width, --height, or --size", file=sys.stderr)
        return False

    if args.width and args.width <= 0:
        print("❌ Error: width must be > 0", file=sys.stderr)
        return False

    if args.height and args.height <= 0:
        print("❌ Error: height must be > 0", file=sys.stderr)
        return False

    if args.size and (args.size[0] <= 0 or args.size[1] <= 0):
        print("❌ Error: size dimensions must be > 0", file=sys.stderr)
        return False

    return True


def main() -> int:
    args = parse_args()
    
    if not validate_args(args):
        return 1

    target_size = None
    if args.size:
        target_size = tuple(args.size)

    success_count = resize_images_in_directory(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        target_width=args.width,
        target_height=args.height,
        target_size=target_size,
        quality=args.quality,
    )

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

