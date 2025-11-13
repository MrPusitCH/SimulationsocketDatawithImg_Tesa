#!/usr/bin/env python3
"""
Simulate binary image frames sent via WebSocket to the backend server.

This simulator sends actual binary image files (PNG/JPEG) through WebSocket,
testing the new binary image frame support in the backend.

WebSocket endpoint: ws://localhost:3000/ws?type=ingest&device_id=xxx&camera_id=xxx

Configuration:
- Set WEBSOCKET_ENDPOINT environment variable for default endpoint
- Or use --endpoint argument to specify full WebSocket URL
- Or use --host and --port to build endpoint automatically

Usage modes:
1. Send metadata in query string, then send binary images
2. Send metadata JSON message first, then send binary images
3. Send binary images directly (uses query string metadata)

Examples:
    # Send images from P3_VIDEO_frames directory
    python drone_binary_image_simulator.py \\
        --host localhost --port 3000 \\
        --device-id raspberry-pi-1 \\
        --camera-id cam-001 \\
        --frames-dir P3_VIDEO_frames \\
        --interval-s 0.5

    # Send with metadata in query string
    python drone_binary_image_simulator.py \\
        --host localhost --port 3000 \\
        --device-id pi-1 --camera-id cam-1 \\
        --frames-dir P3_VIDEO_frames \\
        --updates 10

    # Send metadata via JSON first, then images
    python drone_binary_image_simulator.py \\
        --host localhost --port 3000 \\
        --device-id pi-1 --camera-id cam-1 \\
        --frames-dir P3_VIDEO_frames \\
        --send-metadata-json
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        os.environ['PYTHONIOENCODING'] = 'utf-8'

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError as exc:
    print("websockets is required. Install with `pip install websockets`.", file=sys.stderr)
    raise

# Default WebSocket endpoint (can be overridden via environment variable or --endpoint argument)
# For Raspberry Pi, set this to your backend server URL, e.g.:
# WEBSOCKET_ENDPOINT = "ws://192.168.1.100:3000/ws?type=ingest"
# Or use environment variable: export WEBSOCKET_ENDPOINT="ws://your-server:3000/ws?type=ingest"
WEBSOCKET_ENDPOINT = os.getenv("WEBSOCKET_ENDPOINT", None)  # None = build from host/port


def get_image_files(directory: str) -> List[Path]:
    """Get all image files (PNG, JPEG, JPG) from directory, sorted by name."""
    dir_path = Path(directory)
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    
    image_extensions = {'.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG'}
    image_files = [
        f for f in dir_path.iterdir()
        if f.is_file() and f.suffix in image_extensions
    ]
    image_files.sort(key=lambda x: x.name)
    return image_files


async def send_binary_images(
    ws: WebSocketClientProtocol,
    args: argparse.Namespace
) -> int:
    """Main loop to send binary image frames."""
    
    # Get image files
    try:
        image_files = get_image_files(args.frames_dir)
        if not image_files:
            print(f"❌ No image files found in {args.frames_dir}", file=sys.stderr)
            return 1
        print(f"📁 Found {len(image_files)} image files")
    except Exception as e:
        print(f"❌ Error reading image directory: {e}", file=sys.stderr)
        return 1
    
    # Wait for welcome message
    try:
        welcome = await asyncio.wait_for(ws.recv(), timeout=2.0)
        welcome_data = json.loads(welcome)
        if welcome_data.get("type") == "connected":
            print(f"✅ Connected: {welcome_data.get('message', '')}\n")
    except asyncio.TimeoutError:
        print("⚠️  No welcome message received, continuing...\n")
    except json.JSONDecodeError:
        print(f"📨 Received: {welcome}\n")
    
    # Send metadata JSON message if requested
    if args.send_metadata_json:
        metadata = {
            "type": "metadata",
            "device_id": args.device_id,
            "camera_id": args.camera_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await ws.send(json.dumps(metadata))
        print(f"📋 Sent metadata JSON: {json.dumps(metadata)}")
        
        # Wait for acknowledgment
        try:
            ack = await asyncio.wait_for(ws.recv(), timeout=1.0)
            ack_data = json.loads(ack)
            if ack_data.get("type") == "ack":
                print(f"   ✅ Metadata acknowledged\n")
        except (asyncio.TimeoutError, json.JSONDecodeError):
            pass
    
    # Send images
    frame_count = 0
    updates_remaining = args.updates if args.updates > 0 else None
    image_index = 0
    
    print(f"📤 Starting to send binary image frames...\n")
    
    try:
        while updates_remaining is None or updates_remaining > 0:
            # Cycle through images if we've sent all
            if image_index >= len(image_files):
                if args.loop:
                    image_index = 0
                    print(f"🔄 Looping back to first image\n")
                else:
                    print(f"✅ Sent all {len(image_files)} images")
                    break
            
            image_file = image_files[image_index]
            
            # Read image file as binary
            try:
                with open(image_file, 'rb') as f:
                    image_data = f.read()
            except Exception as e:
                print(f"❌ Error reading {image_file.name}: {e}", file=sys.stderr)
                image_index += 1
                continue
            
            # Send binary image
            await ws.send(image_data)
            
            frame_count += 1
            image_index += 1
            
            # Print status
            if frame_count % 10 == 0 or frame_count == 1:
                print(f"📸 Frame {frame_count}: Sent {image_file.name} ({len(image_data)} bytes)")
            
            # Try to receive acknowledgment (non-blocking)
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=0.1)
                response_data = json.loads(response)
                msg_type = response_data.get("type", "unknown")
                if msg_type == "ack":
                    if args.verbose:
                        print(f"   ✅ ACK: {response_data.get('message', '')} (fram_id: {response_data.get('fram_id', 'N/A')})")
                elif msg_type == "error":
                    print(f"   ❌ ERROR: {response_data.get('error', 'Unknown error')}")
            except asyncio.TimeoutError:
                pass  # No response yet, continue
            except json.JSONDecodeError:
                pass  # Not JSON, ignore
            
            if updates_remaining:
                updates_remaining -= 1
            
            # Wait before sending next frame
            if updates_remaining is None or updates_remaining > 0:
                await asyncio.sleep(args.interval_s)
    
    except KeyboardInterrupt:
        print(f"\n\n⏹️  Stopped by user.")
        print(f"   Total frames sent: {frame_count}")
    except websockets.exceptions.ConnectionClosed:
        print(f"\n\n⚠️  Connection closed by server.")
        print(f"   Total frames sent: {frame_count}")
    except Exception as e:
        print(f"\n\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    print(f"\n✅ Completed: Sent {frame_count} binary image frames")
    return 0


async def main_async(args: argparse.Namespace) -> int:
    """Main async function."""
    # Determine WebSocket URI
    if args.endpoint:
        # Use provided endpoint directly
        uri = args.endpoint
        # Append query parameters if not already present
        if "?" not in uri:
            query_params = []
            if args.device_id:
                query_params.append(f"device_id={args.device_id}")
            if args.camera_id:
                query_params.append(f"camera_id={args.camera_id}")
            if query_params:
                uri = f"{uri}?{'&'.join(query_params)}"
        elif args.device_id or args.camera_id:
            # Append additional params to existing query string
            query_params = []
            if args.device_id:
                query_params.append(f"device_id={args.device_id}")
            if args.camera_id:
                query_params.append(f"camera_id={args.camera_id}")
            if query_params:
                uri = f"{uri}&{'&'.join(query_params)}"
    elif WEBSOCKET_ENDPOINT:
        # Use endpoint from environment variable
        uri = WEBSOCKET_ENDPOINT
        # Append query parameters if not already present
        if "?" not in uri:
            query_params = []
            if args.device_id:
                query_params.append(f"device_id={args.device_id}")
            if args.camera_id:
                query_params.append(f"camera_id={args.camera_id}")
            if query_params:
                uri = f"{uri}?{'&'.join(query_params)}"
        elif args.device_id or args.camera_id:
            query_params = []
            if args.device_id:
                query_params.append(f"device_id={args.device_id}")
            if args.camera_id:
                query_params.append(f"camera_id={args.camera_id}")
            if query_params:
                uri = f"{uri}&{'&'.join(query_params)}"
    else:
        # Build URI from host/port (backward compatibility)
        query_params = ["type=ingest"]
        if args.device_id:
            query_params.append(f"device_id={args.device_id}")
        if args.camera_id:
            query_params.append(f"camera_id={args.camera_id}")
        
        path = f"/ws?{'&'.join(query_params)}"
        uri = f"ws://{args.host}:{args.port}{path}"
    
    try:
        print(f"🔌 Connecting to {uri}...")
        async with websockets.connect(uri) as ws:
            return await send_binary_images(ws, args)
    except OSError as exc:
        print(f"❌ Failed to connect to {uri} ({exc}).", file=sys.stderr)
        print(f"   Make sure the server is running and accessible", file=sys.stderr)
        return 1
    except websockets.exceptions.InvalidURI:
        print(f"❌ Invalid WebSocket URI: {uri}", file=sys.stderr)
        return 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Send binary image frames via WebSocket to backend."
    )
    
    # Connection
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Full WebSocket endpoint URL (e.g., ws://192.168.1.100:3000/ws?type=ingest). "
             "If provided, --host and --port are ignored. "
             "Can also be set via WEBSOCKET_ENDPOINT environment variable."
    )
    parser.add_argument("--host", default="localhost", help="WebSocket server hostname (used if --endpoint not provided)")
    parser.add_argument("--port", type=int, default=3000, help="WebSocket server port (used if --endpoint not provided)")
    
    # Metadata
    parser.add_argument("--device-id", default="sim-device-1", help="Device identifier")
    parser.add_argument("--camera-id", default="sim-camera-1", help="Camera identifier")
    
    # Image source
    parser.add_argument(
        "--frames-dir",
        default="P3_VIDEO_frames",
        help="Directory containing image files (PNG/JPEG)"
    )
    
    # Sending options
    parser.add_argument(
        "--interval-s",
        type=float,
        default=0.5,
        help="Seconds between frames (default: 0.5)"
    )
    parser.add_argument(
        "--updates",
        type=int,
        default=0,
        help="Total frames to send (0 = send all images once)"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Loop through images continuously"
    )
    parser.add_argument(
        "--send-metadata-json",
        action="store_true",
        help="Send metadata as JSON message before images"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed acknowledgments"
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    if args.interval_s <= 0:
        print("Interval must be greater than zero.", file=sys.stderr)
        return 2
    
    if args.updates < 0:
        print("Updates must be >= 0 (0 = send all).", file=sys.stderr)
        return 2
    
    print(f"\n🚀 Binary Image Frame Simulator")
    if args.endpoint:
        print(f"   Endpoint: {args.endpoint}")
    elif WEBSOCKET_ENDPOINT:
        print(f"   Endpoint: {WEBSOCKET_ENDPOINT} (from environment)")
    else:
        print(f"   Server: ws://{args.host}:{args.port}/ws?type=ingest")
    print(f"   Device ID: {args.device_id}")
    print(f"   Camera ID: {args.camera_id}")
    print(f"   Frames directory: {args.frames_dir}")
    print(f"   Interval: {args.interval_s}s")
    print(f"   Updates: {'all images' if args.updates == 0 else args.updates}")
    print(f"   Loop: {args.loop}")
    print(f"   Send metadata JSON: {args.send_metadata_json}\n")
    
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())

