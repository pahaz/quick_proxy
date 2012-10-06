# proxy python class ru docs

Пакет разделен на несколько частей.
**proxy/core** - ядро прокси сервера.
**proxy/ext** - пакет, где находятся расширения для прокси сервера.

## from proxy.core ##
Основным классам в пакете является **NoBlockProxy**.
Класс предоставляет из себя абстракцию, которая реализует базовый функционал прокси сервера (является расширяемым ядром).


## from proxy.ext ##
Пакет содержит различные реализации прокси серверов, построенных на базе класса NoBlockProxy.

### proxy.ext.InformerProxy ###
Прокси сервер, который показывает процесс передачи данных от клиента, через прокси сервер, на сервер назначения.
Данный процесс представлен в виде текстовых сообщений.

**Пример использования:**

    ...\GitHub\quick_proxy>python -m proxy.core -l warning 8000 hackerdom.ru:80 InformerProxy
    Namespace(core_log_level='warning', destination='hackerdom.ru:80', module='InformerProxy', proxy='8000')
    127.0.0.1:63644  <-*-35741512-> [8000 PROXY 63645] <-*-35741568-> 172.16.10.245:80
    127.0.0.1:63644  --*-35741512>> [8000 PROXY 63645] --*-35741568-- 172.16.10.245:80
    127.0.0.1:63644  --*-35741512-- [8000 PROXY 63645] --*-35741568>> 172.16.10.245:80
    127.0.0.1:63644  --*-35741512-- [8000 PROXY 63645] <<*-35741568-- 172.16.10.245:80
    127.0.0.1:63644  <<*-35741512-- [8000 PROXY 63645] --*-35741568-- 172.16.10.245:80
    127.0.0.1:63644  --*-35741512-- [8000 PROXY 63645] <<*-35741568-- 172.16.10.245:80
    127.0.0.1:63644  <<*-35741512-- [8000 PROXY 63645] --*-35741568-- 172.16.10.245:80
    127.0.0.1:63644  --*-35741512>> [8000 PROXY 63645] --*-35741568-- 172.16.10.245:80
    127.0.0.1:63644  ----35741512-- [8000 PROXY 63645] --*-35741568-- 172.16.10.245:80
    127.0.0.1:63644  ----35741512-- [8000 PROXY 63645] --*-35741568>> 172.16.10.245:80
    127.0.0.1:63644  ----35741512-- [8000 PROXY 63645] ----35741568-- 172.16.10.245:80

**Формат вывода следующий:**

    [адрес:порт клиента] [(1) направление потока данных, * - статус соединения, номер сокета] [Порты, используемые для подключения к прокси и для отправки данных на адрес назначения] [аналогично (1)] [адрес:порт сервера назначения]

### proxy.ext.DumperProxy ###
Сервер, который показывает процесс общения с прокси и сохраняет дампа трафика каждой сессии в отдельный файл.

**Пример использования:**

    ...\GitHub\quick_proxy>python -m proxy.core -l warning 8000 hackerdom.ru:80 DumperProxy
    Namespace(core_log_level='warning', destination='hackerdom.ru:80', module='DumperProxy', proxy='8000')
    127.0.0.1:64207  <-*-34824008-> [8000 PROXY 64208] <-*-34824064-> 172.16.10.245:80
    127.0.0.1:64207  --*-34824008>> [8000 PROXY 64208] --*-34824064-- 172.16.10.245:80 478b
    127.0.0.1:64207  --*-34824008-- [8000 PROXY 64208] --*-34824064>> 172.16.10.245:80 478b
    127.0.0.1:64207  --*-34824008-- [8000 PROXY 64208] <<*-34824064-- 172.16.10.245:80 456b
    127.0.0.1:64207  <<*-34824008-- [8000 PROXY 64208] --*-34824064-- 172.16.10.245:80 456b
    127.0.0.1:64207  --*-34824008-- [8000 PROXY 64208] <<*-34824064-- 172.16.10.245:80 26b
    127.0.0.1:64207  <<*-34824008-- [8000 PROXY 64208] --*-34824064-- 172.16.10.245:80 26b
    127.0.0.1:64207  ----34824008-- [8000 PROXY 64208] --*-34824064-- 172.16.10.245:80 lose 0b
    Traceback (most recent call last):
      File "C:\python27\lib\runpy.py", line 162, in _run_module_as_main
        "__main__", fname, loader, pkg_name)
      File "C:\python27\lib\runpy.py", line 72, in _run_code
        exec code in run_globals
      File "C:\Users\stribog\PycharmProjects\GitHub\quick_proxy\proxy\core.py", line 643, in <module>
        p.serve_forever()
      File "proxy\core.py", line 355, in serve_forever
        readable, writable, exceptional = select.select(inputs, outputs, inputs, poll_interval)
    KeyboardInterrupt

Формат вывода похож на InformerProxy.
В директории можно найти фалы (пр `"port_8000_000000001.dmp"`), которые содержат полным дампом трафика.

**пример `"port_8000_000000001.dmp"`:**


    127.0.0.1:64207  <-*-34824008-> [8000 PROXY 64208] <-*-34824064-> 172.16.10.245:80

    127.0.0.1:64207  --*-34824008>> [8000 PROXY 64208] --*-34824064-- 172.16.10.245:80 478b
    GET / HTTP/1.1
    Host: 127.0.0.1:8000
    Connection: keep-alive
    Cache-Control: max-age=0
    User-Agent: Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.168 Safari/535.19
    Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
    Accept-Encoding: gzip,deflate,sdch
    Accept-Language: ru-RU,ru;q=0.8,en-US;q=0.6,en;q=0.4
    Accept-Charset: windows-1251,utf-8;q=0.7,*;q=0.3
    Cookie: PHPSESSID=924af4f085f23c17954c4f630e0c847a


    127.0.0.1:64207  --*-34824008-- [8000 PROXY 64208] --*-34824064>> 172.16.10.245:80 478b

    127.0.0.1:64207  --*-34824008-- [8000 PROXY 64208] <<*-34824064-- 172.16.10.245:80 456b
    HTTP/1.1 302 Found
    Date: Sat, 06 Oct 2012 08:23:58 GMT
    Server: Apache/2.2.16 (Debian)
    X-Powered-By: PHP/5.2.6-1+lenny16
    Expires: Thu, 19 Nov 1981 08:52:00 GMT
    Cache-Control: no-store, no-cache, must-revalidate, post-check=0, pre-check=0
    Pragma: no-cache
    Location: http://www.hackerdom.ru/NullPage
    Content-Encoding: gzip
    Vary: Accept-Encoding
    Content-Length: 26
    Keep-Alive: timeout=5, max=1000
    Connection: Keep-Alive
    Content-Type: text/html


    127.0.0.1:64207  <<*-34824008-- [8000 PROXY 64208] --*-34824064-- 172.16.10.245:80 456b

    127.0.0.1:64207  --*-34824008-- [8000 PROXY 64208] <<*-34824064-- 172.16.10.245:80 26b
    *********** бинарные данные ***********

# Написание своего прокси сервера #
Нужно разобрать простой пример.









# Quick proxy eng #

Yet another TCP proxy. Very simple to use -- just edit config file and run.

Supports Linux, Freebsd (need test) and Windows; IPv4 and IPv6, Python 2.6 (need test), 2.7, 3.1 (need test), 3.2 (need test).
No external modules required. Not forks on each connection. Saves sessions in
files.

## Configuration example ##
    
    PROXYMAPS = {
        3128 : ("e1.ru", 80),
        1234 : ("127.0.0.1", 80),
        3456 : ("dc21:c7f:2012:6::10", 22),
        4433 : ("alexbers.dyndns.org", 22)
    }

UDP proxy find in https://github.com/henices/Tcp-DNS-proxy/blob/master/tcpdns.py
Twisted proxy find in http://code.activestate.com/recipes/502293-hex-dump-port-forwarding-network-proxy-server/

# Advenced use #
proxy.core.NoBlockProxy - stable core for different proxy servers from proxy.ext.*

    class NoBlockProxy(object):
        """
        Core for different proxy servers.
        This proxy is no blocking and use select.

        notes:
            * If the kernel detects an error in the filter or event
                it continues to work ignoring her.
            * The arguments for the filters and events can be modified,
                changes is not reflected on the proxy core.
            * Override filter__ methods we can change send-recv date or
                drop accepted connections.
            * Override on__ methods we can get different events.

        Overrides:
            filter__accept_connection(self, client_id, client_address, client_proxy_address):
                return True # if accept new connection and forward connection

            on__accept_proxy_connection(self, client_sock_info, forward_sock_info):
                pass # trigger event if new connection accepted and forwarded connection ok

            filter__recv_data(self, data, sock_info):
                return data # filter received data

            filter__send_data(self, data, sock_info):
                return data # filter sending data

            on__connection_close(self, sock_info):
                pass # trigger event if connection close

            on__start_event_loop(self):
                pass # trigger event pre select

            on__init(self):
                pass # trigger event if call init

        """

Example how to use core we can find in dumper_proxy.py and informer_proxy.py files.

## example use different proxy ##

    ..\GitHub\quick_proxy>python -m proxy.core -h
    usage: core.py [-h] [-l CORE_LOG_LEVEL] proxy destination [module]

    This TCP proxy server is no blocking and use select.

    positional arguments:
      proxy                 the proxy "ip:port"
      destination           the destination "host:port"
      module                the extension proxy class

    optional arguments:
      -h, --help            show this help message and exit
      -l CORE_LOG_LEVEL, --core-log-level CORE_LOG_LEVEL
                            level core logging; if default module then level debug
                            else level critical

    example: core.py -l critical 8000 "hackerdom.ru:80"; core.py
    "192.168.0.101:8000" "hackerdom.ru:80"; If you have any problem write them on
    http://github.com/pahaz/

    >python -m proxy.core -h
    >python -m proxy.core -l warning 8000 hackerdom.ru:80 DumperProxy

    # use DumperProxy proxy (with log level=crytical)
    >python -m proxy.core 8000 hackerdom.ru:80 DumperProxy

    # use InformerProxy proxy (with log level=crytical)
    >python -m proxy.core 8000 hackerdom.ru:80 InformerProxy

    # use default proxy (only core with log level=debug)
    >python -m proxy.core 8000 hackerdom.ru:80

    # this is equal to this
    >python -m proxy.core 8000 hackerdom.ru:80 NoBlockProxy

## Authors ##
Inspired the development of alexbers.
First version alexbers.
Full rewrite pahaz.