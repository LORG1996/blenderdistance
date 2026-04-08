bl_info = {
    "name": "Blender Distance",
    "author": "Bobak Studio",
    "version": (1, 7),
    "blender": (3, 0, 0),
    "location": "View3D > UI > BlenderDist",
    "description": "Автоматизація створення карт дистанції",
    "category": "Object",
}

import bpy
import os

# --- ІНТЕРФЕЙС ---
class VIEW3D_PT_BlenderDistancePro(bpy.types.Panel):
    bl_label = "Blender Distance Manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BlenderDist'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="Targets:", icon='EYEDROPPER')
        box.prop(scene, "blender_canvas", text="Canvas")
        
        row = box.row(align=True)
        row.prop(scene, "blender_brush", text="Brush")
        row.prop(scene, "blender_brush_coll", text="Coll")

        layout.operator("object.setup_blender_image_dist", text="Initialize / Reset System", icon='FILE_REFRESH')

        canvas_obj = scene.blender_canvas
        if canvas_obj and "Dynamic Paint" in canvas_obj.modifiers:
            mod = canvas_obj.modifiers["Dynamic Paint"]
            if mod.ui_type == 'CANVAS' and getattr(mod, "canvas_settings", None):
                if len(mod.canvas_settings.canvas_surfaces) > 0:
                    surf = mod.canvas_settings.canvas_surfaces[0]
                    
                    c_box = layout.box()
                    c_box.label(text="Canvas Settings:", icon='SETTINGS')
                    c_box.prop(surf, "image_resolution", text="Resolution")
                    if canvas_obj.type == 'MESH':
                        c_box.prop_search(surf, "uv_layer", canvas_obj.data, "uv_layers", text="UV Map")
                    c_box.prop(surf, "image_output_path", text="Folder Path")

        if scene.blender_brush or scene.blender_brush_coll:
            dist_box = layout.box()
            dist_box.label(text="Proximity Radius:", icon='BRUSH_DATA')
            
            # Якщо вибрано об'єкт
            if scene.blender_brush:
                b_obj = scene.blender_brush
                mod_b = b_obj.modifiers.get("Dynamic Paint")
                if mod_b and mod_b.ui_type == 'BRUSH' and mod_b.brush_settings:
                    dist_box.prop(mod_b.brush_settings, "paint_distance", text="Distance")
                else:
                    dist_box.label(text="Потрібна ініціалізація", icon='ERROR')
            
            # Якщо вибрано колекцію
            if scene.blender_brush_coll:
                row = dist_box.row(align=True)
                row.prop(scene, "blender_global_dist", text="Global")
                row.operator("object.apply_global_dist", text="Apply All")

        if canvas_obj:
            layout.separator()
            col = layout.column(align=True)
            col.scale_y = 1.5
            col.operator("object.bake_only_blender", text="1. BAKE (Current Frame)", icon='RENDER_STILL')
            col.operator("object.refresh_blender_node", text="2. RECONNECT & REFRESH", icon='FILE_REFRESH')

# --- ЛОГІКА ---

def get_canvas_surface(obj):
    if not obj or "Dynamic Paint" not in obj.modifiers: return None
    mod = obj.modifiers["Dynamic Paint"]
    if mod.ui_type == 'CANVAS' and getattr(mod, "canvas_settings", None):
        if len(mod.canvas_settings.canvas_surfaces) > 0: return mod.canvas_settings.canvas_surfaces[0]
    return None

def force_brush_settings(obj, distance=None):
    if not obj or obj.type != 'MESH': return
    mod = obj.modifiers.get("Dynamic Paint") or obj.modifiers.new(name="Dynamic Paint", type='DYNAMIC_PAINT')
    mod.ui_type = 'BRUSH'
    
    if not mod.brush_settings:
        active_orig = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = obj
        bpy.ops.dpaint.type_toggle(type='BRUSH')
        bpy.context.view_layer.objects.active = active_orig
        
    if mod.brush_settings:
        mod.brush_settings.paint_source = 'VOLUME_DISTANCE'
        mod.brush_settings.paint_color = (0, 0, 0)
        if distance is not None:
            mod.brush_settings.paint_distance = distance

# --- ОПЕРАТОРИ ---

class OBJECT_OT_ApplyGlobalDist(bpy.types.Operator):
    bl_idname = "object.apply_global_dist"
    bl_label = "Apply Global Distance"
    def execute(self, context):
        scene = context.scene
        if not scene.blender_brush_coll: return {'CANCELLED'}
        for obj in scene.blender_brush_coll.all_objects:
            force_brush_settings(obj, scene.blender_global_dist)
        return {'FINISHED'}

class OBJECT_OT_BakeOnlyBlender(bpy.types.Operator):
    bl_idname = "object.bake_only_blender"
    bl_label = "Bake"
    def execute(self, context):
        surf = get_canvas_surface(context.scene.blender_canvas)
        if not surf: return {'CANCELLED'}
        current_f = context.scene.frame_current
        surf.frame_start = surf.frame_end = current_f
        full_path = bpy.path.abspath(surf.image_output_path)
        if not os.path.exists(full_path): os.makedirs(full_path)
        bpy.context.view_layer.objects.active = context.scene.blender_canvas
        bpy.ops.dpaint.bake()
        return {'FINISHED'}

class OBJECT_OT_RefreshBlenderNode(bpy.types.Operator):
    bl_idname = "object.refresh_blender_node"
    bl_label = "Refresh"
    def execute(self, context):
        canvas_obj = context.scene.blender_canvas
        surf = get_canvas_surface(canvas_obj)
        if not surf: return {'CANCELLED'}
        output_dir = bpy.path.abspath(surf.image_output_path)
        frame_suffix = f"{context.scene.frame_current:04d}.png"
        filepath = ""
        if os.path.exists(output_dir):
            files = [f for f in os.listdir(output_dir) if f.endswith(frame_suffix)]
            if files: filepath = os.path.join(output_dir, files[0])
        if not filepath: return {'CANCELLED'}
        img_name = os.path.basename(filepath)
        img = bpy.data.images.get(img_name) or bpy.data.images.load(filepath)
        img.reload()
        img.colorspace_settings.name = 'Non-Color'
        mat = canvas_obj.active_material or bpy.data.materials.new(name="Blender_Distance_Bake")
        if not canvas_obj.active_material: canvas_obj.data.materials.append(mat)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        tex_node = nodes.get("Blender_Dist_Node") or nodes.new('ShaderNodeTexImage')
        tex_node.name = "Blender_Dist_Node"
        tex_node.image = img
        if bsdf: mat.node_tree.links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])
        return {'FINISHED'}

class OBJECT_OT_SetupBlenderImageDist(bpy.types.Operator):
    bl_idname = "object.setup_blender_image_dist"
    bl_label = "Initialize"
    def execute(self, context):
        scene = context.scene
        
        # 1. Canvas
        canvas_obj = scene.blender_canvas
        if canvas_obj:
            mod = canvas_obj.modifiers.get("Dynamic Paint") or canvas_obj.modifiers.new(name="Dynamic Paint", type='DYNAMIC_PAINT')
            mod.ui_type = 'CANVAS'
            if not getattr(mod, "canvas_settings", None) or len(mod.canvas_settings.canvas_surfaces) == 0:
                 active_orig = context.view_layer.objects.active
                 context.view_layer.objects.active = canvas_obj
                 bpy.ops.dpaint.type_toggle(type='CANVAS')
                 context.view_layer.objects.active = active_orig
            surf = get_canvas_surface(canvas_obj)
            if surf:
                surf.surface_format = 'IMAGE'
                surf.surface_type = 'PAINT'
                surf.init_color_type = 'COLOR'
                surf.init_color = (1.0, 1.0, 1.0, 1.0)
                surf.use_output_a = True
                if bpy.data.is_saved:
                    surf.image_output_path = os.path.join(os.path.dirname(bpy.data.filepath), "Blender_Bake_Cache")

        # 2. Поодинокий Brush
        if scene.blender_brush:
            force_brush_settings(scene.blender_brush, scene.blender_global_dist)

        # 3. ВСЯ КОЛЕКЦІЯ (Додано/Виправлено)
        if scene.blender_brush_coll:
            for obj in scene.blender_brush_coll.all_objects:
                force_brush_settings(obj, scene.blender_global_dist)
            
        return {'FINISHED'}

classes = (VIEW3D_PT_BlenderDistancePro, OBJECT_OT_ApplyGlobalDist, OBJECT_OT_BakeOnlyBlender, OBJECT_OT_RefreshBlenderNode, OBJECT_OT_SetupBlenderImageDist)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.blender_canvas = bpy.props.PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.blender_brush = bpy.props.PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.blender_brush_coll = bpy.props.PointerProperty(type=bpy.types.Collection)
    bpy.types.Scene.blender_global_dist = bpy.props.FloatProperty(name="Distance", default=1.0)

def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.blender_canvas
    del bpy.types.Scene.blender_brush
    del bpy.types.Scene.blender_brush_coll
    del bpy.types.Scene.blender_global_dist

if __name__ == "__main__":
    register()