# IngeTrazo ↔ Blender Live Sync

## What this project does
Provides a live, one-way synchronization bridge from IngeTrazo (architectural model) to Blender (visualization layer). You can model architecture in IngeTrazo and have the geometry, groups, and BIM metadata appear instantly in Blender for rendering, lighting, and asset population.

## Supported IngeTrazo version
- Tested against the IngeTrazo 2026 branch (PySide6 / OpenGL 3.3 Core).

## Supported Blender version
- Blender 3.6.0+ (requires Python 3.10+ compatible `bpy` API).

## Installation

### Running IngeTrazo sync
1. Copy the `ingetrazo_plugin/blender_sync.py` file to your IngeTrazo plugins folder:
   - Windows: `%APPDATA%/ingetrazo/plugins/`
   - Linux: `~/.local/share/ingetrazo/plugins/`
2. Start IngeTrazo.
3. Open the **Extensions** menu and click **Blender Live Sync**.
4. The status bar will show "Blender Sync listening on 127.0.0.1:47634".

### Installing Blender addon
1. In Blender, go to **Edit > Preferences > Add-ons**.
2. Click **Install...** and select the `blender_addon/ingetrazo_sync.py` file.
3. Enable the "IngeTrazo Sync" add-on.

## Connecting
1. Ensure the IngeTrazo sync server is running.
2. In Blender's 3D Viewport, open the Sidebar (`N` key).
3. Select the **IngeTrazo** tab.
4. Leave the host at `127.0.0.1` and port at `47634`.
5. Click **Connect**.
6. The scene will immediately sync. Any future changes in IngeTrazo will appear in Blender live.

## Architecture
See [docs/architecture.md](docs/architecture.md) for details on how the IngeTrazo TCP server and Blender operator interact safely with their respective main threads.

## Protocol
See [docs/protocol.md](docs/protocol.md) for the JSON TCP protocol specification.

## Current limitations
- **One-way sync**: Changes in Blender do not sync back to IngeTrazo yet.
- **Loose geometry**: All ungrouped faces are sent as a single "Loose Geometry" object.
- **Holes in faces**: Blender MVP does not currently triangulate n-gons with holes, these may need manual fixing in Blender if they occur.

## Development
To work on the project, you can symlink the plugin and addon files directly to their respective application folders.
```bash
# Example
ln -s $(pwd)/ingetrazo_plugin/blender_sync.py ~/.local/share/ingetrazo/plugins/
```

## Testing
Run the Python unit tests for the protocol:
```bash
python -m unittest discover tests/
```

## Roadmap
- [x] Initial TCP Bridge MVP
- [x] Group/Component Geometry Sync
- [x] Material properties sync (Color, Texture, Opacity)
- [x] Support for native Blender collection organization based on IFC tags
- [x] Two-way synchronization (Blender transformations -> IngeTrazo)
