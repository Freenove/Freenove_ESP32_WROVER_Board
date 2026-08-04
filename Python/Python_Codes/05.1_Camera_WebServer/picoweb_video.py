import network
import socket
import time
import gc
from camera import Camera, FrameSize, PixelFormat

cam = Camera(
    frame_size=FrameSize.QQVGA,
    pixel_format=PixelFormat.RGB565,
    xclk_freq=20000000,
    init=True
)

ssid = '********'
password = '********'

station = network.WLAN(network.STA_IF)
station.active(True)
station.connect(ssid, password)

while not station.isconnected():
    time.sleep(1)

ip = station.ifconfig()[0]
print(f'Connected! Open in browser: http://{ip}')

addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen(5)

print('Server running on:', addr)

html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>ESP32 Camera Stream</title>
    <style>
        body {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background-color: #f0f0f0;
            font-family: Arial, sans-serif;
        }
        .video-container {
            text-align: center;
            width: 100%;
            max-width: 1000px;
        }
        canvas {
            width: auto;
            height: auto;
            image-rendering: pixelated;
            border: 2px solid #ccc;
            background-color: #000;
        }
        #status {
            margin-top: 10px;
            font-size: 16px;
            color: #333;
        }
    </style>
</head>
<body>
    <div class="video-container">
        <h1>ESP32 Camera Stream</h1>
        <canvas id="videoCanvas" width="640" height="480"></canvas>
        <div id="status">Connecting to camera...</div>
    </div>

    <script>
        const canvas = document.getElementById('videoCanvas');
        const ctx = canvas.getContext('2d');
        const statusDiv = document.getElementById('status');
        
        function fetchImage() {
            fetch('/frame')
                .then(response => {
                    if (!response.ok) throw new Error('Network request error');
                    return response.arrayBuffer();
                })
                .then(data => {
                    if (!data || data.byteLength === 0) {
                        statusDiv.textContent = 'Error: Empty data received';
                        setTimeout(fetchImage, 500);
                        return;
                    }
                    
                    let uint8Array = new Uint8Array(data);
                    if (data.byteLength % 2 !== 0) {
                        uint8Array = new Uint8Array(data.slice(0, data.byteLength - 1));
                    }
                    
                    const swappedArray = swapRgb565Bytes(uint8Array);
                    const rgb565Array = new Uint16Array(swappedArray.buffer);
                    const rgbaArray = convertRGB565ToRGBA(rgb565Array);
                    
                    const actualPixelCount = rgb565Array.length;
                    
                    let width, height;
                    if (actualPixelCount === 640 * 480) {
                        width = 640; height = 480;
                    } else if (actualPixelCount === 320 * 240) {
                        width = 320; height = 240;
                    } else if (actualPixelCount === 160 * 120) {
                        width = 160; height = 120;
                    } else {
                        width = Math.floor(Math.sqrt(actualPixelCount));
                        while (actualPixelCount % width !== 0 && width > 1) { width--; }
                        height = actualPixelCount / width;
                    }
                    
                    if (canvas.width !== width || canvas.height !== height) {
                        canvas.width = width;
                        canvas.height = height;
                    }
                    
                    const imageData = new ImageData(rgbaArray, width, height);
                    ctx.putImageData(imageData, 0, 0);
                    statusDiv.textContent = `Streaming... Resolution: ${width}x${height}`;
                    
                    setTimeout(fetchImage, 50);
                })
                .catch(error => {
                    console.error('Failed to fetch image:', error);
                    statusDiv.textContent = 'Connection lost, reconnecting...';
                    setTimeout(fetchImage, 1000);
                });
        }
        
        function swapRgb565Bytes(uint8Array) {
            const swapped = new Uint8Array(uint8Array.length);
            for (let i = 0; i < uint8Array.length; i += 2) {
                if (i + 1 < uint8Array.length) {
                    swapped[i] = uint8Array[i + 1];
                    swapped[i + 1] = uint8Array[i];
                } else {
                    swapped[i] = uint8Array[i];
                }
            }
            return swapped;
        }
        
        function convertRGB565ToRGBA(rgb565Array) {
            const length = rgb565Array.length;
            const rgbaArray = new Uint8ClampedArray(length * 4);
            
            for (let i = 0; i < length; i++) {
                const color = rgb565Array[i];
                const r = ((color >> 11) & 0x1F) << 3;
                const g = ((color >> 5) & 0x3F) << 2;
                const b = (color & 0x1F) << 3;
                
                const idx = i * 4;
                rgbaArray[idx] = r;
                rgbaArray[idx + 1] = g;
                rgbaArray[idx + 2] = b;
                rgbaArray[idx + 3] = 255;
            }
            return rgbaArray;
        }
        
        fetchImage();
    </script>
</body>
</html>
"""

def handle_client(client):
    try:
        request = client.recv(1024).decode('utf-8', 'ignore')
        if 'GET /frame' in request:
            frame = cam.capture()
            if frame:
                header = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/octet-stream\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Connection: close\r\n\r\n"
                )
                client.sendall(header.encode('utf-8') + frame)
            else:
                client.sendall(b"HTTP/1.1 500 Internal Server Error\r\n\r\n")
        else:
            header = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                "Connection: close\r\n\r\n"
            )
            client.sendall(header.encode('utf-8') + html.encode('utf-8'))
    finally:
        client.close()

try:
    while True:
        client, addr = s.accept()
        handle_client(client)
except KeyboardInterrupt:
    print("Program stopped")
finally:
    cam.deinit()