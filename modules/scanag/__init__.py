import subprocess
import json
import sys
import os

# Sabitler
MAC = "MAC"
VENDOR = "VENDOR"
RESULTS = "RESULTS"
INPROCESS = "INPROCESS"

dirname = os.path.dirname(__file__)
PATH_RESULTS = os.path.join(dirname, RESULTS)
PATH_INPROCESS = os.path.join(dirname, INPROCESS)

if INPROCESS in os.listdir(dirname):
    os.remove(PATH_INPROCESS)


class ScanAg:
    def __init__(self):
        self.inprocess = False

    def start(self):
        self.scan()

    def scan(self):
        """Ağdaki diğer cihazları tarar"""
        if self.inprocess:
            return

        self.inprocess = True

    @property
    def inprocess(self):
        return INPROCESS in os.listdir(dirname)

    @inprocess.setter
    def inprocess(self, value):
        if value:
            subprocess.Popen([

                # Python konumu
                sys.executable,

                # Script konumu
                dirname,

                # Parametre
                "-p"
            ])

        elif self.inprocess:
            os.remove(PATH_INPROCESS)

    @property
    def result(self):
        if RESULTS not in os.listdir(dirname):
            return {}
        with open(PATH_RESULTS, "r") as f:
            result = json.load(f)
            return result

    @result.setter
    def result(self, data):
        if data:

            with open(PATH_RESULTS, "w") as f:
                json.dump(data, f)

        elif self.result:
            os.remove(PATH_RESULTS)

        self.inprocess = False

    @staticmethod
    def devices(only_esp=False):
        """Ağda bulunan cihazları döndürür

        :param only_esp: bool: Sadece ESPressif Cihazlarını Döndür
        :return: list: [ ("IP", "MAC", "VENDOR"), (...) ... ]
        """
        data = scanag.result
        if only_esp:
            for i in data.copy():
                if not data[i].get(VENDOR, "").lower().startswith("espressif"):
                    data.pop(i)

        return [(ip, data[ip].get(MAC), data[ip].get(VENDOR)) for ip in data]


scanag = ScanAg()
