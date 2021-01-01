# -*- coding:utf-8 -*-
import os
import re
import time
from datetime import timedelta
from mathutils import Vector, Matrix
from mathutils.geometry import intersect_sphere_sphere_2d, intersect_point_line, intersect_line_line_2d
import math

import blf
import bgl
import bpy
import gpu
import bmesh
from gpu_extras.batch import batch_for_shader
import sys

from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import (
    Text,
    Scene,
    Panel,
    Object,
    Operator,
    PropertyGroup,
    AddonPreferences,
    UIList,
)
from bpy.props import (
    IntProperty,
    BoolProperty,
    EnumProperty,
    FloatProperty,
    StringProperty,
    PointerProperty,
    BoolVectorProperty,
    CollectionProperty,
    FloatVectorProperty
)
from bpy_extras.view3d_utils import (
    region_2d_to_vector_3d,
    region_2d_to_origin_3d
)

bl_info = {
    "name": "nESP",
    "description": "Control ESP Board via Micropython",
    "author": "Manahter",
    "version": (0, 1, 0),
    "blender": (2, 91, 0),
    "location": "View3D",
    "category": "Generic",
    "warning": "Under development. Nothing is guaranteed",
    "doc_url": "",
    "tracker_url": ""
}
from .utils.nodal import Nodal, register_modal, unregister_modal
from .modules.dirio import Dirio
from .modules.scanag import scanag
from .modules.webrepl import Webrepl, WR_CMD, WR_KEY
from .modules.rapor import blender_plug

dev = None


class NESP_PR_Connection(PropertyGroup):

    def get_isscanning(self):
        return scanag.inprocess

    def set_isscanning(self, value):
        if value:
            scanag.scan()

    isscanning: BoolProperty(
        name="Is Scanning?",
        get=get_isscanning,
        set=set_isscanning
    )

    scantype: EnumProperty(
        name="Scan Type",
        items=[
            ("all", "All devices", ""),
            ("esp", "Only ESP", ""),
        ]
    )

    def get_isconnecting(self):
        return (dev.isconnect == 0) if dev and dev.dr_isactive() else False

    isconnecting: BoolProperty(
        name="Is connecting",
        default=False,
        get=get_isconnecting
    )

    def set_isconnected(self, value):
        bpy.ops.nesp.communication(action=("connect" if value else "disconnect"))

    def get_isconnected(self):
        return (dev.isconnect > 0) if dev and dev.dr_isactive() else False

    isconnected: BoolProperty(
        name="Is connected",
        description="Is Connected ?",
        default=False,
        get=get_isconnected,
        set=set_isconnected
    )

    def get_inwork(self):
        return self.isconnected and (dev.dr_bind_count() > 0)

    inwork: BoolProperty(
        name="Is in work?",
        get=get_inwork
    )

    def get_devices(self, context):
        return [(i[0], i[0] + " {:1.13}".format(i[2]), i[1]) for i in scanag.devices(only_esp=self.scantype == "esp")]

    device: EnumProperty(
        name="Select Device",
        description="Select the device you want to connect",
        items=get_devices
    )
    port: StringProperty(
        name="Port",
        description="xxx.xxx.x.xx:8266",
        default="8266",
        # min=0
    )
    password: StringProperty(
        name="Password",
        description="Webrepl Password",
        # subtype="PASSWORD"
    )
    controller: EnumProperty(
        items=[("UPY", "MicroPython", "")],
        name="Controller",
        description="Under development...",
        default="UPY"
    )

    @classmethod
    def register(cls):
        Scene.nesp_pr_connection = PointerProperty(
            name="NESP_PR_Connection Name",
            description="NESP_PR_Connection Description",
            type=cls
        )

    @classmethod
    def unregister(cls):
        global dev
        if dev:
            dev.disconnect()
            dev.dr_terminate()
        scanag.inprocess = False
        del Scene.nesp_pr_connection


class NESP_OT_Connection(Operator, Nodal):
    bl_idname = "nesp.connection"
    bl_label = "ESP Connection"
    bl_description = "ESP Connect"
    bl_options = {'REGISTER'}

    action: EnumProperty(
        items=[
            ("void", "Do nothing", ""),
            ("scan", "Scan Network for Devices", ""),
            ("connect", "Connect/Disconnect", ""),
            ("disconnect", "Disconnect", "")
        ]
    )

    dr = None
    delay = 1

    def invoke(self, context, event=None):
        pr_con = context.scene.nesp_pr_connection
        pr_dev = context.scene.nesp_pr_device
        if self.action == "scan":
            pr_con.isscanning = True

        elif self.action == "connect" and pr_con.port.isdigit():
            self.disconnect()

            # Burası; zaten bağlıyız, disconnect yap ve dön demek oluyor
            if pr_con.isconnected or pr_con.isconnecting:
                return {"FINISHED"}

            # Bağlanmayı dene
            else:
                ip = pr_con.device
                global dev
                dev = Dirio(target=Webrepl,
                            kwargs={"host": ip,
                                    "port": int(pr_con.port),
                                    "password": pr_con.password})
                dev.start()

                pr_dev.ip = pr_con.device
                for i in scanag.devices():
                    if i[0] == ip:
                        pr_dev.ip = ip
                        pr_dev.mac = i[1]
                        pr_dev.vendor = i[2]

                context.window_manager.modal_handler_add(self)
                self._last_time = time.time()
                return self.timer_add(context)

        elif self.action == "disconnect":
            self.disconnect()

        return {"FINISHED"}

    def n_modal(self, context, event):
        if self.action == "connect":
            return self.modal_connect(context)

        return {'PASS_THROUGH'}

    def modal_connect(self, context):
        global dev
        if not dev:
            return self.timer_remove(context)

        # Bağlanamadı
        if dev.isconnect < 0:
            self.disconnect()
            return self.timer_remove(context)

        # Bağlandı
        if dev.isconnect > 0:
            bpy.ops.nesp.communication(start=True)
            return self.timer_remove(context)

        return {'PASS_THROUGH'}

    def disconnect(self):
        bpy.ops.nesp.communication(start=False)
        global dev
        if dev:
            try:
                dev.disconnect()
                dev.dr_terminate()
            except Exception:
                ...
            dev = None


class NESP_PT_Connection(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "nESP"
    bl_label = "Connection"
    bl_idname = "NESP_PT_connection"

    # @classmethod
    # def poll(__cls__, context):
    #     return context.scene.nesp_pr_head.tool_scene

    def draw(self, context):
        pr = context.scene.nesp_pr_connection

        row = self.layout.row(align=True)
        col1 = row.column()
        col1.alignment = "RIGHT"
        col1.label(text="Control")
        col1.label(text="Device")
        col1.label(text="Port")
        col1.label(text="Key")

        col1.scale_x = .8

        col2 = row.column(align=False)
        col2.prop(pr, "controller", text="")
        row = col2.row(align=True)
        row.prop(pr, "device", text="")
        row.prop(pr, "isscanning", text="", icon="VIEWZOOM")
        row.enabled = not pr.isscanning
        col2.prop(pr, "port", text="")
        col2.prop(pr, "password", text="")

        conn = pr.isconnected

        row = self.layout.row()

        if conn:
            row.operator(
                "nesp.connection",
                text="Connected",
                icon="LINKED",
                depress=True
            ).action = "disconnect"
        elif pr.isconnecting:
            row.alert = True
            row.operator(
                "nesp.connection",
                text="Connecting",
                icon="ANIM"
            ).action = "disconnect"
        else:
            row.operator(
                "nesp.connection",
                text="Connect",
                icon="UNLINKED",
            ).action = "connect"

    def draw_header_preset(self, context):
        pr = context.scene.nesp_pr_connection
        if not pr.isconnected:
            icon = "UNLINKED"
        elif pr.inwork:
            icon = "TIME"#"PROP_ON"
        else:
            icon = "MESH_CIRCLE"#"PROP_OFF"
        self.layout.prop(pr, "inwork",
                         icon_only=True,
                         emboss=False,
                         icon=icon)
                         #icon=("OUTLINER_OB_FORCE_FIELD" if pr.inwork else "PROP_OFF"))

# ##########################################################
# ##########################################################


class NESP_PR_MessageItem(PropertyGroup):
    ingoing: BoolProperty(
        name="Ingoing?",
        description="Message is Ingoing / Outgoing"
    )
    message: StringProperty(
        name="Messsage?",
        description="Message"
    )

    # time = time.time()
    # incoming = StringProperty(name="Incoming", default="")

    @classmethod
    def register(cls):
        Scene.nesp_pr_messageitem = PointerProperty(
            name="NESP_PR_MessageItem Name",
            description="NESP_PR_MessageItem Description",
            type=cls)

    @classmethod
    def unregister(cls):
        del Scene.nesp_pr_messageitem


class NESP_UL_Messages(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row()
        if item.message.startswith("Traceback (most recent call last):"):
            icon = "FUND"  # "FUND" or "COLORSET_01_VEC"
        elif item.ingoing:
            icon = "BLANK1"
        else:
            icon = "RIGHTARROW_THIN"
        row.prop(item, "message",
                 text="",  # time.strftime(item.time),
                 icon=icon,  # "BLANK1"  "NONE"
                 emboss=False)

        if not item.ingoing and item == data.items[data.active_item_index]:
            row.operator("nesp.messages", emboss=False, text="", icon="LOOP_BACK").msg = item.message
            pass
            # COPYDOWN
            # LOOP_BACK


class NESP_OT_Messages(Operator):
    bl_idname = "nesp.messages"
    bl_label = "Messages Operator"
    bl_description = "Clear Messages in the ListBox"
    bl_options = {'REGISTER'}

    action: EnumProperty(
        items=[
            ("add", "Add to message", ""),
            ("remove", "Remove to message", ""),
            ("clear", "Clear all messages", ""),
            ("clearqueu", "Clear Queu", "")
        ]
    )

    msg: StringProperty()

    def execute(self, context):

        pr_com = context.scene.nesp_pr_communication

        if self.action == "add":
            print("Developing ...")

        elif self.action == "remove":
            print("Developing ...")
            pr_com.items.remove(pr_com.active_item_index)

        elif self.action == "clear":
            pr_com.items.clear()
            pr_com.active_item_index = 0

        if self.msg:
            pr_com.messaging = self.msg

        return {'FINISHED'}


class NESP_PR_Communication(PropertyGroup):
    items: CollectionProperty(
        type=NESP_PR_MessageItem,
        name="Messages",
        description="All Message Items Collection"
    )
    active_item_index: IntProperty(
        name="Active Item",
        default=-1,
        description="Selected message index in Collection"
    )

    ############################################################
    # #################################################### QUEUE
    # Mesaj Kuyruğu
    queue_list = []
    queue_hist = []

    ############################################################
    # ################################################ MESSAGING
    def append_outgoing(self, context):
        if not self.messaging or not context.scene.nesp_pr_connection.isconnected:
            return

        #self.send(context, self.messaging)

        # Mesajı gönderilenler kuyruğuna ekle
        message = self.messaging
        self.queue_list.append(message)

        pr_com = context.scene.nesp_pr_communication

        # Mesajı Communication panele ekle
        item = pr_com.items.add()
        item.ingoing = False
        item.message = message
        pr_com.active_item_index = len(pr_com.items) - 1

        self.messaging = ""

    messaging: StringProperty(name="Outgoing Message",
                              update=append_outgoing)

    # ##########################################################
    # ########################################## WebRepl Methods

    def append_incoming(self, message):
        # Gelen cevapları panele ekle. Hepsini değil tabi ki

        for i in message.strip().split("\n"):
            c = i.strip()
            if not c:
                continue
            item = self.items.add()
            item.ingoing = True
            item.message = c
            self.active_item_index = len(self.items) - 1

    @classmethod
    def register(cls):
        Scene.nesp_pr_communication = PointerProperty(
            name="NESP_PR_Communication Name",
            description="NESP_PR_Communication Description",
            type=cls)

    @classmethod
    def unregister(cls):
        del Scene.nesp_pr_communication


class NESP_OT_Communication(Operator, Nodal):
    bl_idname = "nesp.communication"
    bl_label = "Communication"
    bl_description = "Communication Description"
    bl_options = {'REGISTER'}

    pr_con = None
    pr_com = None
    pr_dev = None
    pr_fsy = None
    delay = 0

    def n_invoke(self, context, event):
        dev.listen()
        self.pr_con = context.scene.nesp_pr_connection
        self.pr_com = context.scene.nesp_pr_communication
        self.pr_dev = context.scene.nesp_pr_device
        self.pr_fsy = context.scene.nesp_pr_filesystem

        bpy.ops.nesp.filesystem()

        return self.timer_add(context)

    mode = ""
    file = ""
    wait = 0

    def n_modal(self, context, event):
        if not self.pr_con.isconnected:
            unregister_modal(self)
            return self.timer_remove(context)

        if not self.pr_con.isconnected:
            return {"CANCELLED"}

        if self.pr_com.queue_list:
            val = self.pr_com.queue_list.pop(0)
            if type(val) in (tuple, list):
                if val[0] == WR_KEY._FILE_WRITE:
                    dev.put_file_content(val[1], val[2])
                elif val[0] == WR_KEY._FILE_READ:
                    print("Getur\n"*5)
                    dev.get_file_content(val[1])
            else:
                dev.send(val)

            self.pr_com.queue_hist.append(val)

            # Son gönderilenler yankı olarak geldiğinde boşuna ekrana eklemeleyim diye
            if len(self.pr_com.queue_hist) > 20:
                self.pr_com.queue_hist = self.pr_com.queue_hist[10:]

            return {'PASS_THROUGH'}

        a = dev.receives
        if a and len(a):
            cmds = WR_CMD.all()
            for i in a:
                if i in cmds or i in self.pr_com.queue_hist:
                    continue

                pr_dev = self.pr_dev
                if i.startswith(WR_KEY._OS_INFO):
                    # OSI: (sysname='esp8266', nodename='esp8266', release='2.0.0(5a875ba)',
                    # version='v1.13 on 2020-09-02', machine='ESP module (1M) with ESP8266')
                    ans = i.replace(WR_KEY._OS_INFO, "", 1).strip("() \t\r\n")
                    res = {}
                    for c in ans.split(","):
                        key, val = c.split("=", 1)
                        res[key.strip()] = val.strip("'")

                    pr_dev.machine = res.get("machine", "")
                    pr_dev.platform = res.get("sysname", "")
                    pr_dev.micropy_version = res.get("version", "")
                    pr_dev.release = res.get("release", "")

                elif i.startswith(WR_KEY._MEMORY):
                    # GC: total: WR_KEY, used: 3152, free: 34800
                    ans = i.replace(WR_KEY._MEMORY, "", 1).strip()

                    nums = re.findall(r'\d+', ans)
                    if len(nums) > 2:
                        pr_dev.memory = f"%{(int(nums[1]) * 100) // int(nums[0])}"

                elif i.startswith(WR_KEY._SIGNAL):
                    # SIG: -72
                    # https://hackster.imgix.net/uploads/attachments/1004079/frsy0u3k10zeout_large_zLKM8zCIqi.jpg?auto=compress%2Cformat&w=740&h=555&fit=max
                    ans = i.replace(WR_KEY._SIGNAL, "", 1).strip()
                    pr_dev.wifi_strength = f"%{100 + ((40 + int(ans)) * 2)}" if ans.replace("-", "").isdigit() else ans

                elif i.startswith(WR_KEY._FREQUENCE):
                    # FRQ: 80000000
                    ans = i.replace(WR_KEY._FREQUENCE, "", 1).strip()
                    pr_dev.frequence = f"{int(ans) / 1000000}MHz" if ans.isdigit() else ans

                elif i.startswith(WR_KEY._FLASH_SIZE):
                    # FLS: 1048576
                    ans = i.replace(WR_KEY._FLASH_SIZE, "", 1).strip()
                    pr_dev.flash_size = f"{int(ans) / 1048576}Mb" if ans.isdigit() else ans

                elif i.startswith(WR_KEY._LISTDIR):
                    # LDR: [('ay.py', 32768, 0, 18), ('boot.py', 32768, 0, 175), ('webrepl_cfg.py', 32768, 0, 16)]
                    ans = i.replace(WR_KEY._LISTDIR, "", 1).strip()
                    try:
                        res = eval(ans)
                    except:
                        res = []

                    pr_fsy = self.pr_fsy
                    pr_fsy.items.clear()
                    aii = pr_fsy.active_item_index
                    pr_fsy.active_item_index = 0

                    path = pr_fsy.path

                    for r in res:
                        item = pr_fsy.items.add()
                        item.name = r[0]
                        item.isdir = r[1] == 16384
                        item.path = os.path.join(path, r[0])
                        item.ismaking = False

                    if len(pr_fsy.items) > aii:
                        pr_fsy.active_item_index = aii

                elif i.startswith(WR_KEY._DIR):
                    # DIR: (True, ['__class__', 'from_bytes', 'to_bytes'], '2')
                    ans = i.replace(WR_KEY._DIR, "", 1).strip()
                    try:
                        res = eval(ans)
                    except:
                        res = (False, [], "")

                    pr_fsy = self.pr_fsy
                    pr_fsy.items.clear()
                    pr_fsy.active_item_index = 0

                    # if isval
                    if res[0]:
                        item = pr_fsy.items.add()
                        item.isval = True
                        item.isdir = False
                        item.name = res[2]
                    else:
                        for r in res[1]:
                            if r == "__class__":
                                continue
                            item = pr_fsy.items.add()
                            item.isval = False
                            item.isdir = True
                            item.name = r

                elif i.startswith(WR_KEY._MODULES):
                    # <MDL:
                    # ...
                    # MDL>
                    self.pr_fsy.items.clear()
                    self.mode = "module"
                    self.wait = time.time()

                elif i.startswith(WR_KEY.MODULES_):
                    # <MDL:
                    # ...
                    # MDL>
                    if self.mode == "module":
                        self.mode = ""

                elif i.startswith(WR_KEY._FILE_READ):
                    # FRD: filename.py
                    ans, data = i.split("\n", 1)
                    file_name = ans.replace(WR_KEY._FILE_READ, "", 1).strip()

                    if file_name in bpy.data.texts:
                        file = bpy.data.texts[file_name]
                        file.clear()
                    else:
                        file = bpy.data.texts.new(file_name)

                    file.write(data)

                    for area in context.screen.areas:
                        if area.type == "TEXT_EDITOR":
                            area.spaces[0].text = file

                elif self.mode == "module":
                    if i.startswith("Plus any mod"):
                        continue

                    if time.time() - self.wait > 3:
                        self.mode = ""

                    ans = i.strip().split()
                    pr_fsy = self.pr_fsy
                    pr_fsy.active_item_index = 0

                    for r in ans:
                        item = pr_fsy.items.add()
                        item.isdir = False
                        item.name = r

                elif i.startswith(WR_KEY._RELOAD_DIR_):
                    bpy.ops.nesp.filesystem(action="reload")

                else:
                    self.pr_com.append_incoming(i)

            a = dev.receives
            if a:
                a.clear()

        # dev'in bir değişkeninde WebRepl ile alınan cevaplar depolanıyor olacak.
        # Oradaki cevapları alıyoruz okuyoruz.
        # Eğer değişmesi gereken değişken varsa oraya aktarıyoruz.
        # Değişmesi gereken birşey yoksa, doğrudan Comm panele ekliyoruz

        # Eğer bir fonksiyon çalışırsa, alanları yenile
        # if dev.dr_binds_check():
        #     if context.area:
        #         context.area.tag_redraw()

        return {'PASS_THROUGH'}


class NESP_PT_Communication(Panel):
    bl_idname = "NESP_PT_communication"
    bl_label = "Communication"
    bl_region_type = "UI"
    bl_space_type = "VIEW_3D"
    bl_category = "nESP"

    # bl_options = {"DEFAULT_CLOSED", "HIDE_HEADER"}

    # @classmethod
    # def poll(__cls__, context):
    #     return context.scene.nesp_pr_connection.isconnected

    def draw(self, context):
        layout = self.layout
        layout.enabled = context.scene.nesp_pr_connection.isconnected

        pr = context.scene.nesp_pr_communication

        row = layout.row(align=True)
        row.operator("nesp.commands", text="Raw").command = WR_CMD.CONTROL_A
        row.operator("nesp.commands", text="Normal").command = WR_CMD.CONTROL_B
        row.operator("nesp.commands", text="Interrupt").command = WR_CMD.CONTROL_C
        row.operator("nesp.commands", text="Reset").command = WR_CMD.CONTROL_D

        col = layout.column(align=True)
        col.template_list(
            "NESP_UL_Messages",  # TYPE
            "nesp_ul_messages",  # ID
            pr,  # Data Pointer
            "items",  # Propname
            pr,  # active_dataptr
            "active_item_index",  # active_propname
            rows=3,
            type='DEFAULT'
        )

        row = col.row(align=True)

        # if not context.scene.nesp_pr_connection.isconnected:
        #    row.enabled = False
        #    row.alert = True

        row.prop(pr, "messaging", text="", full_event=False)
        row.operator("nesp.messages", text="", icon="TRASH", ).action = "clear"


class NESP_OT_Commands(Operator):
    bl_idname = "nesp.commands"
    bl_label = "nESP Commands"
    bl_description = ""
    bl_options = {'REGISTER'}

    command: StringProperty()

    def execute(self, context):
        pr_com = context.scene.nesp_pr_communication

        if self.command == "get_infos":
            pr_com.queue_list.extend([WR_CMD.SIGNAL,
                                      WR_CMD.MEMORY,
                                      WR_CMD.OS_INFO,
                                      WR_CMD.FREQUENCE,
                                      WR_CMD.FLASH_SIZE,
                                      ])
        elif self.command == "get_status":
            pr_com.queue_list.extend([WR_CMD.MEMORY, WR_CMD.SIGNAL])

        elif self.command == WR_CMD.MEMORY_OPTIMIZE:
            pr_com.queue_list.append(WR_CMD.MEMORY_OPTIMIZE)
            pr_com.queue_list.append(WR_CMD.MEMORY)
        else:
            pr_com.queue_list.append(self.command)

        return {'FINISHED'}


class NESP_PR_Device(PropertyGroup):
    ip: StringProperty(name="IP Address")
    mac: StringProperty(name="MAC Address")
    vendor: StringProperty(name="Vendor Name")

    machine: StringProperty(name="Machine")
    platform: StringProperty(name="Platform")
    release: StringProperty(name="Release")
    micropy_version: StringProperty(name="MicroPy Version")

    memory: StringProperty(name="Used Memory")
    frequence: StringProperty(name="Frequence")
    flash_size: StringProperty(name="Flash Size")
    wifi_strength: StringProperty(name="Wifi Signal Quality")

    @classmethod
    def register(cls):
        Scene.nesp_pr_device = PointerProperty(
            name="NESP_PT_Device Name",
            description="NESP_PT_Device Description",
            type=cls
        )

    @classmethod
    def unregister(cls):
        del Scene.nesp_pr_device



class NESP_PT_Device(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "nESP"
    bl_label = "Device"
    bl_idname = "NESP_PT_device"

    def draw(self, context):
        pr = context.scene.nesp_pr_device

        self.layout.enabled = context.scene.nesp_pr_connection.isconnected
        row = self.layout.row(align=True)
        col1 = row.column()
        col1.alignment = "RIGHT"
        col1.label(text="IP", icon="MOD_PARTICLES")
        col1.label(text="MAC", icon="RNA")
        col1.label(text="Vendor", icon="MOD_BUILD")

        col2 = row.column()
        col2.label(text=pr.ip)
        col2.label(text=pr.mac)
        col2.label(text=pr.vendor)


class NESP_PT_DeviceDetails(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "nESP"
    bl_label = "Details"
    bl_parent_id = "NESP_PT_device"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        pr = context.scene.nesp_pr_device

        layout = self.layout
        layout.enabled = context.scene.nesp_pr_connection.isconnected

        row = layout.row(align=True)
        row.operator("nesp.commands", text="Get Device Info", icon="WORDWRAP_ON").command = "get_infos"

        row = layout.row(align=True)
        col1 = row.column()
        col1.alignment = "RIGHT"
        col1.label(text="Machine", icon="FILE_ARCHIVE")      # NODE_SEL PACKAGE SYSTEM
        col1.label(text="Platform", icon="DESKTOP")     # NODE  UGLYPACKAGE DESKTOP   PARTICLE_DATA
        col1.label(text="MicroPy", icon="SCRIPT")      # SCRIPT
        col1.label(text="Release", icon="PACKAGE")      # FILE_TEXT   LINENUMBERS_ON  WORDWRAP_ON
        col1.label(text="Flash Size", icon="DISK_DRIVE")   # DISK_DRIVE EXTERNAL_DRIVE
        col1.label(text="Frequence", icon="FORCE_HARMONIC")    # SEQ_HISTOGRAM  RIGID_BODY   FORCE_HARMONIC

        col2 = row.column()
        col2.label(text=pr.machine)
        col2.label(text=pr.platform)
        col2.label(text=pr.micropy_version)
        col2.label(text=pr.release)
        col2.label(text=pr.flash_size)
        col2.label(text=pr.frequence)


class NESP_PT_DeviceStatus(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "nESP"
    bl_label = "Status"
    bl_parent_id = "NESP_PT_device"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        pr = context.scene.nesp_pr_device

        layout = self.layout
        layout.enabled = context.scene.nesp_pr_connection.isconnected

        row = layout.row(align=True)
        row.operator("nesp.commands", text="Get Status Info", icon="STATUSBAR").command = "get_status"

        row = layout.row(align=True)

        col1 = row.column()
        col1.alignment = "RIGHT"
        col1.label(text="Memory", icon="MEMORY")
        col1.label(text="Signal", icon="MOD_WAVE")

        col2 = row.column()
        col2.alignment = "RIGHT"

        row2 = col2.row(align=True)
        row2.label(text=pr.memory)
        row2.operator("nesp.commands", text="", emboss=False, icon="BRUSH_DATA").command = WR_CMD.MEMORY_OPTIMIZE
        row2.operator("nesp.commands", text="", emboss=False, icon="FILE_REFRESH").command = WR_CMD.MEMORY

        row3 = col2.row(align=True)
        row3.label(text=pr.wifi_strength)
        row3.operator("nesp.commands", text="", emboss=False, icon="FILE_REFRESH").command = WR_CMD.SIGNAL

        col2.scale_x = 1.2


# ##########################################################
# ##########################################################

class NESP_UL_FileSystems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        if item.isval:
            icon = "DISK_DRIVE"
        elif item.isdir:
            icon = "FILEBROWSER"
        elif item.name.endswith(".py"):
            icon = "FILE_SCRIPT"  # "SCRIPTPLUGINS"  # "FUND" or "COLORSET_01_VEC"
        else:
            icon = "BLANK1"
        row.prop(item, "name",
                 text="",
                 icon=icon,
                 emboss=False)

        # Eğer bu item seçiliyse;
        if item == data.items[data.active_item_index]:
            # print("context", context)
            # print("layout", layout)
            # print("data", data)
            # print("item", item)
            # print("icon", icon)
            # print("active_data", active_data)
            # print("active_propname", active_propname)
            # print("", dir(data.items))
            # print("", )
            # print("", )

            pr = context.scene.nesp_pr_filesystem
            md = pr.mode
            if md == "os.dir" or (md == "im.dir" and (not pr.path or pr.path == os.sep)):
                row.operator("nesp.filesystem", text="", emboss=False, icon="TRASH").action = "remove"

            if item.isdir:
                row.operator("nesp.filesystem", text="", emboss=False, icon="RIGHTARROW_THIN").action = "go"

            if md == "os.dir" and not item.isdir:
                row.operator("nesp.filesystem", text="", emboss=False, icon="IMPORT").action = "download"

                if item.path in bpy.data.texts:
                    row.operator("nesp.filesystem", text="", emboss=False, icon="EXPORT").action = "upload"

                if item.name.endswith(".py"):
                    row.operator("nesp.filesystem", text="", emboss=False, icon="PLAY").action = "run"

            if md == "module":
                row.operator("nesp.filesystem", text="", emboss=False, icon="APPEND_BLEND").action = "run"


class NESP_PR_FileSystemItem(PropertyGroup):
    def update_name(self, context):
        pr = context.scene.nesp_pr_filesystem
        if self.ismaking or pr.mode != "os.dir":
            return
        path_old = self.path
        path_new = self.path = os.path.join(os.path.dirname(path_old), self.name)
        if path_old == path_new:
            return

        context.scene.nesp_pr_communication.queue_list.append(WR_CMD.RENAME.format(path_old, path_new))

    name: StringProperty(
        name="Messsage?",
        description="Message",
        update=update_name
    )
    path: StringProperty(
        name="Path"
    )
    isdir: BoolProperty(
        name="Is Directory?"
    )
    isval: BoolProperty(
        name="Is Value?"
    )
    # Itemler ilk oluşturulma esnasında değişirken, update'ler çalışmasın diye...
    ismaking: BoolProperty(default=True)

    @classmethod
    def register(cls):
        Scene.nesp_pr_filesystemitem = PointerProperty(
            name="NESP_PR_FileSystemItem Name",
            description="NESP_PR_FileSystemItem Description",
            type=cls)

    @classmethod
    def unregister(cls):
        del Scene.nesp_pr_filesystemitem


class NESP_PR_FileSystem(PropertyGroup):
    items: CollectionProperty(
        type=NESP_PR_FileSystemItem,
        name="Messages",
        description="All Message Items Collection"
    )
    active_item_index: IntProperty(
        name="Active Item",
        default=-1,
        description="Selected message index in Collection"
    )

    # #########################################
    # #########################################

    def reload(self, context):
        self.path = os.sep
        bpy.ops.nesp.filesystem(action="reload")

    mode: EnumProperty(
        items=[("os.dir", "Files", "Directory"),
               ("im.dir", "NameSpace", "NameSpace"),
               ("module", "Modules", "Modules")
               ],
        name="Listing Metods",
        description="Select listing methods",
        update=reload
    )

    path: StringProperty(name="Active Path", default=os.sep)    # , update=reload

    @classmethod
    def register(cls):
        Scene.nesp_pr_filesystem = PointerProperty(
            name="NESP_PR_FileSystem Name",
            description="NESP_PR_FileSystem Description",
            type=cls
        )

    @classmethod
    def unregister(cls):
        del Scene.nesp_pr_filesystem


class NESP_OT_FileSystem(Operator):
    bl_idname = "nesp.filesystem"
    bl_label = "nESP FileSystem"
    bl_options = {'REGISTER'}
    bl_description = ""

    action: EnumProperty(
        items=[
            ("reload", "", ""),
            ("back", "", ""),
            ("home", "", ""),
            ("refresh", "", ""),
            ("new_dir", "", ""),
            ("new_file", "", ""),
            ("download", "", ""),
            ("upload", "", ""),
            ("go", "", ""),
            ("run", "", ""),
            ("remove", "", ""),
        ]
    )

    def execute(self, context):

        pr_com = context.scene.nesp_pr_communication
        pr_fsy = context.scene.nesp_pr_filesystem

        mode = pr_fsy.mode
        if self.action == "back":
            pr_fsy.path = os.path.dirname(pr_fsy.path) or os.sep

        elif self.action == "home":
            pr_fsy.path = os.sep

        elif self.action == "refresh":
            pr_fsy.path = pr_fsy.path

        elif self.action == "go":
            pr_fsy.path = os.path.join(pr_fsy.path, pr_fsy.items[pr_fsy.active_item_index].name)

        elif self.action == "run":
            # TODO !!! Modül olarak içe aktarmadan önce, eskisini silen kısmı da ekle
            item = pr_fsy.items[pr_fsy.active_item_index]
            path = os.path.join(pr_fsy.path, item.name)
            code = path.strip(os.sep).replace('/', '.').rsplit('.', 1)[0]
            pr_com.queue_list.append(WR_CMD.RUN.format(code))

        elif self.action == "remove":
            item = pr_fsy.items[pr_fsy.active_item_index]
            path = os.path.join(pr_fsy.path, item.name)

            if mode == "os.dir" and item.isdir:
                pr_com.queue_list.append(WR_CMD.REMOVE_DIR.format(path))
            elif mode == "os.dir":
                pr_com.queue_list.append(WR_CMD.REMOVE_FILE.format(path))
            elif mode == "im.dir":
                pr_com.queue_list.append(WR_CMD.REMOVE_VALUE.format(path.strip(f"{os.sep} \r\n")))

        elif self.action == "download":
            item = pr_fsy.items[pr_fsy.active_item_index]
            pr_com.queue_list.append((WR_KEY._FILE_READ, item.path))

        elif self.action == "upload":
            item = pr_fsy.items[pr_fsy.active_item_index]
            if item.path in bpy.data.texts:
                data = bpy.data.texts[item.path].as_string()
                pr_com.queue_list.append((WR_KEY._FILE_WRITE, data, item.path))

        elif self.action == "new_dir" and pr_fsy.mode == "os.dir":
            names = [i.name for i in pr_fsy.items]
            name = "NewFolder"
            no = 1
            while name in names:
                name = f"NewFolder{no}"
                no += 1

            path = os.path.join(pr_fsy.path, name)
            pr_com.queue_list.append(WR_CMD.MAKE_DIR.format(path))

        elif self.action == "new_file" and pr_fsy.mode == "os.dir":
            names = [i.name for i in pr_fsy.items]

            name = "NewFile.py"
            no = 1
            while name in names:
                name = f"NewFile{no}.py"
                no += 1

            path = os.path.join(pr_fsy.path, name)
            pr_com.queue_list.append(WR_CMD.FILE_WRITE.format(path, b"\n"))

        # Reload : Her seferinde yenile
        path = pr_fsy.path

        if mode == "os.dir":
            path = os.sep + pr_fsy.path if not path.startswith(os.sep) else path
            pr_com.queue_list.append(WR_CMD.LISTDIR.format(path))

        elif mode == "im.dir":
            if path and path not in (os.sep, "."):
                path = path.strip(os.sep).replace(os.sep, ".")
                pr_com.queue_list.append(WR_CMD.DIR_VALUE.format(path))
            else:
                pr_com.queue_list.append(WR_CMD.DIR_DEFAULT)

        else:
            pr_com.queue_list.append(WR_CMD.MODULES)

        return {'FINISHED'}


class NESP_PT_FileSystem(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "nESP"
    bl_label = "File System"
    bl_idname = "NESP_PT_filesystem"

    def draw(self, context):
        pr = context.scene.nesp_pr_filesystem

        layout = self.layout
        layout.enabled = context.scene.nesp_pr_connection.isconnected
        row1 = layout.row()
        row1.prop(pr, "mode", expand=True)

        # ######################################
        # ################################## Bar
        row2 = layout.row(align=True)
        row2.operator("nesp.filesystem", text="", icon="BACK").action = "back"
        row2.operator("nesp.filesystem", text="", icon="HOME").action = "home"
        row2.operator("nesp.filesystem", text="", icon="FILE_REFRESH").action = "refresh"

        # if pr.mode == "os.dir":
        #     row2.prop(pr, "path", text="")
        # elif pr.mode == "im.dir":
        #     row2.prop(pr, "path", text="")
        # else:
        row2.prop(pr, "path", text="")

        row2.operator("nesp.filesystem", text="", icon="NEWFOLDER").action = "new_dir"
        row2.operator("nesp.filesystem", text="", icon="FILE_NEW").action = "new_file"

        # row2 = layout.row(align=True)
        # row2.separator()
        # row2.operator("ncnc.objects", icon="NEWFOLDER", text="")#.action = "newdir"
        # row2.operator("ncnc.objects", icon="FILE_NEW", text="")#.action = "newfile"
        # row2.separator()
        # row2.operator("ncnc.objects", icon="TRASH", text="")#.action = "delete"
        # ######################################
        # ############################## ListBox
        pr_fs = context.scene.nesp_pr_filesystem

        row = layout.row()
        col2 = row.column(align=True)
        col2.template_list(
            "NESP_UL_FileSystems",  # TYPE
            "nesp_ul_filesystems",  # ID
            pr_fs,  # Data Pointer
            "items",  # Propname
            pr_fs,  # active_dataptr
            "active_item_index",  # active_propname
            rows=3,
            type='DEFAULT'
        )


# ##########################################################
# ##########################################################
class NESP_UL_Pins(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.scale_x = 0
        row.prop(item, "no", text="", emboss=False, slider=True)
        row.scale_x = 5
        row.prop(item, "name", text="", emboss=False)
        row.scale_x = 2
        row.prop(item, "io", text="", emboss=False) # TRACKING_CLEAR_BACKWARDS  TRACKING_CLEAR_FORWARDS

        len_item = len(data.items)
        act_indx = data.active_item_index
        # Eğer bu item seçiliyse;
        if len_item > act_indx and item == data.items[act_indx]:
            # print("context", context)
            # print("layout", layout)
            # print("data", data)
            # print("item", item)
            # print("icon", icon)
            # print("active_data", active_data)
            # print("active_propname", active_propname)
            # print("", dir(data.items))
            # print("", )
            # print("", )

            pr = context.scene.nesp_pr_pins
            md = pr.mode
            if md == "os.dir" or (md == "im.dir" and (not pr.path or pr.path == os.sep)):
                row.operator("nesp.pins", text="", emboss=False, icon="TRASH").action = "remove"


class NESP_PR_PinItem(PropertyGroup):
    name: StringProperty(
        name="Pin name",
        description="Pin name"
    )
    no: IntProperty(
        name="Pin No",
        description="",
        min=0,
        max=50
    )
    io: EnumProperty(
        items=[
            ("Pin.IN", "IN", "Pin.IN"),
            ("Pin.OUT", "OUT", "Pin.OUT"),
        ],
        name="Pin Mode"
    )
    value: BoolProperty(
        name="Off/On"
    )

    @classmethod
    def register(cls):
        Scene.nesp_pr_pinitem = PointerProperty(
            name="NESP_PR_PinItem Name",
            description="NESP_PR_PinItem Description",
            type=cls)

    @classmethod
    def unregister(cls):
        del Scene.nesp_pr_pinitem


class NESP_PR_Pin(PropertyGroup):
    items: CollectionProperty(
        type=NESP_PR_PinItem,
        name="Pins",
        description="All Pin Items Collection"
    )
    active_item_index: IntProperty(
        name="Active Item",
        default=-1,
        description="Selected pin index in Collection"
    )

    # #########################################
    # #########################################
    mode: EnumProperty(
        items=[("control", "Control", ""),
               ("setup", "Setup", ""),
               ],
        name="Mode",
        description="Select Mode"
    )

    @classmethod
    def register(cls):
        Scene.nesp_pr_pins = PointerProperty(
            name="NESP_PR_Pin Name",
            description="NESP_PR_Pin Description",
            type=cls
        )

    @classmethod
    def unregister(cls):
        del Scene.nesp_pr_pins


class NESP_OT_Pins(Operator):
    bl_idname = "nesp.pins"
    bl_label = "nESP Pins"
    bl_options = {'REGISTER'}
    bl_description = ""

    action: EnumProperty(
        items=[
            ("add", "Add", ""),
            ("remove", "Remove", ""),
            ("clear", "Remove", ""),
            ("import", "Import", ""),
            ("export", "Export", ""),
            ("reload", "Reload", ""),
        ]
    )

    def execute(self, context):
        pr_com = context.scene.nesp_pr_communication
        pr_pin = context.scene.nesp_pr_pins

        if self.action == "add":
            pinler = {
                "esp32": [0, 2, 4, 5, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19,
                          21, 22, 23, 25, 26, 27, 32, 33, 34, 35, 36, 39],
                "esp8266": [0, 1, 2, 3, 4, 5, 12, 13, 14, 15]
             }
            for i in pr_pin.items:
                if i.no in pinler["esp32"]:
                    pinler["esp32"].remove(i.no)

            item = pr_pin.items.add()
            item.no = pinler["esp32"][0] if pinler["esp32"] else 0
            item.io = "Pin.OUT"
            item.name = "Pin Name"
            pr_pin.active_item_index = len(pr_pin.items) - 1

        if self.action == "remove":
            act_indx = pr_pin.active_item_index
            len_item = len(pr_pin.items)
            if len_item > act_indx:
                pr_pin.items.remove(pr_pin.active_item_index)

            if len_item - 1 > 0 and act_indx - 1 > -1:
                pr_pin.active_item_index -= 1


        if self.action == "clear":
            pr_pin.items.clear()

        return {'FINISHED'}


class NESP_PT_Pins(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "nESP"
    bl_label = "Pins"
    bl_idname = "NESP_PT_pins"

    def draw(self, context):
        pr = context.scene.nesp_pr_pins

        layout = self.layout
        # layout.enabled = context.scene.nesp_pr_connection.isconnected
        row1 = layout.row()
        row1.operator("nesp.pins", text="", icon="FILE_REFRESH").action = "reload"
        row1.prop(pr, "mode", expand=True)

        # row2 = layout.row(align=True)
        # row2.operator("nesp.pins", text="", icon="ADD").action = "add"
        # row2.operator("nesp.pins", text="", icon="REMOVE").action = "remove"
        # row2.operator("nesp.pins", text="", icon="TRASH").action = "clear"
        # row2.label(text=" ", icon="BLANK1")
        # row2.operator("nesp.pins", text="", icon="FILE_REFRESH").action = "reload"
        # row2.label(text=" ", icon="BLANK1")
        # row2.operator("nesp.pins", text="", icon="IMPORT").action = "import"
        # row2.operator("nesp.pins", text="", icon="EXPORT").action = "export"



        # ######################################
        # ############################## ListBox
        row = layout.row()

        col1 = row.column(align=True)
        col1.operator("nesp.pins", text="", icon="ADD").action = "add"
        col1.operator("nesp.pins", text="", icon="REMOVE").action = "remove"
        col1.operator("nesp.pins", text="", icon="TRASH").action = "clear"
        col1.separator()
        # col1.label(text="", icon="BLANK1")
        col1.separator()
        # col1.label(text=" ", icon="BLANK1")
        col1.operator("nesp.pins", text="", icon="EXPORT").action = "export"
        col1.operator("nesp.pins", text="", icon="IMPORT").action = "import"

        col2 = row.column(align=True)
        col2.template_list(
            "NESP_UL_Pins",  # TYPE
            "nesp_ul_pins", # ID
            pr,             # Data Pointer
            "items",        # Propname
            pr,             # active_dataptr
            "active_item_index",  # active_propname
            rows=3,
            type='DEFAULT'
        )


classes = [
    NESP_PR_Connection,
    NESP_OT_Connection,
    NESP_PT_Connection,

    NESP_PR_MessageItem,
    NESP_PR_Communication,
    NESP_OT_Communication,
    NESP_UL_Messages,
    NESP_OT_Messages,
    NESP_PT_Communication,

    NESP_OT_Commands,

    NESP_PR_Device,
    NESP_PT_Device,
    NESP_PT_DeviceDetails,
    NESP_PT_DeviceStatus,

    NESP_UL_FileSystems,
    NESP_PR_FileSystemItem,
    NESP_PR_FileSystem,
    NESP_OT_FileSystem,
    NESP_PT_FileSystem,
NESP_UL_Pins,
NESP_PR_PinItem,
NESP_PR_Pin,
NESP_OT_Pins,
NESP_PT_Pins,
]


def register():
    for i in classes:
        bpy.utils.register_class(i)


def unregister():
    for i in classes[::-1]:
        bpy.utils.unregister_class(i)


if __name__ == "__main__":
    register()
