"""Aynı ağda bulunan diğer cihazları tarar"""

_name_        = "ScanAg"
__author__    = 'Manahter'
__copyright__ = 'Copyright 2020, ScanAg'
__version__   = '1.2.0'
__date__      = "15.12.2020"

# TODO:
#   * Dirio ile yapmayı dene

from multiprocessing import Queue
from threading import Thread
from requests import get
from sys import platform
import subprocess
import socket
import time
import sys
import os
import re

dirname = os.path.dirname(__file__)

try:
    from ..getvendor import get_mac_vendor
    from ..getmac import get_mac_address
    from ..scanag import scanag
    from ..rapor import Rapor
except:
    # Bu dosyanın bulunduğu üst dizini, python sistemine ekliyoruz ki, modül araken burayada baksın
    updirname = os.path.dirname(dirname)
    sys.path.append(updirname)

    from getvendor import get_mac_vendor
    from getmac import get_mac_address
    from scanag import scanag
    from rapor import Rapor

rapor = Rapor(module=_name_,
              module_path=dirname,
              mode="A",
              keep=True)


# Sabitler
MAC = "MAC"
VENDOR = "VENDOR"
RESULTS = "RESULTS"
INPROCESS = "INPROCESS"

PATH_RESULTS = os.path.join(dirname, RESULTS)
PATH_INPROCESS = os.path.join(dirname, INPROCESS)


def inprocess(value):
    if value:
        with open(PATH_INPROCESS, "w") as f:
            f.write("")
    else:
        os.remove(PATH_INPROCESS)


def is_connection(fast=False):
    """Internete bağlı mıyız?

    :param fast: Hızlı sorgula.

    :return: bool
    """
    if fast:
        # Eğer bağlantı;
        #   varsa -> 127.0.1.1
        #   yoksa -> 127.0.0.1

        return socket.gethostbyname(socket.gethostname()) != "127.0.0.1"
    try:
        if get('https://google.com').ok:
            return True
    except:
        return False


def find_my_ip():
    """Bizim IP adresimizi döndürür

    :return: None or "xxx.xxx.x.x"
    """
    if not socket.gethostbyname(socket.gethostname()) != "127.0.0.1":
        # Eğer bağlantı;
        #   varsa -> 127.0.1.1
        #   yoksa -> 127.0.0.1

        rapor.warning(find_my_ip.__name__, "Stopped: There is no connection")
        return

    s_time = time.time()
    rapor.info_grey(find_my_ip.__name__, "Started")

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()

    rapor.info(find_my_ip.__name__, f"{ip}")
    rapor.info_grey(find_my_ip.__name__, f"Finished at {time.time() - s_time}ms")
    return ip


def scan_with_arp():
    """Komut satırından veriyi çeker. Hızlı yöntemdir. Sadece Linux'da çalışır.

    :return: dict   --> { "MAC":"IP", "MAC":"IP",. .. }
    """
    if platform not in ["linux", "linux2"]:
        rapor.warning(scan_with_arp.__name__, "Stopped: This method tested only on Linux")
        return {}

    s_time = time.time()
    rapor.info_grey(scan_with_arp.__name__, "scan_with_arp, Started")

    # Komut satırına "arp" komutu iletilir ve gelen veri satırlara ayırır
    cikti = os.popen("arp -a").read().split('\n')

    # Bulunanlar
    data = {}

    # Tüm satırlarda ip aranır
    for i in cikti:

        # Eğer MAC adresi varsa, bilgiler alınır
        if i.find(":") > 0:
            mac_match = re.search('([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', i, re.M | re.I)
            ip_match = re.search('[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+', i, re.M | re.I)

            ip = i[ip_match.start():ip_match.end()]
            mac = i[mac_match.start():mac_match.end()]

            data[ip] = {MAC: mac, VENDOR: ""}

    scanag.result = data

    rapor.info(scan_with_arp.__name__, f"Finished at {time.time() - s_time}ms")
    return data


def scan_with_multiping(pool_size=255):
    """Multiprocess yöntemiyle Ping atarak , ağı haritala

    :param pool_size: Paralel Ping işlem Miktarı
    :return: list of valid ip addresses
    """
    inprocess(True)
    s_time = time.time()
    data = {}
    ip_list = list()

    # Kendi IP'mizi bulup, baş kısmını tutuyoruz. 192.168.1.xxx
    ip = find_my_ip()

    if not ip:
        rapor.warning(scan_with_multiping.__name__, "Stopped: Self IP not found")
        scanag.result = data
        return data

    rapor.info_grey(scan_with_multiping.__name__, "Started")

    ip_parts = ip.split('.')
    base_ip = ip_parts[0] + '.' + ip_parts[1] + '.' + ip_parts[2] + '.'
    ip_sonu = int(ip_parts[-1])
    rapor.info_grey(scan_with_multiping.__name__, f"Base IP: {base_ip}")

    # İşlemler arası veri taşıyacak değişkenler
    works = Queue()
    results = Queue()

    # İşlemler oluşturulur.
    pool = [Thread(target=_pinger, args=(works, results)) for i in range(pool_size)]

    rapor.info_grey(scan_with_multiping.__name__, f"Pools start")
    # İşlemler başlatılır
    for p in pool:
        p.start()

    rapor.info_grey(scan_with_multiping.__name__, f"Works; put IP")
    # cue hte ping processes
    for i in range(1, 255):
        # Kendi IP adresimizi çıkartıyoruz, böylece işlem daha kısa sürüyor.
        if i != ip_sonu:
            works.put(base_ip + f'{i}')

    rapor.info_grey(scan_with_multiping.__name__, f"Work; put None")
    # While True döngüsü sonlansın, Prosesler sonlansın diye, None değeri veriyoruz.
    for p in pool:
        works.put(None)

    rapor.info_grey(scan_with_multiping.__name__, f"Pools join")
    # Proseslerin bitmesini bekliyoruz.
    for p in pool:
        p.join()

    rapor.info_grey(scan_with_multiping.__name__, f"get Results")
    # Sonuçları alıyoruz.
    while not results.empty():
        ip = results.get()
        ip_list.append(ip)

    rapor.info_grey(scan_with_multiping.__name__, f"find MACs and Vendors")
    for ip in ip_list:
        mac = get_mac_address(ip=ip) or ""
        vendor = get_mac_vendor(mac) or ""
        data[ip] = {MAC: mac, VENDOR: vendor}
        rapor.info(scan_with_multiping.__name__, f"Found; {ip}, {mac}, {vendor}")

    scanag.result = data

    rapor.info(scan_with_multiping.__name__, f"Finished at {time.time() - s_time}ms")

    works.close()
    results.close()

    return data


def _pinger(works_queue, results_queue):
    """Ping yollar

    :param works_queue:
    :param results_queue:
    :return:
    """
    # Çıktılar boşluğa yazılsın
    DEVNULL = open(os.devnull, 'w')

    # Fonksiyon bitirilene kadar, Ping yollar
    while True:
        # Ana Process ile bu Process arasındaki veridir.
        # Ana Process'den veri gelmesi beklenir..
        ip = works_queue.get()

        # Veri None ise fonksiyon biter.
        if ip is None:
            break

        try:
            # Terminale işlem gönderilir.
            subprocess.check_call(['ping', '-c1', ip], stdout=DEVNULL)
            # Hata çıkmadıysa sıra buraya geçer.
            # Sonuç değişkenine IP kaydedilir...
            results_queue.put(ip)
        except:
            pass

    DEVNULL.close()


scan_with_multiping()
