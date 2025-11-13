# Binary Image Frame Simulator

This simulator sends actual binary image files (PNG/JPEG) through WebSocket to test the new binary image frame support in the backend.

## Installation

```bash
pip install websockets
```

## Usage

### Basic Example

Send images from the `P3_VIDEO_frames` directory:

```bash
python drone_binary_image_simulator.py \
    --host localhost --port 3000 \
    --device-id raspberry-pi-1 \
    --camera-id cam-001 \
    --frames-dir P3_VIDEO_frames \
    --interval-s 0.5
```

### Send Specific Number of Frames

```bash
python drone_binary_image_simulator.py \
    --host localhost --port 3000 \
    --device-id pi-1 --camera-id cam-1 \
    --frames-dir P3_VIDEO_frames \
    --updates 10 \
    --interval-s 0.3
```

### Send Metadata via JSON First

If you want to send metadata as a JSON message before sending binary images:

```bash
python drone_binary_image_simulator.py \
    --host localhost --port 3000 \
    --device-id pi-1 --camera-id cam-1 \
    --frames-dir P3_VIDEO_frames \
    --send-metadata-json \
    --interval-s 0.5
```

### Loop Through Images Continuously

```bash
python drone_binary_image_simulator.py \
    --host localhost --port 3000 \
    --device-id pi-1 --camera-id cam-1 \
    --frames-dir P3_VIDEO_frames \
    --loop \
    --interval-s 0.5
```

## Parameters

**Connection:**
- `--host`: WebSocket server hostname (default: localhost)
- `--port`: WebSocket server port (default: 3000)

**Metadata:**
- `--device-id`: Device identifier (default: sim-device-1)
- `--camera-id`: Camera identifier (default: sim-camera-1)

**Image Source:**
- `--frames-dir`: Directory containing image files (PNG/JPEG) (default: P3_VIDEO_frames)

**Sending Options:**
- `--interval-s`: Seconds between frames (default: 0.5)
- `--updates`: Total frames to send (0 = send all images once, default: 0)
- `--loop`: Loop through images continuously
- `--send-metadata-json`: Send metadata as JSON message before images
- `--verbose`: Show detailed acknowledgments

## How It Works

1. **Metadata in Query String** (default):
   - Connects to: `ws://host:port/ws?type=ingest&device_id=xxx&camera_id=xxx`
   - Sends binary images directly

2. **Metadata via JSON Message**:
   - Connects to WebSocket
   - Sends JSON metadata message first: `{"type": "metadata", "device_id": "...", "camera_id": "...", "timestamp": "..."}`
   - Then sends binary images

3. **Backend Processing**:
   - Backend detects binary image (JPEG/PNG)
   - Saves to database with metadata
   - Caches latest frame
   - Forwards to frontend via WebSocket

## Testing

1. **Start Backend:**
   ```bash
   cd Backend_Tesa
   npm run dev
   ```

2. **Run Simulator:**
   ```bash
   cd Simulationsend_socket
   python drone_binary_image_simulator.py \
       --host localhost --port 3000 \
       --device-id test-pi-1 \
       --camera-id test-cam-1 \
       --frames-dir P3_VIDEO_frames \
       --updates 5 \
       --interval-s 0.5
   ```

3. **Check Backend Logs:**
   - Look for: `📸 Received binary image frame`
   - Look for: `🖼️ Saved binary image frame`
   - Look for: `✅ ACK` messages

4. **Check Frontend:**
   - Connect frontend to: `ws://localhost:3000/ws`
   - Frontend should receive binary image frames

## Notes

- Images are sent as raw binary data (no encoding)
- Backend automatically detects JPEG/PNG format
- Metadata can come from query string or JSON message
- Each image is saved to database with device_id, camera_id, and timestamp
- Latest frame is cached in memory for fast access

