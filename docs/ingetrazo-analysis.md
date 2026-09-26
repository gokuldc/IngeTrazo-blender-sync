# IngeTrazo Architecture & Integration Analysis

This report details the internal architecture of IngeTrazo, based on a direct inspection of its source code, and outlines the required integration points for the IngeTrazo ↔ Blender synchronization bridge.

## 1. IngeTrazo architecture
- **Language**: Python (3.10+)
- **GUI Framework**: PySide6 (Qt for Python) with OpenGL 3.3 Core for the viewport.
- **Entry Point**: `vendor/ingetrazo/main.py`
- **Package System**: Standard `pip` dependencies (`requirements.txt`), packaged via PyInstaller and AppImage.
- **Document Architecture**: The document is represented by `core.scene.Scene` (`vendor/ingetrazo/core/scene.py`). It holds the root `mesh` (loose geometry) and a list of `groups` (encapsulated components). It also tracks `layers`, `materials`, `dimensions`, etc.
- **Application Lifecycle**: Managed by `main.py` and `views/main_window.py`. Supports single-instance mode via local sockets.

## 2. Plugin system
- **Discovery**: Handled by `vendor/ingetrazo/core/extensions.py`. Plugins are loaded by path from `<app_root>/plugins/` and `%APPDATA%/ingetrazo/plugins` (or XDG equivalent).
- **Manifests**: No explicit manifest file. A plugin is a Python module or package (e.g. `x.py` or `x/__init__.py`).
- **Registration**: Plugins expose `setup(app)` (receiving a `views.extension_api.ExtensionApp`) and subclass `tools.base.Tool`. The system imports modules safely off `sys.path`.
- **UI Extension**: Handled in `setup(app)` where side panels and viewport overlays can be added.
- **Examples**: `vendor/ingetrazo/plugins/ai_bridge.py` and `plugins/model_info.py`.

## 3. Scene/model representation
- **Scene**: `core.scene.Scene` is the root container.
- **Groups/Components**: `core.group.Group` (`vendor/ingetrazo/core/group.py`). A group isolates geometry into its own `Mesh`. A group can be a component instance if `group.xform` is set (a shared prototype mesh). `group.children` holds nested placements.
- **Loose Geometry**: Stored in `scene.mesh`. Tools and commands edit the loose mesh or the mesh of the currently open group (`scene.edit_group`).

## 4. Geometry representation
- **Data Structures**: Found in `vendor/ingetrazo/core/mesh.py`. IngeTrazo uses a half-edge style shared-vertex topology.
- **Classes**: `Vertex`, `Edge`, `Face`, `Mesh`.
- **Vertices**: `QVector3D` positions. Points within `1e-4` tolerance are welded into a shared `Vertex`.
- **Faces**: Defined by a boundary `loop` of `Vertex` objects and optional `hole_loops`. Faces carry metadata in a dictionary: `face.attrs`.
- **Transforms**: Stored as `QMatrix4x4` on component instances (`group.xform`). Classic groups bake transforms into world coordinates.

## 5. Object identity
- **Groups**: `core.group.Group` has a persistent, generated `uuid4().hex[:16]` stored in `group.uid`. This survives saving, loading, and is duplicated correctly.
- **Faces/Edges**: Loose geometry does not have inherent stable UUIDs unless they are tagged with BIM metadata (`face.attrs["ifc"]["id"]`).
- **Conclusion**: We will use `group.uid` for synchronizing groups/components. For loose geometry, we may need to group them first or use their BIM tags if present. We should avoid creating a second UUID system for groups.

## 6. Change/event mechanism
- **Tracking**: `core.scene.Scene` has an integer `version` property that increments on every mutation (`self.version += 1`).
- **Signals**: `views/viewport.py` tracks changes and emits `self.sceneVersionChanged.emit(self.scene.version)`.
- **Integration**: Polling `scene.version` is extremely cheap, but we can also hook into `viewport.sceneVersionChanged` signal to detect when the user modifies the scene.

## 7. Material system
- **Registry**: `core.materials.Material` (`vendor/ingetrazo/core/materials.py`) defines named materials (`name`, `color`, `texture`, `opacity`). The `Scene` stores these in `scene.materials` (a dict mapping name to `Material`).
- **Face Assignment**: Faces store the material name via `face.attrs["mat"] = "Name"`. The actual render properties (`color`, `texture`, `opacity`) are *baked* into `face.attrs` so they render even if the material is missing from the registry.

## 8. BIM system
- **Mechanism**: `vendor/ingetrazo/core/bim.py`. BIM is implemented as metadata on selected geometry.
- **Storage**: Groups store `group.ifc = {"class": "IfcWall", "name": ...}`. Loose faces store `face.attrs["ifc"] = {"id": 123, "class": "IfcWall", "name": ...}`.

## 9. Existing network/AI bridge
- **AI Bridge**: `vendor/ingetrazo/plugins/ai_bridge.py`.
- **Networking**: Implements a localhost TCP socket server (`socket.SOCK_STREAM`) on port 4763.
- **Protocol**: Newline-delimited JSON.
- **Threading**: The server runs in a daemon `threading.Thread`. Requests are passed to the Qt Main Thread via `self._dispatch.emit(job)` (a `Signal(object)` connected via `Qt.QueuedConnection`).

## 10. Threading/main-thread requirements
- **Requirement**: All scene mutations and Qt GUI operations MUST occur on the main Qt thread.
- **Pattern**: The network layer should run in a background thread and use Qt Signals (`Qt.QueuedConnection`) or `QTimer` to schedule updates on the main thread, exactly as `ai_bridge.py` does.

## 11. Relevant source files/classes
- `core/scene.py` -> `Scene`
- `core/group.py` -> `Group`
- `core/mesh.py` -> `Mesh`, `Face`, `Edge`, `Vertex`
- `core/materials.py` -> `Material`
- `core/extensions.py` -> Plugin loading
- `plugins/ai_bridge.py` -> TCP Server & Threading example
- `views/viewport.py` -> Viewport state & Signals (`sceneVersionChanged`)

## 12. Recommended integration points
- **Plugin Entry**: Create a directory `plugins/blender_sync/` with `__init__.py` exposing `setup(app)` and a `Tool` subclass for the UI toggle.
- **Network**: Use a background thread with an `asyncio` WebSocket server or a plain TCP socket for JSON message passing.
- **Event Hook**: Connect to `app.viewport.sceneVersionChanged` to trigger diffing/synchronization.
- **Diffing**: Since `sceneVersionChanged` only says "something changed", the plugin will need to snapshot `scene.groups` by `uid` and detect creations/updates/deletions.

## 13. API stability concerns
- Geometry is manipulated via `scene.mesh.add_edge()` and `scene.mesh.add_face()`. `Group.mesh` mutations also bump versions.
- The `Group` API separates "classic groups" (baked coordinates) from "components" (instances with `xform`). We must handle `iter_placements()` properly.

## 14. Proposed synchronization architecture
1. **IngeTrazo Plugin (`blender_sync`)**:
   - Runs a TCP JSON server on localhost.
   - Listens to `app.viewport.sceneVersionChanged`.
   - On change, diffs `scene.groups` (via `group.uid`) to find added/modified/removed groups.
   - Converts IngeTrazo geometry to a JSON payload.
2. **Blender Add-on**:
   - Connects to localhost TCP server.
   - Modifies Blender scene using `bpy` on the main thread via timer/queue.
   - Stores `ingetrazo_uuid` in object custom properties.

## 15. Unknowns/risks
- **Loose Geometry**: `Scene.mesh` contains loose faces that do not have `uid`s. Synchronizing loose geometry incrementally is hard without stable IDs. We may need to synchronize the *entire* loose mesh as a single Blender object, or encourage the user to group geometry in IngeTrazo before syncing.
- **Performance**: Serializing large meshes to JSON on the main thread might block the UI. We need to optimize the extraction of vertices/faces.
