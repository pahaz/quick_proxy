# Quick proxy #

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