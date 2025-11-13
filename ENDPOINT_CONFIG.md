# WebSocket Endpoint Configuration Guide

This guide explains how to easily configure the WebSocket endpoint for use with a real Raspberry Pi.

## Three Ways to Configure Endpoint

### 1. Command Line Argument (Easiest for Testing)

Use `--endpoint` argument to specify the full WebSocket URL:

```bash
# Binary Image Simulator
python drone_binary_image_simulator.py \
    --endpoint "ws://192.168.1.100:3000/ws?type=ingest" \
    --device-id raspberry-pi-1 \
    --camera-id cam-001 \
    --frames-dir P3_VIDEO_frames

# JSON WebSocket Simulator
python drone_websocket_simulator.py \
    --endpoint "ws://192.168.1.100:3000/ws?type=ingest" \
    --center-lat 13.7563 --center-lon 100.5018 \
    --num-drones 1 --interval-s 0.5
```

**Advantages:**
- ✅ Quick and easy for testing
- ✅ No file editing required
- ✅ Can be different for each run

---

### 2. Environment Variable (Best for Raspberry Pi)

Set `WEBSOCKET_ENDPOINT` environment variable once, then use the script normally:

**Linux/Raspberry Pi:**
```bash
# Set in ~/.bashrc or ~/.profile for permanent configuration
export WEBSOCKET_ENDPOINT="ws://192.168.1.100:3000/ws?type=ingest"

# Or set for current session only
export WEBSOCKET_ENDPOINT="ws://192.168.1.100:3000/ws?type=ingest"
python drone_binary_image_simulator.py --device-id pi-1 --camera-id cam-1
```

**Windows:**
```powershell
# Set for current session
$env:WEBSOCKET_ENDPOINT="ws://192.168.1.100:3000/ws?type=ingest"
python drone_binary_image_simulator.py --device-id pi-1 --camera-id cam-1

# Or set permanently (System Properties > Environment Variables)
```

**Advantages:**
- ✅ Set once, use everywhere
- ✅ Good for production Raspberry Pi setup
- ✅ Can be in systemd service or startup script

---

### 3. Edit Code Directly (For Permanent Configuration)

Edit the simulator file and set the `WEBSOCKET_ENDPOINT` variable:

**File:** `drone_binary_image_simulator.py` or `drone_websocket_simulator.py`

**Location:** Around line 74-82

```python
# Default WebSocket endpoint (can be overridden via environment variable or --endpoint argument)
# For Raspberry Pi, set this to your backend server URL, e.g.:
WEBSOCKET_ENDPOINT = "ws://192.168.1.100:3000/ws?type=ingest"  # Uncomment and set your endpoint
# Or use environment variable: export WEBSOCKET_ENDPOINT="ws://your-server:3000/ws?type=ingest"
# WEBSOCKET_ENDPOINT = os.getenv("WEBSOCKET_ENDPOINT", None)  # Comment this line
```

**Advantages:**
- ✅ Hardcoded in script
- ✅ No need to remember command line args
- ✅ Good for dedicated Raspberry Pi scripts

---

## Priority Order

The endpoint is determined in this order (highest priority first):

1. **`--endpoint` command line argument** (highest priority)
2. **`WEBSOCKET_ENDPOINT` environment variable**
3. **Built from `--host`, `--port`, and `--path`** (backward compatibility)

---

## Examples for Raspberry Pi

### Example 1: Production Setup with Environment Variable

**On Raspberry Pi, create startup script:**

```bash
#!/bin/bash
# /home/pi/start_camera.sh

export WEBSOCKET_ENDPOINT="ws://192.168.1.100:3000/ws?type=ingest"
export DEVICE_ID="raspberry-pi-1"
export CAMERA_ID="cam-001"

cd /home/pi/camera_scripts
python drone_binary_image_simulator.py \
    --device-id $DEVICE_ID \
    --camera-id $CAMERA_ID \
    --frames-dir /home/pi/camera_frames \
    --loop
```

### Example 2: Systemd Service

**Create `/etc/systemd/system/camera-sender.service`:**

```ini
[Unit]
Description=Camera Image Sender
After=network.target

[Service]
Type=simple
User=pi
Environment="WEBSOCKET_ENDPOINT=ws://192.168.1.100:3000/ws?type=ingest"
WorkingDirectory=/home/pi/camera_scripts
ExecStart=/usr/bin/python3 /home/pi/camera_scripts/drone_binary_image_simulator.py \
    --device-id raspberry-pi-1 \
    --camera-id cam-001 \
    --frames-dir /home/pi/camera_frames \
    --loop
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl enable camera-sender.service
sudo systemctl start camera-sender.service
```

### Example 3: Quick Test with Command Line

```bash
python drone_binary_image_simulator.py \
    --endpoint "ws://192.168.1.100:3000/ws?type=ingest" \
    --device-id test-pi \
    --camera-id test-cam \
    --frames-dir ./frames \
    --updates 10
```

---

## Finding Your Backend Server IP

**On Raspberry Pi, find backend server:**
```bash
# If backend is on same network
ping backend-hostname

# Or check router admin panel for connected devices
# Or use nmap to scan network
nmap -sn 192.168.1.0/24
```

**Common backend URLs:**
- Local development: `ws://localhost:3000/ws?type=ingest`
- Same network: `ws://192.168.1.100:3000/ws?type=ingest`
- Remote server: `ws://your-domain.com:3000/ws?type=ingest`
- With SSL: `wss://your-domain.com/ws?type=ingest`

---

## Troubleshooting

### Connection Refused
- Check backend server is running
- Verify IP address and port are correct
- Check firewall settings

### Wrong Endpoint Format
- Must start with `ws://` or `wss://`
- Include full path: `/ws?type=ingest`
- No trailing slash

### Environment Variable Not Working
- Check variable is set: `echo $WEBSOCKET_ENDPOINT`
- Make sure no spaces around `=`
- Restart terminal/session after setting

---

## Quick Reference

```bash
# Method 1: Command line
--endpoint "ws://192.168.1.100:3000/ws?type=ingest"

# Method 2: Environment variable
export WEBSOCKET_ENDPOINT="ws://192.168.1.100:3000/ws?type=ingest"

# Method 3: Edit code
WEBSOCKET_ENDPOINT = "ws://192.168.1.100:3000/ws?type=ingest"
```

