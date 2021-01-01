from time import gmtime, strftime
import os
import tempfile

__author__    = 'Manahter'
__copyright__ = 'Copyright 2020, Rapor'
__version__   = '1.1.0'

# TODO:
#  * Raporları temp klasörüne kaydet.
#  * Her oluşturulduğu yer için ayrı rapor dosyası yazılır veya Her uygulama için aynı isimde dosya adı...
#  * Short modu da ekle. Örnek çıktı:
#       I | ModulAdı | fonk | mesaj
"""
Bundan faydalanarak, fonksiyon adını girmeden de, fonksiyonun adını al

from inspect import getframeinfo, currentframe, stack

def test_func_name():
    return naber("s")

def naber(a):
    print("Naberi çağıran fonksiyon ;", stack()[1].function)
    print("Bu fonksiyon ;", getframeinfo(currentframe()).function)

print(test_func_name())

"""
_modes_ = {
    "iNFO": 1,  # Grey
    "INFO": 2,
    "WARNING": 3,
    "NOTICE": 4,
    "ERROR": 5
}


class Color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

    ITALIC = '\33[3m'
    URL = '\33[4m'
    BLINK = '\33[5m'
    BLINK2 = '\33[6m'
    SELECTED = '\33[7m'

    BLACK = '\33[30m'
    RED = '\33[31m'
    GREEN = '\33[32m'
    YELLOW = '\33[33m'
    BLUE = '\33[34m'
    VIOLET = '\33[35m'
    BEIGE = '\33[36m'
    WHITE = '\33[37m'

    BLACKBG = '\33[40m'
    REDBG = '\33[41m'
    GREENBG = '\33[42m'
    YELLOWBG = '\33[43m'
    BLUEBG = '\33[44m'
    VIOLETBG = '\33[45m'
    BEIGEBG = '\33[46m'
    WHITEBG = '\33[47m'

    GREY = '\33[90m'
    RED2 = '\33[91m'
    GREEN2 = '\33[92m'
    YELLOW2 = '\33[93m'
    BLUE2 = '\33[94m'
    VIOLET2 = '\33[95m'
    BEIGE2 = '\33[96m'
    WHITE2 = '\33[97m'

    GREYBG = '\33[100m'
    REDBG2 = '\33[101m'
    GREENBG2 = '\33[102m'
    YELLOWBG2 = '\33[103m'
    BLUEBG2 = '\33[104m'
    VIOLETBG2 = '\33[105m'
    BEIGEBG2 = '\33[106m'
    WHITEBG2 = '\33[107m'


class Rapor:
    """
    :func common: type, module, messager, message, color
        :param module: str: "Self module Name" ... anything
        :param messager: str: "Func name" ... anything
        :param message: str: "I done" ... anything

        [ type ] [ module ] messager: message
    Example 1:
        # Create
        rapor = Rapor(module="Scaner")

        # or Call1
        rapor.info("scan_start", "Scanning started...")
        >> [ INFO ] [ Scaner ] scan_start: Scanning started...

        # Call 2
        rapor.info( messager="scan_start", message="Scanning started...")
        >> [ INFO ] [ Scaner ] scan_start: Scanning started...


    Example 2:
        # Direct Call-1 without create
        Rapor.info("scan_start", "Scanning started...")
        >> [ INFO ] scan_start: Scanning started...

        # Direct Call-2 without create
        Rapor.info(module="Scaner", messager="scan_start", message="Scanning started...")
        >> [ INFO ] [ Scaner ] scan_start: Scanning started...

    """
    """Want do you keep?"""
    _keep = False
    _mode = 0
    module = ""
    messager = ""

    def __init__(self, module="", module_path="", messager="", mode="A", tempdir="", keep=False):
        """
        :param mode: str: Usage: 'A', 'INEW', 'NE' ...
            'A' -> All,
            'I' -> INFO,
            'i' -> INFO_GREY,
            'W' -> WARNING,
            'N' -> NOTICE,
            'E' -> ERROR
        """
        self._path = os.path.join(tempdir or tempfile.gettempdir(), module or os.path.dirname(__file__))
        self._mode_path = os.path.join(self._path, "mode")
        self._keep_path = os.path.join(self._path, "keep")

        # Dizin yoksa oluştur
        if not os.path.exists(self._path):
            os.mkdir(self._path)

        # Eski dosya varsa silinir.
        elif "keep" in os.listdir(self._path):
            os.remove(self._keep_path)

        self.messager = messager
        self.module = module
        self.mode = mode
        self._keep = keep

        if module_path:
            self.notice("Loaded", module_path)

        self.notice("TempDir", self._path)

    @property
    def mode(self):
        """
        Keys:
            'A' -> ALL,
            'I' -> INFO,
            'i' -> iNFO_GREY,
            'W' -> WARNING,
            'N' -> NOTICE,
            'E' -> ERROR

            TODO:
                'C' -> Colored
                'S' -> Short
        Example:
            'Ai' -> print 'ALL', Except 'INFO_GREY'
            'WE' -> print 'WARNING' and 'ERROR'
            'NEI' -> print 'NOTICE' and 'ERROR' and 'INFO'
        """
        if not os.path.exists(self._mode_path):
            return "A"
        with open(self._mode_path) as f:
            return f.read().strip()

    @mode.setter
    def mode(self, val):
        """Set only self"""
        if type(val) != str:
            return

        with open(self._mode_path, "w") as f:
            f.write(val)

        self._mode = val

    @property
    def keep(self):
        return self._keep

    @keep.setter
    def keep(self, val):
        if type(val) == str and self._keep:
            with open(self._keep_path, "a") as f:
                f.write(val.replace("\n", "") + "\n")

    def info(*args, **kwargs):
        Rapor.common(*args, type="INFO", color=Color.GREEN, **kwargs)

    def info_grey(*args, **kwargs):
        Rapor.common(*args, type="iNFO", color=Color.GREY, **kwargs)

    def warning(*args, **kwargs):
        Rapor.common(*args, type="WARNING", color=Color.YELLOW, **kwargs)

    def error(*args, **kwargs):
        Rapor.common(*args, type="ERROR", color=Color.RED, **kwargs)

    def notice(*args, **kwargs):
        Rapor.common(*args, type="NOTICE", color=Color.BLUE, **kwargs)

    def common(*args, **kwargs):
        args = list(args)
        self = args.pop(0) if len(args) and type(args[0]) == Rapor else Rapor

        tipi = kwargs.get("type", "-")
        mode = self.mode
        if "A" in mode:
            if tipi[0] in mode:
                return
        elif tipi[0] not in mode:
            return

        module = kwargs.get("module", self.module)
        messager = kwargs.get("messager", self.messager or (args[0] if len(args) else ""))
        message = kwargs.get("message", (args[1] if len(args) > 1 else ""))

        pres = ["[{}{}{: ^7s}{}]".format(Color.BOLD, kwargs.get("color", Color.GREY), tipi, Color.END)]

        if module:
            pres.append("{:10}>".format(module))

        if messager:
            pres.append("{:12}".format(messager))

        if message:
            pres.append(": " + message)

        print(*pres)

        if self.keep:
            pres[0] = "|{: ^7s}|".format(tipi)
            pres.insert(0, strftime("%Y-%m-%d %H:%M:%S", gmtime()))
            self.keep = " ".join(pres)
