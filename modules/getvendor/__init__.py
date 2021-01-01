__copyright__ = 'Copyright 2020, ScanAg'
__author__ = 'Manahter'
__version__ = '1.0.0'

from requests import get
import csv
import os


def get_mac_vendor(mac, method=0, only_esp=False):
    """MAC adresinden üreticiyi bulur.

    :param mac: str: MAC adresi
    :param method: int:
        0 -> dahili veritabınını kullanır.
        1 -> 'maclookup.app' api'si
        2 -> 'macvendors.co' adresinin api'si kullanılır.
        Veritabanbı kaynağı: https://regauth.standards.ieee.org/standards-ra-web/pub/view.html#registries
    :param only_esp: bool: Yalnızca Espressif ürünlerini bul.
    :return: Company"""

    if method is 0:
        result = ""

        _mac = mac.replace(":", "").upper()

        for db in ["esp"] if only_esp else ("l", "m", "s"):
            if result:
                break

            with open(f'{os.path.dirname(__file__)}/ma{db}.csv', 'r') as f:
                reader = csv.reader(f)

                for row in reader:
                    if row[1] in _mac:
                        result = row[2]
                        break

    elif method is 1:
        veri = get(f"https://api.maclookup.app/v2/macs/{mac}").json()
        result = veri.get("company")

    else:
        veri = get(f"https://macvendors.co/api/{mac}/json/").json()
        result = veri["result"].get("company")
    return result

