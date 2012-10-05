# use only valid hostnames
from proxy.ext import DumperProxy

PROXYMAPS = {
    8000 : ("ya.ru", 80),
    1234 : ("127.0.0.1", 80),
    3456 : ("dc21:c7f:2012:6::10", 22),
    4433 : ("alexbers.dyndns.org", 22)
}

CLS = DumperProxy