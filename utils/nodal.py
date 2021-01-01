from bpy.props import BoolProperty
from bpy.types import Operator
import time

running_modals = {}


def register_modal(self):
    # if exists previous modal (self), stop it
    unregister_modal(self)

    # Register to self
    running_modals[self.bl_idname] = self

    # self.report({'INFO'}, "NESP Communication: Started")


def unregister_modal(self):
    # Get previous running modal
    self_prev = running_modals.get(self.bl_idname)

    try:
        # if exists previous modal (self), stop it
        if self_prev:
            self_prev._inloop = False
            running_modals.pop(self.bl_idname)

            # self.report({'INFO'}, "NESP Communication: Stopped (Previous Modal)")
    except:
        running_modals.pop(self.bl_idname)


class Nodal:
    _last_time = 0
    _inloop = True
    delay = .1

    start: BoolProperty(default=True)

    def execute(self, context):
        return self.invoke(context, None)

    def invoke(self, context, event):
        # ########################### STANDARD
        if not self.start:
            unregister_modal(self)
            return {'CANCELLED'}
        register_modal(self)
        context.window_manager.modal_handler_add(self)
        # ####################################
        # ####################################

        abc = self.n_invoke(context, event)
        if abc:
            return abc

        return self.timer_add(context)

    def timer_add(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.delay, window=context.window)
        return {"RUNNING_MODAL"}

    def timer_remove(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        return {'CANCELLED'}

    def modal(self, context, event):
        # ########################### STANDARD
        if not self._inloop:
            if context.area:
                context.area.tag_redraw()
            return self.timer_remove(context)

        if time.time() - self._last_time < self.delay:
            return {'PASS_THROUGH'}

        self._last_time = time.time()
        # ####################################
        # Buradan sonra yapmak istediklerimiz

        result = self.n_modal(context, event)

        # Ekranı yenile
        if context.area:
            context.area.tag_redraw()
        return result

    def n_invoke(self, context, event):
        return None

    def n_modal(self, context, event):
        return {"PASS_THROUGH"}
