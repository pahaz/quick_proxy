import socket
from threading import Thread
from time import sleep
from proxy.core import NoBlockProxy

import config

if not getattr(config, "CLS"):
    setattr(config, "CLS", NoBlockProxy)

class Proxy(Thread):
    def __init__(self,
                 listen_port, server_host, server_port,
                 listen_ipv6=False):
        Thread.__init__(self, name='port' + str(listen_port))
        proxy_host = "0.0.0.0" if not listen_ipv6 else "::"
        self.proxy = config.CLS(proxy_host, listen_port, server_host, server_port, False)
        self.proxy.set_proxy_core_log_level('info')

    def run(self):
        self.proxy.init()
        self.proxy.serve_forever()

for listen_port, sockaddr in config.PROXYMAPS.items():
    server_host, server_port = sockaddr
    p = Proxy(listen_port, server_host, server_port)
    p.daemon = True
    p.start()

while True:
    sleep(1337)