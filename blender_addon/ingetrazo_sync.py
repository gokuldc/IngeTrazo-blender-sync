bl_info = {
    "name": "IngeTrazo Sync",
    "description": "Live synchronization with IngeTrazo",
    "author": "IngeTrazo Contributors",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > IngeTrazo",
    "category": "Import-Export",
}

import bpy
import bmesh
import json
import socket
import threading
import queue
import mathutils

_sync_thread = None
_sync_queue = queue.Queue()
_stop_event = threading.Event()
_is_connected = False
_socket = None

def get_or_create_collection(name, parent_col=None):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    if parent_col:
        parent_col.children.link(col)
    else:
        bpy.context.scene.collection.children.link(col)
    return col

def get_object_by_uuid(uid):
    for obj in bpy.data.objects:
        if obj.get("ingetrazo_uuid") == uid:
            return obj
    return None

def update_object_geometry(obj, geom_data):
    import os
    verts = geom_data.get("vertices", [])
    faces = geom_data.get("faces", [])
    materials_data = geom_data.get("materials", [])
    face_materials = geom_data.get("face_materials", [])
    uv_data = geom_data.get("uvs", [])
    
    mesh = obj.data
    mesh.clear_geometry()
    mesh.from_pydata(verts, [], faces)
    
    # Update materials
    mesh.materials.clear()
    for mat_data in materials_data:
        mat_name = mat_data.get("name", "DefaultMaterial")
        if mat_name in bpy.data.materials:
            mat = bpy.data.materials[mat_name]
        else:
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
            
        color = mat_data.get("color")
        opacity = mat_data.get("opacity")
        
        if color:
            r, g, b = color[0], color[1], color[2]
            a = color[3] if len(color) > 3 else 1.0
            
            # Update Viewport Solid Mode color
            mat.diffuse_color = (r, g, b, opacity if opacity is not None else a)
            
            if mat.use_nodes and mat.node_tree:
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    bsdf.inputs['Base Color'].default_value = (r, g, b, a)
                    if opacity is not None and opacity < 1.0:
                        bsdf.inputs['Alpha'].default_value = opacity
                        mat.blend_method = 'BLEND'
                        
        texture_path = mat_data.get("texture_path")
        if texture_path and os.path.exists(texture_path):
            if mat.use_nodes and mat.node_tree:
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    tex_node = mat.node_tree.nodes.get("IngeTrazoTexture")
                    if not tex_node:
                        tex_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                        tex_node.name = "IngeTrazoTexture"
                        mat.node_tree.links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
                    
                    img_name = os.path.basename(texture_path)
                    if img_name in bpy.data.images:
                        img = bpy.data.images[img_name]
                    else:
                        img = bpy.data.images.load(texture_path)
                    tex_node.image = img
                    
        mesh.materials.append(mat)
        
    # Assign face materials safely
    for i, poly in enumerate(mesh.polygons):
        if i < len(face_materials):
            poly.material_index = face_materials[i]
            
    # Apply UVs
    if uv_data and mesh.polygons:
        if not mesh.uv_layers:
            mesh.uv_layers.new(name="UVMap")
        uv_layer = mesh.uv_layers.active
        for i, poly in enumerate(mesh.polygons):
            if i < len(uv_data):
                poly_uvs = uv_data[i]
                for j, loop_idx in enumerate(poly.loop_indices):
                    if j < len(poly_uvs):
                        uv_layer.data[loop_idx].uv = poly_uvs[j]
            
    mesh.update()

def process_message(msg):
    try:
        if msg.get("message") == "object_update":
            obj_data = msg["object"]
            uid = obj_data["id"]
            
            # Organize into Collections based on IFC class
            master_col = get_or_create_collection("IngeTrazo")
            metadata = obj_data.get("metadata", {})
            ifc_data = metadata.get("ifc") or {}
            
            ifc_class = ifc_data.get("class", "Untagged")
            target_col = get_or_create_collection(f"IngeTrazo_{ifc_class}", parent_col=master_col)
            
            obj = get_object_by_uuid(uid)
            
            if not obj:
                mesh = bpy.data.meshes.new(name=obj_data.get("name", "IngeTrazoObj"))
                obj = bpy.data.objects.new(obj_data.get("name", "IngeTrazoObj"), mesh)
                obj["ingetrazo_uuid"] = uid
                obj["ingetrazo_sync"] = True
                target_col.objects.link(obj)
            else:
                # Rename if changed
                obj.name = obj_data.get("name", obj.name)
                obj.data.name = obj.name
                
                # Update collection linking
                for c in obj.users_collection:
                    if c != target_col:
                        c.objects.unlink(obj)
                if target_col.name not in [c.name for c in obj.users_collection]:
                    target_col.objects.link(obj)
                
            # Update metadata Custom Properties
            for k, v in ifc_data.items():
                obj[f"ifc_{k}"] = v
            if "layer" in metadata:
                obj["layer"] = metadata["layer"]
                
            # Update Transform (column-major to row-major)
            t = obj_data.get("transform")
            if t and len(t) == 16:
                mat = mathutils.Matrix((
                    (t[0], t[4], t[8], t[12]),
                    (t[1], t[5], t[9], t[13]),
                    (t[2], t[6], t[10], t[14]),
                    (t[3], t[7], t[11], t[15])
                ))
                obj.matrix_world = mat
                
            # Update Geometry
            geom = obj_data.get("geometry")
            if geom:
                update_object_geometry(obj, geom)

        elif msg.get("message") == "object_delete":
            uid = msg["object"]["id"]
            obj = get_object_by_uuid(uid)
            if obj:
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
                    
        bpy.context.view_layer.update()
    except Exception as e:
        print("[IngeTrazo Sync] Error processing message:", e)

def timer_callback():
    while not _sync_queue.empty():
        try:
            msg = _sync_queue.get_nowait()
            process_message(msg)
        except queue.Empty:
            break
    
    if _is_connected:
        return 0.1
    return None

def sync_worker(host, port):
    global _is_connected, _socket
    
    try:
        _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _socket.connect((host, port))
        
        # Handshake
        handshake = {
            "protocol": "ingetrazo-blender-sync",
            "version": 1,
            "message": "hello",
            "client": "blender-addon"
        }
        _socket.sendall((json.dumps(handshake) + "\n").encode('utf-8'))
        
        _socket.settimeout(0.5)
        buf = b""
        
        while not _stop_event.is_set():
            try:
                chunk = _socket.recv(65536)
                if not chunk:
                    print("[IngeTrazo Sync] Server closed connection (EOF).")
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        msg = json.loads(line)
                        _sync_queue.put(msg)
            except socket.timeout:
                continue
            except OSError:
                break
            except json.JSONDecodeError as e:
                print("[IngeTrazo Sync] JSON Error:", e)
                
    except Exception as e:
        print("[IngeTrazo Sync] Connection Error:", e)
        
    finally:
        if _socket:
            try:
                _socket.close()
            except:
                pass
            _socket = None
        _is_connected = False
        print("[IngeTrazo Sync] Disconnected.")

class INGETRAZO_OT_connect(bpy.types.Operator):
    """Connect to IngeTrazo"""
    bl_idname = "ingetrazo.connect"
    bl_label = "Connect"
    
    def execute(self, context):
        global _sync_thread, _is_connected
        if _is_connected:
            self.report({'INFO'}, "Already connected")
            return {'CANCELLED'}
            
        _stop_event.clear()
        
        host = context.scene.ingetrazo_host
        port = context.scene.ingetrazo_port
        
        _sync_thread = threading.Thread(target=sync_worker, args=(host, port), daemon=True)
        _sync_thread.start()
        _is_connected = True
        
        if not bpy.app.timers.is_registered(timer_callback):
            bpy.app.timers.register(timer_callback)
            
        self.report({'INFO'}, "Connecting to IngeTrazo...")
        return {'FINISHED'}

class INGETRAZO_OT_disconnect(bpy.types.Operator):
    """Disconnect from IngeTrazo"""
    bl_idname = "ingetrazo.disconnect"
    bl_label = "Disconnect"
    
    def execute(self, context):
        global _is_connected, _socket
        if not _is_connected:
            return {'CANCELLED'}
            
        _stop_event.set()
        if _socket:
            try:
                _socket.close()
            except:
                pass
        
        _is_connected = False
        self.report({'INFO'}, "Disconnected from IngeTrazo")
        return {'FINISHED'}

class INGETRAZO_PT_panel(bpy.types.Panel):
    bl_label = "IngeTrazo Sync"
    bl_idname = "INGETRAZO_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'IngeTrazo'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        status = "Connected" if _is_connected else "Disconnected"
        layout.label(text=f"Status: {status}")
        
        layout.prop(scene, "ingetrazo_host", text="Host")
        layout.prop(scene, "ingetrazo_port", text="Port")
        
        row = layout.row()
        if not _is_connected:
            row.operator("ingetrazo.connect")
        else:
            row.operator("ingetrazo.disconnect")

def register():
    bpy.types.Scene.ingetrazo_host = bpy.props.StringProperty(
        name="Host", default="127.0.0.1"
    )
    bpy.types.Scene.ingetrazo_port = bpy.props.IntProperty(
        name="Port", default=47634
    )
    
    bpy.utils.register_class(INGETRAZO_OT_connect)
    bpy.utils.register_class(INGETRAZO_OT_disconnect)
    bpy.utils.register_class(INGETRAZO_PT_panel)

def unregister():
    global _is_connected
    if _is_connected:
        _stop_event.set()
        if _socket:
            try:
                _socket.close()
            except:
                pass
        _is_connected = False

    if bpy.app.timers.is_registered(timer_callback):
        bpy.app.timers.unregister(timer_callback)
        
    bpy.utils.unregister_class(INGETRAZO_OT_connect)
    bpy.utils.unregister_class(INGETRAZO_OT_disconnect)
    bpy.utils.unregister_class(INGETRAZO_PT_panel)
    
    del bpy.types.Scene.ingetrazo_host
    del bpy.types.Scene.ingetrazo_port

if __name__ == "__main__":
    register()
