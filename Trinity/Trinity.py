# --- METADADOS DO ADDON ---
bl_info = {
    "name": "Trinity",
    "author": "MarcosPFA15- git",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > Trinity",
    "description": "Aplica os princípios de animação (Arco, Antecipação, Timing) a Objetos e Pose Bones.",
    "warning": "",
    "doc_url": "",
    "category": "Animation",
}

import bpy
import math
from mathutils import Vector

# --- FUNÇÃO HELPER PARA OBTER INFORMAÇÕES DO ALVO ---
def get_animation_target_info(context, action):
    """
    Verifica o contexto para determinar se o alvo da animação é um Objeto ou um Pose Bone.
    Retorna um dicionário com as f-curves de localização e o alvo para keyframing.
    """
    obj = context.active_object
    target_info = {
        'fcurves': [],
        'target': None,
        'data_path': 'location'
    }

    if not obj or not obj.animation_data or not obj.animation_data.action:
        return None

    if obj.mode == 'POSE' and context.active_pose_bone:
        bone = context.active_pose_bone
        data_path_prefix = f'pose.bones["{bone.name}"].location'
        
        fcurves_found = [action.fcurves.find(data_path_prefix, index=i) for i in range(3)]
        if all(fcurves_found):
            target_info['fcurves'] = fcurves_found
            target_info['target'] = bone
            return target_info
            
    else:
        fcurves_found = [action.fcurves.find('location', index=i) for i in range(3)]
        if all(fcurves_found):
            target_info['fcurves'] = fcurves_found
            target_info['target'] = obj
            return target_info
            
    return None

# --- OPERADOR PRINCIPAL ---
class OBJECT_OT_apply_animation_principles(bpy.types.Operator):
    """Aplica os princípios de animação selecionados ao alvo ativo dentro do intervalo de frames"""
    bl_label = "Apply Animation Principles"
    bl_idname = "object.apply_animation_principles"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.animation_principles_props
        obj = context.active_object

        if not obj:
            self.report({'WARNING'}, "Nenhum objeto selecionado.")
            return {'CANCELLED'}

        if not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "O objeto não possui dados de animação (keyframes).")
            return {'CANCELLED'}

        action = obj.animation_data.action
        start_frame = props.start_frame
        end_frame = props.end_frame

        if start_frame >= end_frame and (props.apply_global_timing or props.apply_arc):
             self.report({'WARNING'}, "O 'Start Frame' deve ser menor que o 'End Frame' para Arco ou Global Timing.")
             return {'CANCELLED'}

        # --- ORDEM DE APLICAÇÃO ---
        if props.apply_shift_time:
            self.apply_shift_time(action, props.start_frame, props.shift_frames)
            start_frame += props.shift_frames
            end_frame += props.shift_frames
        if props.apply_global_timing:
            original_duration = end_frame - start_frame
            new_duration = math.floor(original_duration * props.global_timing_scale)
            duration_delta = new_duration - original_duration
            
            self.apply_global_timing(context, action, start_frame, end_frame, props.global_timing_scale, duration_delta)
            
            end_frame = start_frame + new_duration
        if props.apply_arc:
            self.apply_arc(context, action, props.arc_height, props.arc_angle, start_frame, end_frame)
        if props.apply_anticipation:
            self.apply_anticipation(context, action, props.anticipation_frames, props.anticipation_amount, start_frame)
        if props.apply_localized_timing:
            self.apply_localized_timing(context, action, props.timing_zone_start, props.timing_zone_end, props.timing_zone_scale)

        self.report({'INFO'}, "Princípios de animação aplicados!")
        return {'FINISHED'}
    
    def apply_shift_time(self, action, start_frame, frames_to_shift):
        """Desloca todos os keyframes da animação a partir de um ponto."""
        if frames_to_shift == 0:
            return
            
        for fcurve in action.fcurves:
            for kf in reversed(fcurve.keyframe_points):
                if kf.co.x > start_frame:
                    kf.co.x += frames_to_shift
                    kf.handle_left.x += frames_to_shift
                    kf.handle_right.x += frames_to_shift
            fcurve.update()

    def apply_arc(self, context, action, arc_height, arc_angle, start_frame, end_frame):
        """Aplica um arco aditivo, afetando apenas o alvo selecionado."""
        props = context.scene.animation_principles_props
        target_info = get_animation_target_info(context, action)
        if not target_info:
            self.report({'WARNING'}, "Alvo válido não encontrado para o Arco.")
            return

        fcurves = target_info['fcurves']
        target = target_info['target']
        mid_frame = (start_frame + end_frame) / 2.0
        
        start_pos = Vector((fcurves[0].evaluate(start_frame), fcurves[1].evaluate(start_frame), fcurves[2].evaluate(start_frame)))
        end_pos = Vector((fcurves[0].evaluate(end_frame), fcurves[1].evaluate(end_frame), fcurves[2].evaluate(end_frame)))
        
        base_pos = start_pos.lerp(end_pos, 0.5)
        direction_vec = end_pos - start_pos
        
        if direction_vec.length < 0.0001: direction_vec = Vector((0, 1, 0))
        direction_vec.normalize()
        
        if abs(direction_vec.dot(Vector((0.0, 0.0, 1.0)))) > 0.999:
            perp_vec_up, perp_vec_right = Vector((1.0, 0.0, 0.0)), direction_vec.cross(Vector((1.0, 0.0, 0.0)))
        else:
            world_up = Vector((0.0, 0.0, 1.0))
            perp_vec_right = direction_vec.cross(world_up)
            perp_vec_up = perp_vec_right.cross(direction_vec)

        perp_vec_up.normalize(); perp_vec_right.normalize()
        angle_rad = arc_angle 
        arc_offset = (perp_vec_up * math.cos(angle_rad)) + (perp_vec_right * math.sin(angle_rad))
        arc_peak_pos = base_pos + arc_offset * arc_height
        target.location = arc_peak_pos
        target.keyframe_insert(data_path="location", frame=math.floor(mid_frame))
        
        for fc in fcurves:
            fc.update()
            kf_start, kf_mid, kf_end = None, None, None
            for kf in fc.keyframe_points:
                if abs(kf.co.x - start_frame) < 0.001: kf_start = kf
                elif abs(kf.co.x - mid_frame) < 0.001: kf_mid = kf
                elif abs(kf.co.x - end_frame) < 0.001: kf_end = kf

            if kf_start: kf_start.interpolation = 'BEZIER'
            if kf_mid: kf_mid.interpolation = 'BEZIER'
            if kf_end: kf_end.interpolation = 'BEZIER'

            if kf_start: kf_start.handle_right_type = 'AUTO'
            if kf_mid: kf_mid.handle_left_type = 'AUTO'; kf_mid.handle_right_type = 'AUTO'
            if kf_end: kf_end.handle_left_type = 'AUTO'
            fc.update()

    def apply_anticipation(self, context, action, frames, amount, start_frame):
        props = context.scene.animation_principles_props
        target_info = get_animation_target_info(context, action)
        if not target_info:
            self.report({'WARNING'}, "Alvo válido não encontrado para a Antecipação.")
            return
            
        fcurves, target = target_info['fcurves'], target_info['target']
        pos_start = Vector((fcurves[0].evaluate(start_frame), fcurves[1].evaluate(start_frame), fcurves[2].evaluate(start_frame)))
        
        next_kf_frame = float('inf')
        for kf in fcurves[0].keyframe_points:
            if kf.co.x > start_frame and kf.co.x < next_kf_frame: next_kf_frame = kf.co.x
        if next_kf_frame == float('inf'): next_kf_frame = start_frame + 1

        pos_next = Vector((fcurves[0].evaluate(next_kf_frame), fcurves[1].evaluate(next_kf_frame), fcurves[2].evaluate(next_kf_frame)))
        direction = (pos_next - pos_start).normalized()
        if direction.length < 0.001: return
        anticipation_pos = pos_start - direction * amount

        curves_to_shift = action.fcurves if props.anticipation_sync else fcurves
        for fcurve in curves_to_shift:
            for kf in fcurve.keyframe_points:
                if kf.co.x >= start_frame:
                    kf.co.x += frames; kf.handle_left.x += frames; kf.handle_right.x += frames

        target.location = pos_start
        target.keyframe_insert(data_path="location", frame=start_frame)
        target.location = anticipation_pos
        target.keyframe_insert(data_path="location", frame=start_frame + (frames // 2))

    def apply_localized_timing(self, context, action, zone_start, zone_end, scale_factor):
        """(CORRIGIDO) Arredonda os valores das alças para evitar frames 'quebrados'."""
        if zone_start >= zone_end:
            self.report({'WARNING'}, "O 'Zone Start' deve ser menor que o 'Zone End'.")
            return
        
        target_info = get_animation_target_info(context, action)
        if not target_info:
            self.report({'WARNING'}, "Alvo válido não encontrado para o Timing Localizado.")
            return

        for fcurve in target_info['fcurves']:
            for kf in fcurve.keyframe_points:
                if kf.co.x >= zone_start and kf.co.x <= zone_end:
                    kf.handle_left_type = 'ALIGNED'; kf.handle_right_type = 'ALIGNED'
            fcurve.update()
            for kf in fcurve.keyframe_points:
                if kf.co.x >= zone_start and kf.co.x <= zone_end:
                    handle_vec_left_x = kf.handle_left.x - kf.co.x
                    kf.handle_left.x = kf.co.x + math.floor(handle_vec_left_x * scale_factor)
                    handle_vec_right_x = kf.handle_right.x - kf.co.x
                    kf.handle_right.x = kf.co.x + math.floor(handle_vec_right_x * scale_factor)
            fcurve.update()
            
    def apply_global_timing(self, context, action, start_frame, end_frame, scale_factor, duration_delta):
        """(CORRIGIDO) Escala a duração usando valores inteiros (arredondados)."""
        target_info = get_animation_target_info(context, action)
        if not target_info:
            self.report({'WARNING'}, "Alvo válido não encontrado para o Global Timing.")
            return
        original_duration = end_frame - start_frame
        if original_duration <= 0: return
        for fcurve in action.fcurves:
            for kf in reversed(fcurve.keyframe_points):
                if kf.co.x > end_frame:
                    kf.co.x += duration_delta
                    kf.handle_left.x += duration_delta
                    kf.handle_right.x += duration_delta
        for fcurve in target_info['fcurves']:
            for kf in reversed(fcurve.keyframe_points):
                if kf.co.x > start_frame and kf.co.x <= end_frame:
                    original_pos_in_range = kf.co.x - start_frame
                    new_kf_x = start_frame + math.floor(original_pos_in_range * scale_factor)
                    
                    original_handle_L_offset = kf.handle_left.x - kf.co.x
                    original_handle_R_offset = kf.handle_right.x - kf.co.x
                    new_handle_L_x = new_kf_x + math.floor(original_handle_L_offset * scale_factor)
                    new_handle_R_x = new_kf_x + math.floor(original_handle_R_offset * scale_factor)
                    
                    kf.co.x = new_kf_x
                    kf.handle_left.x = new_handle_L_x
                    kf.handle_right.x = new_handle_R_x
            fcurve.update()

# --- PROPRIEDADES (CONFIGURAÇÕES) ---
class AnimationPrinciplesProperties(bpy.types.PropertyGroup):
    start_frame: bpy.props.IntProperty(name="Start", default=1, min=1)
    end_frame: bpy.props.IntProperty(name="End", default=100, min=1)

    apply_arc: bpy.props.BoolProperty(name="Apply Arc", default=False)
    arc_height: bpy.props.FloatProperty(name="Arc Height", default=1.0)
    arc_angle: bpy.props.FloatProperty(name="Arc Angle", default=0.0, subtype='ANGLE')
    
    apply_anticipation: bpy.props.BoolProperty(name="Apply Anticipation", default=False)
    anticipation_frames: bpy.props.IntProperty(name="Frames", default=5, min=1)
    anticipation_amount: bpy.props.FloatProperty(name="Amount", default=0.5)
    anticipation_sync: bpy.props.BoolProperty(name="Sync Whole Animation", default=True, description="Desloca todos os keyframes da animação para manter a sincronia")
    apply_shift_time: bpy.props.BoolProperty(
        name="Shift Global Time", 
        default=False, 
        description="Desloca todos os keyframes. >0 adiciona tempo (move para a direita), <0 remove tempo (move para a esquerda)"
    )
    shift_frames: bpy.props.IntProperty(
        name="Frames to Shift", 
        default=10,
        description="Número de frames para deslocar (pode ser negativo)"
    )
    
    apply_global_timing: bpy.props.BoolProperty(name="Apply Time Scale (Range)", default=False)
    global_timing_scale: bpy.props.FloatProperty(name="Time Scale", default=1.25, min=0.01, description="Escala a duração do intervalo. <1.0 = mais rápido, >1.0 = mais lento")

    apply_localized_timing: bpy.props.BoolProperty(name="Apply Localized Timing", default=False)
    timing_zone_start: bpy.props.IntProperty(name="Zone Start", default=40, min=1)
    timing_zone_end: bpy.props.IntProperty(name="Zone End", default=60, min=1)
    timing_zone_scale: bpy.props.FloatProperty(name="Velocity Scale", default=0.5, min=0.01, description="Muda a velocidade na zona. <1.0 = mais rápido, >1.0 = mais lento")

# --- PAINEL DA UI ---
class ANIM_PT_principles_panel(bpy.types.Panel):
    bl_label = "Trinity Animation"
    bl_idname = "ANIM_PT_trinity_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Trinity'
    def draw(self, context):
        layout = self.layout
        props = context.scene.animation_principles_props

        box = layout.box()
        box.label(text="Global Frame Range:")
        row = box.row()
        row.prop(props, "start_frame")
        row.prop(props, "end_frame")
        layout.separator()
        box_arc = layout.box()
        box_arc.prop(props, "apply_arc")
        if props.apply_arc:
            row = box_arc.row(align=True)
            row.prop(props, "arc_angle"); row.prop(props, "arc_height")
        box_ant = layout.box()
        box_ant.prop(props, "apply_anticipation")
        if props.apply_anticipation:
            row = box_ant.row()
            row.prop(props, "anticipation_frames"); row.prop(props, "anticipation_amount")
            box_ant.prop(props, "anticipation_sync")
        box_shift_time = layout.box()
        box_shift_time.prop(props, "apply_shift_time")
        if props.apply_shift_time:
            box_shift_time.prop(props, "shift_frames")
        box_global_time = layout.box()
        box_global_time.prop(props, "apply_global_timing", text="Apply Time Scale (Range)")
        if props.apply_global_timing:
            box_global_time.prop(props, "global_timing_scale")
            
        box_local_time = layout.box()
        box_local_time.prop(props, "apply_localized_timing")
        if props.apply_localized_timing:
            box_local_time.prop(props, "timing_zone_scale")
            row = box_local_time.row()
            row.prop(props, "timing_zone_start"); row.prop(props, "timing_zone_end")
        
        layout.separator()
        layout.operator("object.apply_animation_principles", text="Apply to Selected")

# --- REGISTRO DO ADDON ---
classes = (
    OBJECT_OT_apply_animation_principles,
    AnimationPrinciplesProperties,
    ANIM_PT_principles_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.animation_principles_props = bpy.props.PointerProperty(type=AnimationPrinciplesProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.animation_principles_props

if __name__ == "__main__":
    register()

