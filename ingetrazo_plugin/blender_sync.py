# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo to Blender Live Sync Plugin."""
from __future__ import annotations

import json
import socket
import threading
import queue
import traceback
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal

from tools.base import Tool
from core.i18n import tr

DEFAULT_PORT = 47634

class _BlenderSyncServer(QObject):
    """Network server and scene observer."""

    # Signal to queue updates to the network thread
    _send_signal = Signal(object)

    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.server = None
        self.thread = None
        self._stop = threading.Event()
        self.clients = []
        self._last_version = -1
        self._known_uids = set()

        self.viewport.sceneVersionChanged.connect(self._on_scene_changed, Qt.QueuedConnection)
        self._send_signal.connect(self._handle_signal, Qt.QueuedConnection)

    def _handle_signal(self, payload):
        if payload == "force_full":
            self._on_scene_changed(self.viewport.scene.version, force_full=True)

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", DEFAULT_PORT))
        self.server.listen(5)
        self.server.settimeout(0.5)

        self._stop.clear()
        self.thread = threading.Thread(target=self._serve, name="blender-sync", daemon=True)
        self.thread.start()

        # Send initial snapshot if scene is not empty
        self._on_scene_changed(self.viewport.scene.version)
        return DEFAULT_PORT

    def stop(self):
        self._stop.set()
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
            self.server = None
        for conn in self.clients:
            try:
                conn.close()
            except OSError:
                pass
        self.clients.clear()

    @property
    def running(self):
        return self.server is not None

    def _serve(self):
        while not self._stop.is_set() and self.server is not None:
            try:
                conn, addr = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                return

            print(f"[SYNC] Blender connected from {addr}")
            self.clients.append(conn)
            
            # Start a receiver thread for this client (for handshake/ping)
            t = threading.Thread(target=self._client_read, args=(conn,), daemon=True)
            t.start()

            # Schedule a full snapshot for this new client on the main thread safely.
            self._send_signal.emit("force_full")

    def _client_read(self, conn):
        buf = b""
        with conn:
            conn.settimeout(0.5)
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        req = json.loads(line)
                        if req.get("message") == "hello":
                            self._send_raw(conn, {
                                "protocol": "ingetrazo-blender-sync",
                                "version": 1,
                                "message": "hello_ack",
                                "revision": self.viewport.scene.version
                            })
                    except Exception as e:
                        print("[SYNC] Invalid message from client:", e)
            if conn in self.clients:
                self.clients.remove(conn)

    def _send_raw(self, conn, msg_dict):
        try:
            data = (json.dumps(msg_dict) + "\n").encode("utf-8")
            conn.sendall(data)
        except OSError:
            if conn in self.clients:
                self.clients.remove(conn)

    def _broadcast(self, msg_dict):
        if not self.clients:
            return
        data = (json.dumps(msg_dict) + "\n").encode("utf-8")
        dead = []
        for conn in self.clients:
            try:
                conn.sendall(data)
            except OSError:
                dead.append(conn)
        for conn in dead:
            if conn in self.clients:
                self.clients.remove(conn)

    def _serialize_mesh(self, mesh, group_mat=None):
        try:
            from core.materials import effective_attrs
            from core.texture import face_uv_axes
        except ImportError:
            effective_attrs = lambda attrs, mat: attrs or {}
            face_uv_axes = None
            
        verts = []
        vid_to_idx = {}
        for i, v in enumerate(mesh.vertices):
            verts.append([v.position.x(), v.position.y(), v.position.z()])
            vid_to_idx[id(v)] = i

        faces = []
        uvs = []
        materials = []
        mat_to_idx = {}
        face_materials = []

        for f in mesh.faces:
            face_indices = []
            face_uvs = []
            
            # Extract material for this face
            attrs = effective_attrs(f.attrs, group_mat) if group_mat else f.attrs
            tex = attrs.get("texture") if attrs else None
            
            has_uv = False
            if tex:
                if face_uv_axes is not None:
                    gu, cu, gv, cv = face_uv_axes(tex, f.normal())
                    ux, uy, uz, uc = gu.x(), gu.y(), gu.z(), cu
                    vx, vy, vz, vc = gv.x(), gv.y(), gv.z(), cv
                    has_uv = True
                else:
                    uvw = tex.get("uvw")
                    if uvw and len(uvw) == 8:
                        ux, uy, uz, uc = uvw[0:4]
                        vx, vy, vz, vc = uvw[4:8]
                        has_uv = True

            for v in f.loop:
                idx = vid_to_idx.get(id(v))
                if idx is not None:
                    face_indices.append(idx)
                    if has_uv:
                        x, y, z = v.position.x(), v.position.y(), v.position.z()
                        face_uvs.append([ux*x + uy*y + uz*z + uc, vx*x + vy*y + vz*z + vc])
                    else:
                        face_uvs.append([0.0, 0.0])
                    
            if len(face_indices) < 3:
                continue
                
            faces.append(face_indices)
            uvs.append(face_uvs)
            
            # Extract material for this face
            attrs = effective_attrs(f.attrs, group_mat) if group_mat else f.attrs
            mat_name = attrs.get("mat") if attrs else None
            color = attrs.get("color") if attrs else None
            opacity = attrs.get("opacity") if attrs else None
            texture_path = tex.get("path") if tex else None
            
            if not mat_name:
                if texture_path:
                    import os
                    mat_name = f"__tex_{os.path.basename(texture_path)}"
                elif color:
                    mat_name = f"__color_{color[0]:.2f}_{color[1]:.2f}_{color[2]:.2f}"
                else:
                    mat_name = "DefaultMaterial"

            if mat_name not in mat_to_idx:
                mat_to_idx[mat_name] = len(materials)
                materials.append({
                    "name": mat_name,
                    "color": color,
                    "opacity": opacity,
                    "texture_path": texture_path
                })
            
            face_materials.append(mat_to_idx[mat_name])

        return {"vertices": verts, "faces": faces, "uvs": uvs, "materials": materials, "face_materials": face_materials}

    def _extract_group_data(self, group):
        # We need to send the mesh in local coordinates if it's an instance, or world if not.
        # But wait, Blender wants local coordinates and a world transform.
        # `group.mesh` is local if `group.xform` is set.
        
        # Serialize mesh
        geom = self._serialize_mesh(group.mesh, getattr(group, "material", None))

        # Transform (column-major)
        transform = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
        if group.xform is not None:
            # PySide6 QMatrix4x4 data() is column-major flat list/tuple
            transform = list(group.xform.data())
        elif group.axes is not None:
            transform = list(group.axes.data())

        metadata = {}
        if group.ifc:
            metadata = dict(group.ifc)

        return {
            "id": group.uid,
            "name": group.name,
            "type": "group",
            "transform": transform,
            "geometry": geom,
            "metadata": metadata
        }

    def _on_scene_changed(self, version, force_full=False):
        if not self.running or not self.clients:
            return
        
        if version == self._last_version and not force_full:
            return
            
        try:
            scene = self.viewport.scene
            current_uids = set()
            
            updates = []
            deletes = []

            if force_full:
                self._broadcast({
                    "protocol": "ingetrazo-blender-sync",
                    "version": 1,
                    "message": "sync_begin",
                    "revision": version
                })

            for group in scene.groups:
                current_uids.add(group.uid)
                try:
                    gdata = self._extract_group_data(group)
                    msg = {
                        "protocol": "ingetrazo-blender-sync",
                        "version": 1,
                        "message": "object_update",
                        "revision": version,
                        "object": gdata
                    }
                    updates.append(msg)
                except Exception as e:
                    print(f"[SYNC] Error extracting group {group.name}: {e}")
                    traceback.print_exc()

            # Handle loose geometry as a special group
            loose_uid = "loose-geometry-0000"
            current_uids.add(loose_uid)
            loose_geom = self._serialize_mesh(scene.mesh, None)
            updates.append({
                "protocol": "ingetrazo-blender-sync",
                "version": 1,
                "message": "object_update",
                "revision": version,
                "object": {
                    "id": loose_uid,
                    "name": "Loose Geometry",
                    "type": "loose",
                    "transform": [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0],
                    "geometry": loose_geom,
                    "metadata": {}
                }
            })

            if not force_full:
                # Find deleted
                for uid in self._known_uids:
                    if uid not in current_uids:
                        deletes.append({
                            "protocol": "ingetrazo-blender-sync",
                            "version": 1,
                            "message": "object_delete",
                            "revision": version,
                            "object": {"id": uid}
                        })

            self._known_uids = current_uids
            self._last_version = version

            # Transmit
            for msg in deletes:
                self._broadcast(msg)
            for msg in updates:
                self._broadcast(msg)
                
            if force_full:
                self._broadcast({
                    "protocol": "ingetrazo-blender-sync",
                    "version": 1,
                    "message": "sync_end",
                    "revision": version
                })
        except Exception as e:
            print("[SYNC] FATAL ERROR in _on_scene_changed:", e)
            traceback.print_exc()

class BlenderSyncTool(Tool):
    """Extensions menu entry to toggle the Blender Live Sync bridge."""
    name = "Blender Live Sync"
    uses_snap = False

    def on_activate(self, viewport):
        window = viewport.window()
        bridge = getattr(window, "_blender_sync", None)
        if bridge is None:
            bridge = _BlenderSyncServer(viewport)
            window._blender_sync = bridge
        
        if bridge.running:
            bridge.stop()
            viewport.flash_status(tr("Blender Sync stopped"))
        else:
            try:
                port = bridge.start()
                viewport.flash_status(tr("Blender Sync listening on 127.0.0.1:{port}", port=port), 8000)
            except OSError as exc:
                viewport.flash_status(tr("Blender Sync failed to start: {err}", err=str(exc)))

    def on_deactivate(self, viewport):
        pass

def setup(app):
    """Extension initialization."""
    pass
