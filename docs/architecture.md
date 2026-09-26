# Synchronization Architecture

## Overview
The synchronization bridge connects **IngeTrazo** (the authoritative architectural model) with **Blender** (the visualization model).

```text
                  IngeTrazo
                      │
                IngeTrazo Plugin (Server)
                      │
                Sync Protocol (TCP/JSON)
                      │
              localhost connection
                      │
                      ▼
                Blender Add-on (Client)
                      │
                    bpy
                      │
                      ▼
                   Blender
```

## Component 1: IngeTrazo Plugin (`blender_sync`)
The IngeTrazo plugin acts as the TCP server.
- **Location**: It will be installed in `plugins/blender_sync/`.
- **UI**: Exposes an Extensions menu entry to start/stop the server.
- **Server**: Runs on a background daemon thread, listening on `127.0.0.1:8765`.
- **Change Detection**: Connects to the main `viewport.sceneVersionChanged` signal via a Qt connection. Whenever the scene version bumps, it calculates a diff of the scene.
- **Diffing Mechanism**:
  - Maintains a dictionary of previously synced groups by their `uid`.
  - On change, it iterates `scene.groups`. If a `uid` is new or its geometry/transform has changed, it emits an `object_update`.
  - If a previously known `uid` is no longer in `scene.groups`, it emits an `object_delete`.
  - The `scene.loose_mesh` (geometry not inside a group) is treated as a single special object with a fixed UUID (e.g., `loose-geometry-0000`).

## Component 2: Blender Add-on (`ingetrazo_sync.py`)
The Blender add-on connects to the IngeTrazo server and translates the protocol into `bpy` actions.
- **UI**: A panel in the 3D Viewport sidebar (`N` panel) under "IngeTrazo Sync".
- **Client**: Connects to the TCP socket on a background thread. Reads JSON messages and places them in a `queue.Queue`.
- **Main Thread Execution**: A modal operator or an `app.timers` callback dequeues messages and updates the Blender scene. This is required because `bpy` cannot be safely mutated from a background thread.
- **Object Identity**: Synchronized objects receive custom properties:
  - `obj["ingetrazo_uuid"]` = IngeTrazo UID
  - `obj["ingetrazo_sync"]` = True
- **Geometry Update**: When an `object_update` arrives, the add-on finds the Blender object by `ingetrazo_uuid`. If found, it updates its location and replaces its mesh data block (or modifies it). If not found, it creates a new object.
- **Blender-only Objects**: Objects without `ingetrazo_uuid` are strictly ignored. This allows users to safely populate the scene with vegetation, lights, and cameras.

## Materials & Metadata
- Materials are sent as `material_update` messages. Blender matches them by name or ID.
- BIM metadata from `ifc` attributes are injected into Blender custom properties, e.g. `obj["ifc_class"] = "IfcWall"`.

## Threading
- **IngeTrazo**: Main thread handles drawing/GUI. Network runs in a daemon thread. State extraction runs on the main thread when `sceneVersionChanged` triggers, safely putting the payload into a thread-safe queue to be sent over TCP.
- **Blender**: Network runs in a daemon thread. Scene mutation happens via `bpy.app.timers` running on Blender's main thread.
