#!/usr/bin/env python3
"""
Simulate drone data and send via WebSocket to the backend server.

This simulator connects to the WebSocket ingest endpoint and sends frame data
in the same format as the MQTT simulator, but over WebSocket instead.

WebSocket endpoint: ws://localhost:3000/ws/ingest

Frame structure format:
{
    "fram_id": "string",
    "cam_id": "string",
    "token_id": "string",  # Just the token string - backend will fetch camera_info from API
    "timestamp": "ISO string",
    "image_info": {
        "width": int,
        "height": int
    },
    "objects": [
        {
            "obj_id": "string",
            "type": "string",
            "lat": float,
            "lng": float,
            "alt": float,
            "speed_kt": float
        }
    ]
}

Examples:
    # Basic test with 5 frames
    python drone_websocket_simulator.py \
        --host localhost --port 3000 \
        --center-lat 13.7563 --center-lon 100.5018 \
        --num-drones 2 --interval-s 0.5 --radius-m 120 \
        --cam-id e8a76237-df96-4a6a-9375-baa4d74f5f12 \
        --token 257c87b4-9469-44fe-9132-8937f69723bd \
        --updates 5

    # Continuous mode (default)
    python drone_websocket_simulator.py \
        --host localhost --port 3000 \
        --center-lat 13.7563 --center-lon 100.5018 \
        --num-drones 1 --interval-s 1.0 --radius-m 120
"""

import argparse
import asyncio
import json
import math
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple, Optional

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        # Fallback for older Python versions
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


METERS_PER_DEGREE_LAT = 111_320.0

IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080
VIEW_HALF_WIDTH_M = 600.0  # how many meters from center map to screen edge (internal only)


def meters_per_degree_lon(latitude_deg: float) -> float:
    """Approximate meters per degree of longitude at a given latitude."""
    cos_lat = max(1e-12, abs(math.cos(math.radians(latitude_deg))))
    return METERS_PER_DEGREE_LAT * cos_lat


def position_on_circle(
    center_lat: float, center_lon: float, radius_m: float, angle_rad: float
) -> Tuple[float, float]:
    """
    Compute latitude/longitude for a point on a circle around a center.
    Angle is measured from east and increases counter-clockwise.
    """
    delta_lat = (radius_m * math.sin(angle_rad)) / METERS_PER_DEGREE_LAT
    delta_lon = (radius_m * math.cos(angle_rad)) / meters_per_degree_lon(center_lat)
    return center_lat + delta_lat, center_lon + delta_lon


def latlon_to_m_offsets(
    lat: float, lon: float, center_lat: float, center_lon: float
) -> Tuple[float, float]:
    """Return (dx_east_m, dy_north_m) from center."""
    dy_north_m = (lat - center_lat) * METERS_PER_DEGREE_LAT
    dx_east_m = (lon - center_lon) * meters_per_degree_lon(center_lat)
    return dx_east_m, dy_north_m


def clamp(v: float, vmin: float, vmax: float) -> float:
    return max(vmin, min(vmax, v))


def compute_bbox_and_conf(
    dx_east_m: float, dy_north_m: float, current_speed_mps: float
) -> Tuple[Tuple[int, int, int, int], float]:
    """
    Compute a plausible bbox and confidence based on distance and speed.
    Returns ((x, y, w, h), confidence).
    """
    # Project meters to pixels (simple linear screen model)
    px_per_m_x = (IMAGE_WIDTH / 2) / VIEW_HALF_WIDTH_M
    px_per_m_y = (IMAGE_HEIGHT / 2) / VIEW_HALF_WIDTH_M

    x_center = (IMAGE_WIDTH / 2) + dx_east_m * px_per_m_x + random.gauss(0.0, 5.0)
    y_center = (IMAGE_HEIGHT / 2) - dy_north_m * px_per_m_y + random.gauss(0.0, 5.0)

    distance_m = math.hypot(dx_east_m, dy_north_m)

    # Size shrinks with distance, plus noise
    width_px = 12_000.0 / (distance_m + 50.0) + random.gauss(0.0, 5.0)
    width_px = clamp(width_px, 12.0, 240.0)
    height_px = width_px * 0.66

    # Convert center->top-left, clamp to screen
    x = int(clamp(x_center - width_px / 2.0, 0.0, IMAGE_WIDTH - width_px))
    y = int(clamp(y_center - height_px / 2.0, 0.0, IMAGE_HEIGHT - height_px))
    w = int(min(width_px, IMAGE_WIDTH - x))
    h = int(min(height_px, IMAGE_HEIGHT - y))

    # Confidence model: base - size penalties - speed penalty + jitter
    base = 0.85
    size_penalty = 0.0
    if w < 30:
        size_penalty += 0.15
    if w > 180:
        size_penalty += 0.07
    speed_penalty = clamp((current_speed_mps - 6.0) * 0.02, 0.0, 0.15)
    jitter = random.uniform(-0.05, 0.05)
    confidence = clamp(base - size_penalty - speed_penalty + jitter, 0.30, 0.98)

    return (x, y, w, h), round(confidence, 2)


@dataclass
class DroneState:
    drone_id: str
    type: str
    motion: str  # "circle" | "straight"
    angle_rad: float  # used for circle
    bearing_rad: float  # used for straight
    radius_m: float
    speed_base_mps: float
    lat: float  # only used/updated for straight
    lon: float  # only used/updated for straight
    base_alt_m: float
    wobble_m: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish simulated drone data via WebSocket.")

    # Connection
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Full WebSocket endpoint URL (e.g., ws://192.168.1.100:3000/ws?type=ingest). "
             "If provided, --host, --port, and --path are ignored. "
             "Can also be set via WEBSOCKET_ENDPOINT environment variable."
    )
    parser.add_argument("--host", default="localhost", help="WebSocket server hostname or IP (used if --endpoint not provided).")
    parser.add_argument("--port", type=int, default=3000, help="WebSocket server port (used if --endpoint not provided).")
    parser.add_argument("--path", default="/ws/ingest", help="WebSocket path (default: /ws/ingest, used if --endpoint not provided).")

    # Scene
    parser.add_argument("--center-lat", type=float, required=True, help="Latitude of scene center.")
    parser.add_argument("--center-lon", type=float, required=True, help="Longitude of scene center.")
    parser.add_argument("--interval-s", type=float, default=0.5, help="Seconds between published updates.")
    parser.add_argument("--updates", type=int, default=0, help="Total updates to send (0 = run continuously).")

    # Motion params
    parser.add_argument("--radius-m", type=float, default=120.0, help="Base orbit radius for circle motion.")
    parser.add_argument("--altitude-m", type=float, default=120.0, help="Base altitude in meters.")
    parser.add_argument("--altitude-wobble-m", type=float, default=8.0, help="Altitude variation amplitude in meters.")

    # Frames mode params
    parser.add_argument("--num-drones", type=int, default=1, help="How many drones per frame.")
    parser.add_argument(
        "--speed-range-kt",
        type=float,
        nargs=2,
        metavar=("MIN", "MAX"),
        default=[6.0, 24.0],
        help="Speed range for drones in knots (min max).",
    )
    parser.add_argument("--noise-level-m", type=float, default=3.0, help="GPS jitter standard deviation in meters.")
    parser.add_argument("--miss-rate", type=float, default=0.10, help="Probability per frame to miss a real drone.")
    parser.add_argument(
        "--false-positive-rate",
        type=float,
        default=0.03,
        help="Probability per frame to add a false detection.",
    )
    parser.add_argument("--cam-id", default="e8a76237-df96-4a6a-9375-baa4d74f5f12", help="Camera identifier.")
    parser.add_argument("--token", default="257c87b4-9469-44fe-9132-8937f69723bd", help="Camera token for API authentication.")
    parser.add_argument("--show-responses", action="store_true", help="Show server responses (ack/error messages).")

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> bool:
    if args.interval_s <= 0:
        print("Update interval must be greater than zero.", file=sys.stderr)
        return False
    if args.radius_m <= 0:
        print("Orbit radius must be greater than zero.", file=sys.stderr)
        return False
    if args.num_drones < 1:
        print("num-drones must be >= 1.", file=sys.stderr)
        return False
    if len(args.speed_range_kt) != 2 or args.speed_range_kt[0] <= 0 or args.speed_range_kt[0] > args.speed_range_kt[1]:
        print("speed-range-kt must be two numbers: MIN > 0 and MIN <= MAX.", file=sys.stderr)
        return False
    if not (0.0 <= args.miss_rate < 1.0):
        print("miss-rate must be in [0, 1).", file=sys.stderr)
        return False
    if not (0.0 <= args.false_positive_rate < 1.0):
        print("false-positive-rate must be in [0, 1).", file=sys.stderr)
        return False
    return True


def init_frames_states(args: argparse.Namespace) -> List[DroneState]:
    states: List[DroneState] = []
    # Convert knots to m/s for internal calculations (1 knot = 0.514444 m/s)
    KNOTS_TO_MPS = 0.514444
    speed_min_kt, speed_max_kt = args.speed_range_kt
    speed_min = speed_min_kt * KNOTS_TO_MPS
    speed_max = speed_max_kt * KNOTS_TO_MPS

    for i in range(args.num_drones):
        drone_id = f"sim-{i + 1}"
        motion = "circle" if random.random() < 0.6 else "straight"
        speed_base = random.uniform(speed_min, speed_max)
        wobble = args.altitude_wobble_m
        typ = "unknown"

        # random small start offset near center (0..25% of radius)
        start_r = random.uniform(0.0, args.radius_m * 0.25)
        start_theta = random.uniform(0.0, 2 * math.pi)
        offset_lat = (start_r * math.sin(start_theta)) / METERS_PER_DEGREE_LAT
        offset_lon = (start_r * math.cos(start_theta)) / meters_per_degree_lon(args.center_lat)
        start_lat = args.center_lat + offset_lat
        start_lon = args.center_lon + offset_lon

        if motion == "circle":
            angle_rad = random.uniform(0.0, 2 * math.pi)
            bearing_rad = 0.0
            radius = random.uniform(args.radius_m * 0.7, args.radius_m * 1.3)
        else:
            angle_rad = 0.0
            bearing_rad = random.uniform(0.0, 2 * math.pi)
            radius = args.radius_m

        states.append(
            DroneState(
                drone_id=drone_id,
                type=typ,
                motion=motion,
                angle_rad=angle_rad,
                bearing_rad=bearing_rad,
                radius_m=radius,
                speed_base_mps=speed_base,
                lat=start_lat,
                lon=start_lon,
                base_alt_m=args.altitude_m,
                wobble_m=wobble,
            )
        )
    return states


async def frames_loop(ws: WebSocketClientProtocol, args: argparse.Namespace) -> int:
    states = init_frames_states(args)
    frame_id = 0
    dt = args.interval_s
    updates_remaining = args.updates if args.updates > 0 else None
    KNOTS_TO_MPS = 0.514444  # Conversion factor

    # Print startup info
    print(f"\n🚀 Starting drone WebSocket simulator")
    if args.endpoint:
        print(f"   Endpoint: {args.endpoint}")
    elif WEBSOCKET_ENDPOINT:
        print(f"   Endpoint: {WEBSOCKET_ENDPOINT} (from environment)")
    else:
        print(f"   Server: ws://{args.host}:{args.port}{args.path}")
    print(f"   Camera ID: {args.cam_id}")
    print(f"   Token: {args.token[:8]}...")
    print(f"   Drones: {args.num_drones}")
    print(f"   Interval: {args.interval_s}s")
    print(f"   Updates: {'continuous' if updates_remaining is None else updates_remaining}")
    print(f"   Center: ({args.center_lat}, {args.center_lon})")
    print(f"\n📡 Sending frames... (Press Ctrl+C to stop)\n")

    try:
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

        while updates_remaining is None or updates_remaining > 0:
            objects = []
            now_iso = datetime.now(timezone.utc).isoformat()

            for st in states:
                # base speed with small per-frame noise (in m/s for calculations)
                current_speed_mps = st.speed_base_mps * random.uniform(0.9, 1.1)
                current_speed_kt = current_speed_mps / KNOTS_TO_MPS  # Convert to knots

                # update position
                if st.motion == "circle":
                    st.angle_rad = (st.angle_rad + (current_speed_mps / st.radius_m) * dt) % (2 * math.pi)
                    lat, lon = position_on_circle(args.center_lat, args.center_lon, st.radius_m, st.angle_rad)
                else:
                    delta_north_m = current_speed_mps * dt * math.cos(st.bearing_rad)
                    delta_east_m = current_speed_mps * dt * math.sin(st.bearing_rad)
                    st.lat = st.lat + (delta_north_m / METERS_PER_DEGREE_LAT)
                    st.lon = st.lon + (delta_east_m / meters_per_degree_lon(st.lat))
                    lat, lon = st.lat, st.lon

                # GPS noise (meters -> degrees)
                if args.noise_level_m > 0.0:
                    noise_north_m = random.gauss(0.0, args.noise_level_m)
                    noise_east_m = random.gauss(0.0, args.noise_level_m)
                    lat += noise_north_m / METERS_PER_DEGREE_LAT
                    lon += noise_east_m / meters_per_degree_lon(lat)

                # altitude wobble
                t = time.time()
                wobble_phase = st.angle_rad if st.motion == "circle" else t
                base_wobble = st.wobble_m * math.sin(wobble_phase)
                random_alt_variation = random.uniform(-2.0, 2.0)
                alt = st.base_alt_m + base_wobble + random_alt_variation

                # missed detection?
                if random.random() < args.miss_rate:
                    pass  # skip this object this frame
                else:
                    objects.append(
                        {
                            "obj_id": st.drone_id,
                            "type": st.type,
                            "lat": round(lat, 7),
                            "lng": round(lon, 7),
                            "alt": round(alt, 2),
                            "speed_kt": round(current_speed_kt, 2),
                        }
                    )

            # false positive(s)
            if random.random() < args.false_positive_rate:
                dx = random.uniform(-VIEW_HALF_WIDTH_M, VIEW_HALF_WIDTH_M)
                dy = random.uniform(-VIEW_HALF_WIDTH_M, VIEW_HALF_WIDTH_M)
                lat_fp = args.center_lat + (dy / METERS_PER_DEGREE_LAT)
                lon_fp = args.center_lon + (dx / meters_per_degree_lon(args.center_lat))
                speed_fp_mps = random.uniform(0.0, 2.0)
                speed_fp_kt = speed_fp_mps / KNOTS_TO_MPS
                objects.append(
                    {
                        "obj_id": f"fp-{uuid.uuid4().hex[:6]}",
                        "type": "unknown",
                        "lat": round(lat_fp, 7),
                        "lng": round(lon_fp, 7),
                        "alt": round(args.altitude_m + random.uniform(-5.0, 5.0), 2),
                        "speed_kt": round(speed_fp_kt, 2),
                    }
                )

            # Frame payload
            payload = {
                "fram_id": str(frame_id),
                "cam_id": args.cam_id,
                "token_id": args.token,  # Just the token string - backend will fetch camera_info from API
                "timestamp": now_iso,
                "image_info": {
                    "width": IMAGE_WIDTH,
                    "height": IMAGE_HEIGHT,
                },
                "objects": objects,
            }

            payload_json = json.dumps(payload)
            await ws.send(payload_json)

            # Print status every 10 frames or on first frame
            if frame_id % 10 == 0 or frame_id == 0:
                print(f"📤 Frame {frame_id}: Sent {len(objects)} objects")

            # Try to receive response (non-blocking)
            if args.show_responses:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=0.1)
                    response_data = json.loads(response)
                    msg_type = response_data.get("type", "unknown")
                    if msg_type == "ack":
                        print(f"   ✅ ACK: {response_data.get('message', '')} (fram_id: {response_data.get('fram_id', 'N/A')})")
                    elif msg_type == "error":
                        print(f"   ❌ ERROR: {response_data.get('error', 'Unknown error')}")
                except asyncio.TimeoutError:
                    pass  # No response yet, continue
                except json.JSONDecodeError:
                    pass  # Not JSON, ignore

            frame_id += 1
            if updates_remaining:
                updates_remaining -= 1
            await asyncio.sleep(dt)

    except KeyboardInterrupt:
        print(f"\n\n⏹️  Stopped by user.")
        print(f"   Total frames sent: {frame_id}")
    except websockets.exceptions.ConnectionClosed:
        print(f"\n\n⚠️  Connection closed by server.")
        print(f"   Total frames sent: {frame_id}")
    except Exception as e:
        print(f"\n\n❌ Error: {e}", file=sys.stderr)
        return 1

    return 0


async def main_async(args: argparse.Namespace) -> int:
    """Main async function."""
    # Determine WebSocket URI
    if args.endpoint:
        # Use provided endpoint directly
        uri = args.endpoint
    elif WEBSOCKET_ENDPOINT:
        # Use endpoint from environment variable
        uri = WEBSOCKET_ENDPOINT
    else:
        # Build URI from host/port/path (backward compatibility)
        # Use /ws with ?type=ingest query parameter for data ingestion
        path = args.path if args.path != "/ws/ingest" else "/ws?type=ingest"
        uri = f"ws://{args.host}:{args.port}{path}"
    
    try:
        print(f"🔌 Connecting to {uri}...")
        async with websockets.connect(uri) as ws:
            return await frames_loop(ws, args)
    except OSError as exc:
        print(f"❌ Failed to connect to {uri} ({exc}).", file=sys.stderr)
        print(f"   Make sure the server is running and accessible", file=sys.stderr)
        return 1
    except websockets.exceptions.InvalidURI:
        print(f"❌ Invalid WebSocket URI: {uri}", file=sys.stderr)
        return 1


def main() -> int:
    args = parse_args()
    if not validate_args(args):
        return 2

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())

