# IngeTrazo ↔ Blender Sync Protocol

This document defines the JSON-based TCP protocol used to synchronize IngeTrazo's architectural model with Blender.

## Overview
The protocol uses newline-delimited JSON over a TCP connection (default port: 47634, localhost only).

Each message is a single JSON object followed by `\n`.

## Message Structure
All messages must include a `message` type, a `protocol` identifier, and a `version`. Revisions are used to ensure ordering.

```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "<message_type>",
  "revision": 42
}
```

## Handshake
When Blender connects, it expects a handshake.

**Blender → IngeTrazo:**
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "hello",
  "client": "blender-addon"
}
```

**IngeTrazo → Blender:**
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "hello_ack",
  "revision": 120
}
```

## Scene Synchronization
To synchronize a full scene (e.g. on connection), the server sends a `sync_begin`, followed by objects and materials, and finally a `sync_end`.

**IngeTrazo → Blender:**
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "sync_begin",
  "revision": 121
}
```
*(Followed by `object_update` and `material_update` messages)*

```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "sync_end",
  "revision": 121
}
```

## Object Updates
An object in this context is primarily a `core.group.Group` from IngeTrazo, identified by its `uid`.

**IngeTrazo → Blender:**
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "object_update",
  "revision": 122,
  "object": {
    "id": "uuid-string",
    "name": "Wall 01",
    "type": "group",
    "transform": [1.0, 0.0, 0.0, 0.0, ...], 
    "geometry": {
      "vertices": [[x, y, z], ...],
      "faces": [[v0, v1, v2, ...], ...],
      "uvs": [[[u, v], [u, v], ...], ...],
      "materials": [
        {
          "name": "Wood",
          "color": [0.8, 0.4, 0.2],
          "opacity": 1.0,
          "texture_path": "/absolute/path/to/texture.jpg"
        },
        ...
      ],
      "face_materials": [0, 0, 1, 0, ...]
    },
    "metadata": {
      "ifc": {
        "class": "IfcWall",
        "name": "Interior Wall"
      },
      "layer": "Layer0"
    }
  }
}
```
*Note: `transform` is a 16-element array (column-major QMatrix4x4).*

**IngeTrazo → Blender:**
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "object_delete",
  "revision": 123,
  "object": {
    "id": "uuid-string"
  }
}
```

## Client Updates (Two-way sync)
Blender can send transformations back to IngeTrazo when objects are moved. This only applies to objects with valid UUIDs (IngeTrazo Groups). Loose geometry (`loose-geometry-0000`) cannot be live-transformed because it lacks a local matrix in the IngeTrazo engine.

**Blender → IngeTrazo:**
```json
{
  "protocol": "ingetrazo-blender-sync",
  "message": "transform_update",
  "object_id": "uuid-string",
  "transform": [1.0, 0.0, 0.0, 0.0, ...]
}
```
*Note: `transform` is a 16-element array (column-major QMatrix4x4) containing the new local matrix relative to Blender's origin.*

## Materials
**IngeTrazo → Blender:**
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "material_update",
  "revision": 124,
  "material": {
    "name": "Concrete",
    "color": [0.8, 0.8, 0.8],
    "opacity": 1.0,
    "texture": {
      "path": "/path/to/texture.jpg",
      "sw": 1.0,
      "sh": 1.0
    }
  }
}
```

## Keep-Alive
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "ping"
}
```
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "pong"
}
```

## Error Handling
```json
{
  "protocol": "ingetrazo-blender-sync",
  "version": 1,
  "message": "error",
  "error": "Message parsing failed."
}
```

## Units and Coordinates
- **IngeTrazo coordinates**: Z-up, metric (meters).
- **Blender coordinates**: Z-up, metric (meters).
- The protocol assumes a 1:1 scale transmission. Any conversion should occur on the receiving side (Blender).
