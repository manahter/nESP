"""
    Bu modül, rapor ile alınan çıktıları, blender INFO paneline otomatik ekler. Modal sürekli çalışır. Rapor dosyasında
yeni kayıt bulursa, blender'da bildirim olarak verir.

Usage:
    from rapor import blender_plug

NOTE: No need to do anything else
"""

from bpy.app.handlers import persistent
from bpy.utils import register_class
from bpy.types import Operator
import bpy
import time
import os


class RAPOR_OT_Plug(Operator):
    bl_idname = "rapor.reporter"
    bl_label = "Rapor for Blender Reporter"
    bl_description = "ESP Connect"
    bl_options = {'REGISTER'}

    # report_type: EnumProperty(
    #     name="Type",
    #     items=[
    #         ('INFO', "INFO", ""),
    #         ('WARNING', "WARNING", ""),
    #         ('ERROR', "ERROR", ""),
    #         ('DEBUG', "DEBUG", ""),
    #         ('OPERATOR', "OPERATOR", ""),
    #         ('PROPERTY', "PROPERTY", ""),
    #         ('ERROR_INVALID_INPUT', "ERROR_INVALID_INPUT", ""),
    #         ('ERROR_INVALID_CONTEXT', "ERROR_INVALID_CONTEXT", ""),
    #         ('ERROR_OUT_OF_MEMORY', "ERROR_OUT_OF_MEMORY", "")
    #     ],
    # )
    message_types = {
        "INFO": "INFO",
        "iNFO": "INFO",
        #"iNFO": "DEBUG",
        "WARNING": "WARNING",
        "NOTICE": "OPERATOR",
        "ERROR": "ERROR"
    }

    delay = 1
    _last_time = 0

    filename = os.path.join(os.path.dirname(__file__), "keep")
    file_size = 0
    last_message = ""

    def execute(self, context):
        return self.invoke(context, None)

    def invoke(self, context, event=None):
        context.window_manager.modal_handler_add(self)
        wm = context.window_manager
        self._timer = wm.event_timer_add(self.delay, window=context.window)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        # ########################### STANDARD
        if time.time() - self._last_time < self.delay:
            return {'PASS_THROUGH'}

        self._last_time = time.time()
        # ####################################
        # ####################################

        if os.path.exists(self.filename) and self.file_size != os.stat(self.filename).st_size:

            self.file_size = os.stat(self.filename).st_size

            with open(self.filename) as f:
                lines = f.readlines()

                if not lines:
                    return {'PASS_THROUGH'}

                try:
                    ind = lines.index(self.last_message) + 1
                    messages = lines[ind:]
                except:
                    messages = lines

                if not messages:
                    return {'PASS_THROUGH'}

                for i in messages:
                    prs = i.split("|", 2)
                    if len(prs) < 3:
                        continue

                    report_type = self.message_types.get(prs[1].strip(), "INFO")
                    message = prs[2].strip()
                    self.report({report_type}, message)

                self.last_message = messages[-1]

        return {'PASS_THROUGH'}


@persistent
def load_handler(dummy):
    bpy.ops.rapor.reporter()


register_class(RAPOR_OT_Plug)

bpy.app.handlers.load_post.append(load_handler)
