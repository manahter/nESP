import subprocess
import tempfile
import inspect
import random
import shutil
import time
import json
import sys
import os

KWARGS = "k"
RESULT = "r"
VALUE = "v"
ARGS = "a"

# !!! Dekoratörde, fonksiyon okunduktan sonra dosyalarını silebilirsin aslında
# Ya da aradan belli bir süre geçtiyse, dosyayı sil gitsin, loop'tan silebilirisn
"""
Dosyalama Şekli;
    +/tmp
    |---> -/dirio
          |---> +/12345
          |---> -/67891
                |-----> __main__.py     -> Sadece ilk çalıştırılırken vardır.
                |-----> +/func1
                |-----> -/func2
                |       |-------> 11
                |       |-------> 12
                |       |-------> 13
                |                 |-> {"a": ["Func args"], "k": {"Func kwargs"}, "r": "Dönüş değeri"}
                |-----> variable1
                |-----> variable2
                |-----> variable3
                        |-------> "Değişkendeki değer"
"""

# Dosyayı okuyup yazarken sorun çıkıyor.
# import fcntl
#
#
# # ################################ File LOCK - Henüz kullanmadık
# # https://stackoverflow.com/questions/4843359/python-lock-a-file
# def lock_to_file(filename):
#     """ acquire exclusive lock file access """
#     locked_file_descriptor = open(filename, 'w+')
#     fcntl.lockf(locked_file_descriptor, fcntl.LOCK_EX)
#     return locked_file_descriptor
#
#
# def lock_to_release(locked_file_descriptor):
#     """ release exclusive lock file access """
#     locked_file_descriptor.close()
#
#
# # ##############################################################


def new_dir(tempdir, module, class_name, args, kwargs):
    """/Tempdir/353464325"""

    # Dizini oluşturuyoruz
    dir_path = os.path.join(tempdir or tempfile.gettempdir(), "dirio")
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
    no = 111
    while str(no) in os.listdir(dir_path):
        no = random.randint(111, 9999999999)

    new_path = os.path.join(dir_path, str(no))
    os.mkdir(new_path)

    # #######################
    # #######################
    # Scripti oluşturuyoruz

    # Önce bu dosya okunur.
    with open(__file__) as f:
        script_body = f.read()

    # İçe aktarılacak modülün yolu bulunur.
    module_name = os.path.basename(module).split(".")[0]
    module_path = os.path.dirname(module)

    if module_name in ("__init__", "__main__"):
        module_name = os.path.basename(module_path)
        module_path = os.path.dirname(module_path)

    # Scriptin parçaları oluşturulur
    # script_head = f"import sys\nsys.path.append('{module_path}')\nfrom {module_name} import {class_name}"
    script_head = f"""
import sys
sys.path.append('{module_path}')
from {module_name} import {class_name}
"""
    # script_footer = f"new = Dirio(target={class_name}, args={args}, kwargs={kwargs}, worker=True)\nnew._dr_loop()"
    script_footer = f"""
try:
    new = Dirio(target={class_name}, args={args}, kwargs={kwargs}, worker=True)
    new._dr_loop()
except:
    pass

# Çıkışta dosyaları sil

dirname = os.path.dirname(__file__)
if os.path.exists(dirname):
    shutil.rmtree(dirname)

sys.exit()
"""
    script = "\n".join([script_head, script_body, script_footer])

    # Script yazılır
    with open(os.path.join(new_path, "__main__.py"), "w") as f:
        f.write(script)

    # Burada da Process olarak başlatsan iyi olur

    subprocess.Popen([
        sys.executable,
        new_path
    ],
        # close_fds=True
    )

    print("Dirio -> New Path ->", new_path)
    return new_path


def check_type(value):
    tipi = str(type(value))
    if "DrDict" in tipi:
        value = dict(value)
        print("Var doğru")
    elif "DrList" in tipi:
        value = list(value)

    tip = type(value)
    check = True

    if tip in (dict, list, tuple, int, str, float, bool, type(None)):
        if tip is dict:
            for k, v in value.items():
                if not (check_type(k) and check_type(v)):
                    return False
        elif tip in (list, tuple):
            for i in value:
                if not check_type(i):
                    return False
    else:
        return False
    return check


def set_decorator(self):
    # Class'daki tüm değerleri alıyoruz
    for attr in self.__dict__:

        # Bu isimlerdeyse, dekoratör ekleme, boşver.
        # if attr in ("__getattribute__", "__setattr__", "__new__"):
        if (attr.startswith("__") and attr.endswith("__")) or attr in ("dr_terminate", "dr_code",
                                                                       "dr_bind", "dr_binds_check", "dr_isactive"):
            continue

        # Eğer çağrılabilir fonksiyon ise dekorator ekliyoruz
        attribute = getattr(self, attr)

        if callable(attribute):
            setattr(self, attr, get_decorator(self, attribute))


def get_result(path_code, dr_wait):
    start_time = time.time()
    wait_time = 1

    # Cevabı okurken bekle
    while wait_time:
        if os.path.exists(path_code):
            try:
                with open(path_code) as f:
                    data = json.load(f)
                    if RESULT in data:
                        return data.get(RESULT)
            except:
                pass

        # -1 ise cevap gelene kadar bekle
        # 0 ise sadece bir kere kontrol et
        # 5 gibi değer ise, 5 sn kadar bekle
        if dr_wait >= 0:
            wait_time = time.time() - start_time < dr_wait

    return None


def get_decorator(self, func):
    def wrapper(*args, **kwargs):
        # kwargs'ın içinde,
        # dr_code=True varsa; Okuma kodu döndürür.
        # dr_code=2345 gibi ;
        #       İstemci ise, bu kodun dönüşü varsa, onu döndürür. Yoksa None döndürsün.
        #       Sunucu ise, o değerdeki dosyaya RESULT değerini kayıt yap demek oluyor
        # Hiçbiri yoksa     ; En son herhangi bir cevabı döndürür
        dr_code = kwargs.pop("dr_code", False)
        dr_wait = kwargs.pop("dr_wait", 0)

        # Fonksiyonun klasörü
        path = os.path.join(self._dr_dir, func.__name__)

        # Yoksa oluştur
        if not os.path.exists(path):
            os.mkdir(path)

        # Temel metodlar derhal işletilir.  !!! Burayı kullanmak istiyorsan, set_decorator kısmını da düzenle
        # if func.__name__.startswith("__") and func.__name__.endswith("__"):
        #     return func(*args, **kwargs)

        # İstemci ise   veya   self.metod değilse, (@class veya @static ise) baştaki self parametresini sil
        if not self._dr_active or "self" not in inspect.getfullargspec(func).args:
            args = args[1:]

        # ################################
        # İstemci ise ve Parametreler uygunsa, dosyaya kaydeder.
        if not self._dr_active and check_type(args) and check_type(kwargs):

            # dr_code -> int -> Bu kodla olan veri varsa döndür. Belirtilen süre kadar cevabı bekle
            if type(dr_code) is int and dr_code > 1:
                return get_result(os.path.join(path, str(dr_code)), dr_wait)

            # Func dizinindeki dosyaların isimlerini int olarak alır ve
            # ["1", "2", ... ] String listesinde en büyük sayıyı verir. Yoksa 10 değerini verir
            son_code = self._dr_last_code
            new_code = son_code + 1

            full_path = os.path.join(path, str(new_code))
            while os.path.exists(full_path):
                new_code += 1
                full_path = os.path.join(path, str(new_code))

            # Datayı dosyaya yaz
            with open(full_path, 'w') as f:
                json.dump({ARGS: args, KWARGS: kwargs}, f)

            self._dr_last_code = new_code

            # Cevabı bu süre kadar bekle ve dön
            if dr_wait:
                return get_result(full_path, dr_wait)

            # dr_code -> True -> Kodu döndür
            if dr_code is True:
                return new_code

            # dr_code -> False -> Default, Son dosyada cevap varsa döndür
            if son_code != 10:
                try:
                    with open(os.path.join(path, str(son_code))) as f:
                        return json.load(f).get(RESULT)
                except:
                    pass
            # Hiçbiri uymuyorsa, boş dön
            return None

        # ################################
        # Kod varsa datayı koddaki dosyaya yaz. Tabi tipler uygunsa yaz.
        if type(dr_code) is str:
            file = os.path.join(path, dr_code)
            try:
                with open(file) as f:
                    data = json.load(f)
            except:
                return

            # Clas fonksiyonu veya self fonksiyon olmasına göre fazla parametre hatası verebildiğinden böyle yapıldı
            if "self" not in inspect.getfullargspec(func).args:
                result = func(*data.get(ARGS, ()), **data.get(KWARGS, {}))
            else:
                result = func(args[0], *data.get(ARGS, ()), **data.get(KWARGS, {}))

            data[RESULT] = result if check_type(result) else None

            with open(file, "w") as f:
                json.dump(data, f)

            # Zaman kaydedicide, fonksiyonun ismi yoksa, oluştur
            if func.__name__ not in self._dr_last_times:
                self._dr_last_times[func.__name__] = {}

            # Func dosyasını değiştirdiğimiz için, değişim zamanını kaydediyoruz ki, sonradan başkası değişti sanılmasın
            self._dr_last_times[func.__name__][dr_code] = os.stat(file).st_mtime
        else:
            # Sunucuysa, direkt fonksiyonu işle
            result = func(*args, **kwargs)

        return result

    return wrapper


class Dirio:
    _dr_inwork = False
    _dr_binds = {}

    def __init__(self, target=None, args=(), kwargs={}, tempdir="", keeperiod=10, looperiod=.05, worker=False):
        """
        :param target: class: Hedef Class
        :param args: tuple: Class'ın argümanları
        :param kwargs: dict: Class'ın keyword'lü argümanları
        :param tempdir: str: Temporary klasörü. Girilmediyse, standart sistemdeki klasör kullanılır.
        :param keeperiod: int: Geçmişi tutma süresi. Default: 10 sn boyunca geçmişi saklar.
        :param looperiod: int: Sunucu için, döngüde bekleme süresi. Küçük olursa işlemciden, büyük olursa işlemden zarar
        :param worker: bool: Read Only. Değiştirme. Sınıfın kendine has kullanımına dahildir.
        """
        self._dr_bind = {}
        self._dr_active = worker
        self._dr_last_code = 10
        self._dr_last_times = {}
        self._dr_keep_period = keeperiod
        self._dr_loop_period = looperiod
        # Önce kopyalıyoruz, Çünkü üstünde değişiklik yaptığımızda kalıcı olmasın
        target = type(target.__name__, target.__bases__, dict(target.__dict__))
        set_decorator(target)

        if worker:
            # Sunucu kısmıdır. Bu kısım sadece temp klasöründen başlatıldığında çalışır
            self._dr_dir = os.path.dirname(__file__)
        else:
            # İstemci kısmıdır.Sunucu oluşturulur ve başlatılır
            self._dr_dir = new_dir(tempdir, inspect.getfile(target), target.__name__, args, kwargs)

        # target = type(f'gecis.{target.__name__}', tuple(target.__bases__), dict(target.__dict__))

        # Dirio özelliklerini diğer sınıfa ekliyoruz
        for attr in self.__dict__:
            if attr.startswith("_dr_") or attr.startswith("dr_"):  # or attr in ("__getattribute__", "__setattr__"):
                setattr(target, attr, self.__getattribute__(attr))

        # Kendimizi, Clasın kopyasına çeviriyoruz
        self.__class__ = type(f'dirio.{target.__name__}', tuple([Dirio, target]), dict(self.__dict__))

        self._dr_inwork = True

        super().__init__(*args, **kwargs)

    def __getattribute__(self, name):
        # _dr_ ile başlıyorsa veya  __xxx__ gibi bir değişkense hemen döndürülür
        if name.startswith("_dr_") or (name.startswith("__") and name.endswith("__")):
            return super().__getattribute__(name)

        in_class = name in dir(self)

        # print("__getattribute__\t<--\t\t\t", name)

        # Fonksiyon ise, direkt döndürülür.
        ###############
        if in_class:
            value = super().__getattribute__(name)
            if callable(value):
                return value

        _dr_dir = self._dr_dir

        # Değişken ise;
        ###############
        # Değer dosyada varsa, oradan okunur
        # if name in os.listdir(_dr_dir):
        if os.path.exists(os.path.join(_dr_dir, name)):
            try:
                with open(os.path.join(_dr_dir, name)) as f:
                    value = json.load(f).get(VALUE)
                    if type(value) in (dict, list):
                        return DrVar(self, name, value)
                    else:
                        return value
            except:
                pass

        if in_class:
            value = super().__getattribute__(name)

            # Demekki dosyada yok ki buraya kadar geldik, dosyaya da kaydedelim.
            self.__setattr__(name, value)

            if type(value) in (dict, list):
                return DrVar(self, name, value)
            else:
                return value

        return lambda *args, **kwargs: None

    def __setattr__(self, key, value):
        # print("__setattribute__\t\t\t-->\t", key, value)

        # Eğer value, çağrılabilir ise, ona özelliklerimizi ver.

        # Value uygunsa, key isimli dosyaya yaz
        # İstemci ve sunucu için de geçerli
        # if self._dr_inwork:
        # if self._dr_inwork and os.path.exists(self._dr_dir):
        if self._dr_inwork:
            if not os.path.exists(self._dr_dir):
                self.dr_terminate()
                sys.exit(0)

            file = os.path.join(self._dr_dir, key)

            if check_type(value):
                with open(file, "w") as f:
                    json.dump({VALUE: value}, f)
            else:
                # Eğer kaydedilemeyen bir tip ise, dosyada var olanı da sil ki, çağırırken sorun yaşanmasın
                if os.path.exists(file):
                    os.remove(file)

            # !!! Aslında değişkenler için bu işleme gerek yok. Sadece fonksiyonlar için yapsak yeterli olur
            # Eğer Sunucu ise, dosyanın son değişme zamanını güncelle ki, onu değişti zannetmesin.
            # if self._dr_active:
            #     self._dr_last_times[key] = os.stat(file).st_mtime

        super().__setattr__(key, value)

    def _dr_loop(self):
        # Script dosyasını siliyoruz
        if os.path.exists(__file__):
            os.remove(__file__)

        # Kaydedilmiş değerler varsa önce onları okur
        # Daha sonra tüm değerleri dosyaya kaydet
        for i in dir(self):
            if not (i.startswith("__") and i.endswith("__")):
                getattr(self, i)

        # Böyle yapıyoruz ki, çağırırken her seferinde class.getattr'e yük olmasın
        _dr_dir = self._dr_dir
        _dr_last_times = self._dr_last_times

        while self.dr_isactive():
            # Dizindeki, fonksiyon klasörlerinin isimleri alınır.
            func_dirs = [i for i in os.listdir(_dr_dir) if os.path.isdir(os.path.join(_dr_dir, i))]

            # Tüm fonk dizinlerini gez
            for func_dir in func_dirs:
                func_full_path = os.path.join(_dr_dir, func_dir)

                # last'ta fonk yoksa al
                if func_dir not in _dr_last_times:
                    _dr_last_times[func_dir] = {}

                lasts = _dr_last_times[func_dir]

                for func_code in os.listdir(func_full_path):
                    if not func_code.isdigit():
                        continue

                    func_code_full_path = os.path.join(func_full_path, func_code)

                    st = os.stat(func_code_full_path).st_mtime

                    # Daha önce çalıştırdıysak ve son çalışma zamanı aynıysa geç
                    if func_code in lasts and st == lasts.get(func_code):
                        # Saklama zamanı geçtiyse, geçmiş klasörüne aktar ve last_timesden'de kaldır
                        # if time.time() - st > self._dr_keep_period:
                        #    pass
                        #    # lasts'dan kaldır.
                        continue

                    # İlk defa çağrılıyorsa veya son çalışma zamanı farklıysa yap
                    # Fonksiyon işlenir ve dönüşü kaydedilir. Üstelik zamanı da..
                    # print("Fonksiyonu çağıtıruz", func_dir, func_code)
                    getattr(self, func_dir)(dr_code=func_code)

            # self.deger += 5
            # print(self.deger, self)
            # print("Bu da dönüyor", getattr(self, "deger"))
            time.sleep(self._dr_loop_period)

    def dr_terminate(self):
        """İşlemi bitirir"""
        if os.path.exists(self._dr_dir):
            shutil.rmtree(self._dr_dir)

    def dr_code(self, code, wait=0):
        """Dönüşü koddan direkt olarak okumayı sağlar."""
        if type(code) is int:
            code = str(code)

        if not self.dr_isactive():
            return self.dr_terminate()

        # Tüm fonksiyon klasörlerini gezer, eğer içinde elimizdeki koddan dosya varsa onu okur
        for func_name in [j for j in os.listdir(self._dr_dir) if os.path.isdir(os.path.join(self._dr_dir, j))]:
            func_path = os.path.join(self._dr_dir, func_name)

            if not self.dr_isactive():
                return self.dr_terminate()

            if code in os.listdir(func_path):
                return get_result(os.path.join(func_path, code), wait)

        return None

    def dr_bind(self, code, func, args=(), kwargs={}):
        """Girilen kod ile sonuç alındığında, 'func'u çağırır. Parametrelerini de girer.
        Sonuçları arayabilmesi için, arada 'dr_binds_check'in çalıştırılması gerekir.
        Fonksiyonun alacağı ilk parametre, code'un dönüş değeri olmalı"""
        self._dr_binds[code] = [func, args, kwargs]

    def dr_bind_count(self):
        return len(self._dr_binds)

    def dr_binds_check(self):
        """Sonuçları kontrol eder. Sonuçlar geldiyse, Bind'leri çalıştırır"""
        event = False
        for code, vals in self._dr_binds.copy().items():
            result = self.dr_code(code)
            if result is not None:
                func = vals[0]
                args = vals[1]
                kwargs = vals[2]
                func(*args, **kwargs, result=result)
                self._dr_binds.pop(code)
                event = True

        return event

    def dr_isactive(self):
        return self._dr_inwork and os.path.exists(self._dr_dir)










# -*- coding: utf-8 -*-
# String for doctests and  example:
# https://stackoverflow.com/a/9874974
"""
    >>> a = DrVar(self, "self_key", ["a", "b", "c"])
    a  -> ["a", "b", "c"]

    içinde herhangi bir değer değiştiğinde, self' class'daki 'self_key' isimli değişkene yazar.
"""
changer_methods = set("__setitem__ __setslice__ __delitem__ "
                      "update append extend add insert pop popitem "
                      "remove clear setdefault __iadd__".split())


def callback_getter(obj, cls):
    def callback(*args, **kw):
        obj.__setattr__(cls["drkey"], args[1])
    return callback


def proxy_decorator(func, callback):
    def wrapper(*args, **kw):
        rslt = func(*args, **kw)
        callback(func, *args, **kw)
        return rslt
    wrapper.__name__ = func.__name__
    return wrapper


def DrVar(self, key, value):
    """
    dict veya list için kullanılmalı
    :param self: self in class
    :param key: variable name
    :param value: dict or list value

    return types:   <class '__main__.DrDict'>  or <class '__main__.DrList'>
    """
    cls = (dict, list)[type(value) is list]
    new_dct = cls.__dict__.copy()
    new_dct["drkey"] = key
    for key, val in new_dct.items():
        if key in changer_methods:
            new_dct[key] = proxy_decorator(val, callback_getter(self, new_dct))
    return type("Dr" + cls.__name__.capitalize(), (cls,), new_dct)(value)
