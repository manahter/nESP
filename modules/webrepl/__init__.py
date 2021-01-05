#!/usr/bin/env python
import os
import re
import time
import struct
import socket
from threading import Thread
try:
    from ..rapor import Rapor
except:
    # Bu dosyanın bulunduğu üst dizini, python sistemine ekliyoruz ki, modül ararken burayada baksın
    _dirname = os.path.dirname(__file__)
    updirname = os.path.dirname(_dirname)

    import sys

    sys.path.append(updirname)
    from rapor import Rapor

rapor = Rapor(module="WebRepl",
              module_path=os.path.dirname(__file__),
              mode="Ai",
              keep=True
              )

# Assyncio için kaynak;
# https://developer.blender.org/diffusion/BCA/browse/master/blender_cloud/async_loop.py$127

# Treat this remote directory as a root for file transfers
SANDBOX = ""
# SANDBOX = "/tmp/webrepl/"

WEBREPL_REQ_S = "<2sBBQLH64s"
WEBREPL_PUT_FILE = 1
WEBREPL_GET_FILE = 2
WEBREPL_GET_VER = 3

# Karşı cihaza yükleyeceğimiz dosyanın adı SETUP_FILENAME.py
SETUP_FILENAME = "bilen"

# Karşı cihaza yükleyeceğimiz dosyanın içeriği
SETUP_CONTENT = rb"""
from machine import Pin

pins = []

for i in (0, 2):
    p = Pin(i, Pin.OUT)
    p.off()
    pins.append(p)
"""

HANDSHAKE_TEXT = b"""\
GET / HTTP/1.1\r
Host: localhost\r
Connection: Upgrade\r
Upgrade: websocket\r
Sec-WebSocket-Key: foo\r
\r
"""


# from ctypes import int


class websocket:
    def __init__(self, s):
        self.s = s
        self.buf = b""

    def writetext(self, data):
        self.write(data, istext=True)

    def write(self, data, istext=False):
        ll = len(data)
        if ll < 126:
            # TODO: hardcoded "binary" type
            hdr = struct.pack(">BB", (0x82, 0x81)[istext], ll)
        else:
            hdr = struct.pack(">BBH", (0x82, 0x81)[istext], 126, ll)
        self.s.send(hdr)
        self.s.send(data)

    def recvexactly(self, sz):
        res = b""

        while sz:
            data = self.s.recv(sz)

            if not data:
                break

            res += data
            sz -= len(data)
        return res

    def read(self, size, text_ok=False, size_match=True):
        if not self.buf:
            while True:
                hdr = self.recvexactly(2)
                assert len(hdr) == 2
                fl, sz = struct.unpack(">BB", hdr)
                if sz == 126:
                    hdr = self.recvexactly(2)
                    assert len(hdr) == 2
                    (sz,) = struct.unpack(">H", hdr)
                if fl == 0x82:
                    break
                if text_ok and fl == 0x81:
                    break

                rapor.info_grey(websocket.read.__name__, f"Got unexpected websocket record of type, skipping it {fl}")

                while sz:
                    skip = self.s.recv(sz)

                    rapor.info_grey(websocket.read.__name__, f"Skip data ; {skip}")
                    sz -= len(skip)
            data = self.recvexactly(sz)
            assert len(data) == sz
            self.buf = data

        d = self.buf[:size]
        self.buf = self.buf[size:]
        if size_match:
            assert len(d) == size, len(d)
        return d

    @staticmethod
    def ioctl(req, val):
        assert req == 9 and val == 2


class Webrepl:
    isconnect = -1
    '''
    -1: Not connected, 
    0: Connecting, 
    1: Connected
    '''

    timeout = 5
    receives = []
    get_files = []

    def __init__(self, host="", port=8266, password="", auto=True):
        """"""
        self.host = host
        self.port = port
        self.password = password
        self.auto = auto

        self.s = None
        self.ws = None
        self.thread = None

    def start(self):
        # Connecting
        self.isconnect = 0
        if self.auto:
            self.connect()
            self.login()

    def client_handshake(self, sock):
        cl = sock.makefile("rwb", 0)
        cl.write(HANDSHAKE_TEXT, )

        st = time.time()
        while cl.readline() != b"\r\n":
            if time.time() - st > self.timeout:
                rapor.warning(Webrepl.client_handshake.__name__, f"Timeout ; {self.timeout}")
                return False

        return True

    def connect(self, host=None, port=None):
        if host:
            self.host = host
        if port:
            self.port = port

        if not self.host:
            self.isconnect = -1
            return

        rapor.notice(Webrepl.connect.__name__, f"Trying connecting to {self.host} {self.port}")

        self.s = socket.socket()

        addr = socket.getaddrinfo(self.host, self.port)[0][4]

        self.s.settimeout(self.timeout)

        try:
            self.s.connect(addr)
        except:
            self.isconnect = -1
            rapor.notice(Webrepl.connect.__name__, f"Connection failed")
            return

        rapor.info(Webrepl.connect.__name__, "Handshake")

        if self.client_handshake(self.s):
            self.ws = websocket(self.s)
        else:
            self.isconnect = -1

    def disconnect(self):
        if self.s:
            self.s.close()
        self.s = None
        self.ws = None
        self.isconnect = -1
        rapor.info_grey(Webrepl.disconnect.__name__, "Disconnected")

    def login(self, passwd=""):
        if passwd:
            self.password = passwd

        if not (self.password and self.ws):
            self.isconnect = -1
            return

        rapor.info_grey(Webrepl.login.__name__, f"Started")

        while True:
            c = self.ws.read(1, text_ok=True)
            if c == b":":
                assert self.ws.read(1, text_ok=True) == b" "
                break
        self.ws.write(self.password.encode("utf-8") + b"\r")

        rapor.info_grey(Webrepl.login.__name__, f"Send Password ; {self.password}")

        resp = self.ws.read(64, text_ok=True, size_match=False)
        # b'\r\nWebREPL connected\r\n>>> '
        # b'\r\nAccess denied\r\n'
        if b"WebREPL connected" in resp:
            self.isconnect = 1

        rapor.info(Webrepl.login.__name__, f"Response ; {resp.decode('utf-8').strip()}")

        # self.send("import sys, os, machine, gc, esp, network, micropython")
        self.send("import os")

    def send(self, cmd):
        """Sadece gönderir. Okuma yapmaz olacak"""
        if self.isconnect < 0:
            return ""

        rapor.info(Webrepl.send.__name__, f"Sending Command ; {cmd}")
        self.ws.writetext(cmd.encode("utf-8") + b"\r\n")

    def put_file(self, local_file, remote_file):
        sz = os.stat(local_file)[6]
        dest_fname = (SANDBOX + remote_file).encode("utf-8")
        rec = struct.pack(WEBREPL_REQ_S, b"WA", WEBREPL_PUT_FILE, 0, 0, sz, len(dest_fname), dest_fname)

        rapor.info(Webrepl.put_file.__name__, f"Put file struct {rec} {len(rec)}")

        self.ws.write(rec[:10])
        self.ws.write(rec[10:])
        # if self.read_resp() != 0:
        #     rapor.error(Webrepl.put_file.__name__, f"Error: Okuma halindeyken başka işlem çağırıldı")
        #     return

        cnt = 0
        with open(local_file, "rb") as f:
            while True:
                rapor.info_grey(Webrepl.put_file.__name__, f"Sent {cnt} of {sz}")
                buf = f.read(1024)
                if not buf:
                    break
                self.ws.write(buf)
                cnt += len(buf)

        # if self.read_resp() != 0:
        #     rapor.error(Webrepl.put_file.__name__, f"Error: Yarıda kesildi")
        #     return

    def put_file_content(self, file_content, remote_file):
        local_file = "volatilefile"
        with open(local_file, "wb") as f:
            f.write(file_content.encode("utf-8"))

        self.put_file(local_file, remote_file)
        os.remove(local_file)
        return "OK"

    def listen(self, thread=False):
        if not thread:
            self.thread = Thread(target=self.listen, kwargs={"thread": True})
            self.thread.start()
            return

        """Listener olarak değiştir ve sürekli döngüde kal. girdikten sonra Timeout Sonsuz olsun. Thread ekle"""

        resp = b''
        self.s.settimeout(1)

        while self.s and self.ws and self.isconnect > 0:
            try:
                if self.get_files:
                    file_name = self.get_files.pop(0)
                    rsp = self._get_file_content(file_name)
                    self.receives.append(f"{WR_KEY._FILE_READ} {file_name}\n{rsp}")
                    continue
                else:
                    r = self.ws.read(1024, text_ok=True, size_match=False)
            except Exception as e:
                # print(e)
                # rapor.notice(Webrepl.listen.__name__, f"Finished")
                # print(self.receives)
                continue

            if r in (b'\r\n', b'>>> '):
                rsp = resp.decode("utf-8")
                self.receives.append(rsp)
                rapor.info(Webrepl.listen.__name__, f"{rsp}")
                resp = b''
                continue

            resp = resp + r

        return 0

    def get_file_content(self, remote_file):
        self.get_files.append(remote_file)

    def _get_file_content(self, remote_file):

        content = b''
        src_fname = remote_file.encode("utf-8")
        rec = struct.pack(WEBREPL_REQ_S, b"WA", WEBREPL_GET_FILE, 0, 0, 0, len(src_fname), src_fname)

        rapor.info(Webrepl._get_file_content.__name__, f"Get file content struct {rec} {len(rec)}")

        self.ws.write(rec)

        if self.read_resp() != 0:
            rapor.error(Webrepl._get_file_content.__name__, f"Error: Okuma halindeyken başka işlem çağırıldı")
            return ""

        cnt = 0
        while True:
            self.ws.write(b"\0")
            (sz,) = struct.unpack("<H", self.ws.read(2))
            if sz == 0:
                break
            while sz:
                buf = self.ws.read(sz)
                if not buf:
                    raise OSError()
                cnt += len(buf)
                content += buf
                sz -= len(buf)

                rapor.info_grey(Webrepl.get_file_content.__name__, f"Received {cnt} bytes")

        if self.read_resp() != 0:
            rapor.error(Webrepl.get_file_content.__name__, f"Error: Yarıda kesildi")
            return ""

        return content.decode("utf-8")

    def read_resp(self):
        data = self.ws.read(4)
        sig, code = struct.unpack("<2sH", data)
        assert sig == b"WB"
        return code

    def send_req(self, op, sz=0, fname=b""):
        rec = struct.pack(WEBREPL_REQ_S, b"WA", op, 0, 0, sz, len(fname), fname)

        rapor.info_grey(Webrepl.send_req.__name__, f"Send request {rec} {len(rec)}")

        self.ws.write(rec)

    def baudrate(self):
        pass
        # def baudrate(rate):
        #     machine.mem32[0x60000014] = int(80000000 / rate)

        # Kaynak; https://forum.micropython.org/viewtopic.php?t=2078
        # veya
        # buradan araştır; https://github.com/espressif/esptool/blob/b96df73ba75cccd38ed6730829d8d01c0205e508/espressif/efuse/emulate_efuse_controller_base.py#L58
        # https://github.com/espressif/esptool/blob/master/esptool.py#L1071
        # wr.send(")


class WR_KEY:
    _PIN = "PIN: "
    _DIR = "DIR: "
    _MEMORY = "GC: "
    _SIGNAL = "SIG: "
    MODULES_ = "MDL>"
    _OS_INFO = "OSI: "
    _LISTDIR = "LDR: "
    _PLATFORM = "PLT: "
    _MODULES = "<MDL: "
    FILE_READ_ = "FRD>"
    _FREQUENCE = "FRQ: "
    _FILE_READ = "<FRD: "
    _FLASH_SIZE = "FLS: "
    _FIRMWARE_CHECK = "FWC: "
    _RELOAD_DIR_ = "RDR: "
    _FILE_WRITE = "FWR: "


class WR_CMD:
    @classmethod
    def all(cls):
        return [v for k, v in cls.__dict__.items() if not callable(v) and not k.startswith("__")]

    CONTROL_A = "\x01"
    CONTROL_B = "\x02"
    CONTROL_C = "\x03"
    CONTROL_D = "\x04"
    RESET = "\x04"
    BOOT_FILE = "/boot.py"

    PINS_RELOAD = "_npin_.reload() if '_npin_' in globals() else exec('import _npin_')"
    PINS_READ = "_npin_.read() if '_npin_' in globals() else 0"
    PINS_WRITE = "_npin_.write({}, {})  if '_npin_' in globals() else 0"
    PINS_FILE = "_npin_.py"
    PINS_IMPORT = "exec('import _npin_') if '_npin_.py' in __import__('os').listdir() else 0"
    PINS_SETUP = """
from machine import Pin

pins={{i: [Pin(i, eval(io), value=val), io, name] for i, io, name, val in {}}}

def reload():
    import sys
    if "_npin_" in sys.modules:
        del sys.modules["_npin_"]
    exec('import _npin_')
    read()

def read():
    for k, v in pins.items():
        print('PIN:', k,v[0].value(),v[1],v[2])

def write(pin_no, value):
    if pin_no in pins:
        pins[pin_no][0].value(value)
    read()
"""

    MEMORY = "__import__('micropython').mem_info()"
    """
    stack: 2128 out of 8192
    GC: total: 37952, used: 3152, free: 34800
     No. of 1-blocks: 41, 2-blocks: 10, max blk sz: 18, max free sz: 1870
    None
    
    
        info = self.send(code).replace(code, "").strip()
        for c in info.split("\n"):
            if "GC:" in c:
                nums = re.findall(r'\d+', c)
                if len(nums) > 2:
                    return {"total": int(nums[0]), "used": int(nums[1]), "free": int(nums[2])}

        return {"total": 1, "used": 1, "free": 1}
    """

    MEMORY_OPTIMIZE = "__import__('gc').collect()"

    SIGNAL = "_v=__import__('network');print('SIG:',_v.WLAN(_v.STA_IF).status('rssi'))"
    """SIG: -72
    
    
        if sgnl.replace("-", "").isdigit():
            no = int(sgnl)
            if no > -50:
                return no  # f"{no} / Good Signal"
            if no > -80:
                return no  # f"{no} / Medium Signal"
            else:
                return no  # f"{no} / Low Signal"
    """

    FIRMWARE_CHECK = "print('FWC:', __import__('esp').check_fw())"
    """
    print('FWC:', __import__('esp').check_fw())
    md5: 17262cf5ecc565744088e3238cc89447
    FWC: True
    """

    FLASH_SIZE = "print('FLS:', __import__('esp').flash_size())"
    """FLS: 1048576
    
    f"{int(rslt) / 1048576}Mb" if rslt.isdigit() else rslt
    """

    OS_INFO = "print('OSI:', __import__('uos').uname())"
    """OUN: (sysname='esp8266', nodename='esp8266', release='2.0.0(5a875ba)', version='v1.13 on 2020-09-02', machine='ES
    P module (1M) with ESP8266')
    
    Eşittirler yerine : koy. () yerine {} koy ve sözlük olarak oku
    """

    FREQUENCE = "print('FRQ:', __import__('machine').freq())"
    """FRQ: 80000000
    
    f"{int(freq) / 1000000}MHz" if freq.isdigit() else freq
    """

    PLATFORM = "print('PLT:', __import__('sys').platform)"
    """PLT: esp8266"""

    RUN = "import {}"

    # OLD, NEW NEW
    RENAME = "os.rename('{}', '{}');print('RDR: ')"
    # Remove File
    REMOVE_VALUE = "del {};print('RDR: ')"
    # Remove File
    REMOVE_FILE = "__import__('uos').remove('{}');print('RDR: ')"
    # Remove Dir
    REMOVE_DIR = "__import__('uos').rmdir('{}');print('RDR: ')"
    # Make Dir
    MAKE_DIR = "__import__('uos').mkdir('{}');print('RDR: ')"

    MODULES = "print('<MDL: ');help('modules');print('MDL>')"
    """Bu iki etiket arasındakileri al. Düzenle ve listele"""

    # Dir Value
    DIR_VALUE = "print('DIR:', (type({0}) in (int, str, dict, bool, float, list, tuple), dir({0}), str({0})))"
    # Dir Global
    DIR_DEFAULT = "print('DIR:', (False, dir(), ''))"
    """DIR: (True, ['__class__', 'append', 'clear', 'copy', 'count', 'extend', 'index', 'insert', 'pop', 'remove', 
    'reverse', 'sort'], '[Pin(0), Pin(2)]')"""

    # ListDir
    LISTDIR = "print('LDR:', list(__import__('uos').ilistdir('{}')))"
    """LDR: [('NewFolder', 16384, 0, 0), ('nnn.py', 32768, 0, 60)]"""

    # File Read
    FILE_READ = r"_f=open('{0}');print('<FRD:', '{0}');print(_f.read());_f.close();del _f;print('FRD>')"
    FILE_WRITE = r"_f=open('{}', 'wb');_f.write({});_f.close();del _f;print('RDR: ')"
    # Gönderirken, binary olmasına dikkat et;
    # wr.send(CMD.FWR.format("ay.py", data.encode("utf-8")))
    # print('DIR:', (type(pins) in (int, str, dict, bool, float, list, tuple), dir(pins), str(pins)))

    ST7789_FILE = """
from machine import Pin, SPI
import vga1_8x16 as font
import st7789

class st7789n(st7789.ST7789):
    _x_start = 53
    _y_start = 40
    _row_max = 16
    _col_max = 15
    _line_no = 0
    _spacing = 15
    _rot = 0
    
    def __class__(self, *args, **kwargs):
        super().__class__(*args, **kwargs)
        if "rotation" in kwargs:
            self.rotation(kwargs.get("rotation"))
        
    def rotation(self, no):
        super().rotation(no)
        self._rot = no
        w = self.width()
        h = self.height()
        if no % 2:
            self._x_start = 40
            self._y_start = 53
            self._row_max = w // 8 - 1
            self._col_max = h // 15
        else:
            self._x_start = 53
            self._y_start = 40
            self._row_max = w // 8
            self._col_max = h // 16
            
        self._line_no = 0
        self.fill(st7789.BLACK)
    
    def clear(self):
        self.rotation(self._rot)
    
    def new_line(self, text, text_color=st7789.WHITE, back_color=st7789.BLACK):
        _row_max = self._row_max
        while len(text):            
            if len(text) > _row_max:
                yaz = text[:_row_max]
                text = text[_row_max:]
            else:
                yaz = text
                text = ""
                
            self.text(font, " " * _row_max, 0, 0, text_color, back_color)
            self.text(font, yaz, 0, 0, text_color, back_color)
            
            self._line_no = 0 if self._line_no == self._col_max - 1 else self._line_no + 1
            
            self.offset(self._x_start, self._y_start + self._line_no * self._spacing)
            
    
    def display_from_path(self, path):
        # Dosya içeriği şu şekilde, yazılmış olmalı;
        # 123 456 789 123
        # 123,456,789,123
        no = 0
        with open(path) as f:
            line = f.readline()
            while line:
                for rgb in line.split(" ,"):
                    y = no % 240
                    x = no // 240
                    self.pixel(x, y, int(rgb))
                    no += 1
                line = f.readline()
    
    def display_from_data(self, data):
        for no, rgb in enumerate(data):
            y = no % 240
            x = no // 240
            self.pixel(x, y, rgb)


spi = SPI(2, baudrate=30000000, polarity=1, phase=1, sck=Pin(18), mosi=Pin(19))

screen = st7789n(spi, 135, 240, reset=Pin(23, Pin.OUT), cs=Pin(5, Pin.OUT), dc=Pin(16, Pin.OUT), backlight=Pin(4, Pin.OUT)) # , rotation=1)

screen.init()
"""


# wr.send("import machine;print(machine.idle())")     # -> 6406678

# wr.send("import micropython;print(micropython.mem_info())")


# wr.send("import micropython;print(micropython.qstr_info())")
"""
qstr pool: n_pool=1, n_qstr=7, n_str_data_bytes=67, n_total_bytes=163
None
"""

# wr.send("import micropython;print(micropython.stack_use())")
"""
2096
"""

# wr.send("")
"""

"""

# Python language version that this implementation conforms to, as a string.
# wr.send("import sys;print(sys.version)")
"""
3.4.0
"""

# print(wr.get_file_content("boot.py"))
"""
#import esp
#esp.osdebug(None)
import uos, machine
#uos.dupterm(None, 1) # disable REPL on UART(0)
import gc
import webrepl
webrepl.start()
gc.collect()

from bilen import *

Process finished with exit code 0
"""
import sys

# if __name__ == "__main__":
#     wr = Webrepl(host="192.168.1.34", password="123456")
#     wr.start()
#     # print(wr.get_file_content("boot.py"))
#     wr.listen()
#
#     giris = time.time()
#
#     while wr.isconnect > 0 and time.time() - giris < 3:
#         wr.send(WR_CMD.LISTDIR.format("/"))
#         print("Receives", wr.receives)
#         time.sleep(1)
#
#     wr.disconnect()
#     print("Bitti")
