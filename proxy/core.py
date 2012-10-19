import os
import sys

__author__ = 'pahaz'

import threading
import logging
import select
import socket
import errno
from collections import deque

import traceback

from proxy.utils import get_sock_settings
from proxy.utils import hexdump

LEVELS = { 'debug':logging.DEBUG,
           'info':logging.INFO,
           'warning':logging.WARNING,
           'error':logging.ERROR,
           'critical':logging.CRITICAL,
           }

class PublicSockInfo(object):
    def __init__(self, _public_sock_, _public_sock_pair_, is_client):
        id, address, proxy_address = _public_sock_
        pair_id, pair_address, pair_proxy_address = _public_sock_pair_

        self.id = id
        self.address = address
        self.proxy_address = proxy_address
        self.is_client = is_client
        self.pair_id = pair_id
        self.pair_address = pair_address
        self.pair_proxy_address = pair_proxy_address

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
    SOCKET_QUEUE_MAX_SIZE = 30
    PULL_INTERVAL = 10

    proxy_allow_reuse_address = True
    proxy_socket_type = socket.SOCK_STREAM
    proxy_request_queue_size = 5
    max_packet_size = 8192

    def add_proxy_core_log_handler(self, handler):
        self.__log.addHandler(handler)

    def set_proxy_core_log_level(self, lvl):
        if type(lvl) == str:
            lvl = LEVELS.get(lvl)
            if not lvl:
                return
        self.__log.setLevel(lvl)

    def get_forwarding_address(self):
        if not self.forwarding_address_resolved:
            try:
                self.__forward_family, self.__forward_socket_type, self.__forward_address = get_sock_settings(
                    *self.__forward_address_init)
            except Exception, e:
                self.__log.critical('error resolving forward adders: %r' % (e.message,))
                raise e
            else:
                self.__log.debug(
                    'resolved forward adders; forward_family = %r; forward_socket_type = %r; forward_address = %r;' % (
                        self.__forward_family, self.__forward_socket_type, self.__forward_address))
                self.forwarding_address_resolved = True

        return self.__forward_family, self.__forward_socket_type, self.__forward_address

    def __init__(self, proxy_host, proxy_port, forward_host, forward_port, init_socket=True,
                 pre_resolving_forward_host=True):
        self.__proxy_address_init = (proxy_host, proxy_port)
        self.__forward_address_init = (forward_host, forward_port)
        self.__log = logging.getLogger('proxy[%s]' % (proxy_port, ))
        self.__is_shut_down = threading.Event()
        self.__shutdown_request = False

        # for public use and override use
        self.proxy_port = proxy_port
        self.forward_host = forward_host
        self.forward_port = forward_port


        self.proxy_init = False
        self.forwarding_address_resolved = False

        if init_socket: self.init(pre_resolving_forward_host)

    def init(self, pre_resolving_forward_host=True):
        """Called by constructor to bind the socket and activate the server.

        May be overridden.

        """
        if self.proxy_init:
            self.__log.warning('proxy already init and setup')
            return

        proxy_host, proxy_port = self.__proxy_address_init
        forward_host, forward_port = self.__forward_address_init

        self.__log.info(
            'init proxy server (*) <-> proxy(%r:%r) <-> (%r:%r)' % (proxy_host, proxy_port, forward_host, forward_port))

        # set proxy family
        proxy_family = socket.AF_INET6 if ":" in proxy_host else socket.AF_INET
        if not socket.has_ipv6 and proxy_family == socket.AF_INET6:
            self.__log.critical('IPv6 is not supported on this platform but you proxy bind address is IPv6')
            raise ValueError('IPv6 is not supported on this platform but you bind address is IPv6')

        # check support IPv6 in forward
        proxy_family = socket.AF_INET6 if ":" in forward_host else socket.AF_INET
        if not socket.has_ipv6 and proxy_family == socket.AF_INET6:
            self.__log.critical('IPv6 is not supported on this platform but you forward bind address is IPv6')
            raise ValueError('IPv6 is not supported on this platform but you forward bind address is IPv6')

        try:
            self.proxy = socket.socket(proxy_family, self.proxy_socket_type)
        except socket.error, e:
            self.__log.critical('creating proxy socket error: %s' % (e,))
            raise OSError('socket error: %s; errno = %s' % (e.errno, e.message))

        if pre_resolving_forward_host: self.get_forwarding_address() # try pre resolving

        self.__log.info('starting setup proxy %s bind%r' % (
            'REUSEADDR NOBLOCK' if self.proxy_allow_reuse_address else 'NOBLOCK', self.__proxy_address_init))

        try:
            if self.proxy_allow_reuse_address: self.proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.proxy.setblocking(0)
            self.proxy.bind(self.__proxy_address_init)
            self.proxy.listen(self.proxy_request_queue_size)
        except socket.error, e:
            self.proxy.close()
            self.__log.critical('error on initial proxy: %s' % (e,))
            raise e # ('error on initial proxy')

        self.proxy_init = True

        # trigger event
        try:
            self.on__init()
        except Exception, e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.__log.critical('on__init() error: %s; Traceback: %r' % (e, traceback.extract_tb(exc_traceback, 10)))


    def serve_forever(self, poll_interval=-1):
        """Handle all requests at a time until shutdown or all sockets closed.

        Polls for shutdown every poll_interval seconds. Ignores
        self.timeout. If you need to do periodic tasks, do them in
        another thread.
        """
        if poll_interval == -1:
            poll_interval = self.PULL_INTERVAL

        if not self.proxy_init:
            raise ValueError("proxy not init!")

        CLOSE_MESSAGE = ""

        # small utils
        def clear_bead_socket(inputs, outputs, log):
            log.info("cleaning bead sockets")
            for s in inputs:
                try:
                    select.select([s], [], [], 0)
                except:
                    log.warning('find bead: %s' % (id(s),))
                    inputs.remove(s)

            for s in outputs:
                try:
                    select.select([], [s], [], 0)
                except:
                    log.warning('find bead: %s' % (id(s),))
                    outputs.remove(s)

        def psock(lst):
            return str([id(x) for x in lst])

        self.__is_shut_down.clear()

        # Sockets from which we expect to read
        inputs = [self.proxy]

        # Sockets to which we expect to write
        outputs = []

        # socket info (socket -> SockInfo()
        sock_info = {}

        class SockInfo(PublicSockInfo):
            def __init__(self, _sock_, _sock_pair_, is_client):
                pair, pair_id, pair_address, pair_proxy_address = _sock_pair_
                sock, sock_id, sock_address, sock_proxy_address = _sock_
                self.pair = pair
                self.sock = sock
                self.message_queues = deque()
                self.tail_sending = None # to send the remainder if no send in one package
                self.shutdown_message_in_queue = False # need for close pair, if self sock close

                _public_sock_ = _sock_[1:]
                _public_sock_pair_ = _sock_pair_[1:]

                self.__public_info = PublicSockInfo(_public_sock_, _public_sock_pair_, is_client)

                super(SockInfo, self).__init__(_public_sock_, _public_sock_pair_, is_client)

            def public(self):
                """
                Return public object for represent socket in event functions.
                Need for stability core work.
                """
                return self.__public_info

        def get_socket_info(s):
            return sock_info[s]

        def set_socket_info(s, id, address, proxy_address, pair, pair_id, pair_address, pair_proxy_address, is_client):
            sock_in = (s, id, address, proxy_address)
            sock_pair = (pair, pair_id, pair_address, pair_proxy_address)
            new_sock_info = SockInfo(sock_in, sock_pair, is_client)
            sock_info[s] = new_sock_info
            return new_sock_info

        def is_live_socket(s):
            return s in sock_info

        def append_in_socket_message_queues(s, data):
                socket_live = is_live_socket(s)
                if socket_live:
                    info = get_socket_info(s)

                    if data:
                        info.message_queues.append(data)

                    else:
                        append_close_in_socket_message_queues(s, info)

                else:
                    self.__log.warning('recv pair is closed')

                # Add output channel for response
                if s not in outputs and socket_live:
                    outputs.append(s)

        def append_close_in_socket_message_queues(s, info=None):
            """
            Try append close message in socket s.

            Note: If info then socket is live and info_sock_object already get in up.
            """
            # TODO: design code refactor
            if info:
                # recv empty data, append close message
                if not info.shutdown_message_in_queue:
                    info.message_queues.append(CLOSE_MESSAGE)
                    info.shutdown_message_in_queue = True

            else:
                socket_live = is_live_socket(s)
                if socket_live:
                    info = get_socket_info(s)

                    # recv empty data, append close message
                    if not info.shutdown_message_in_queue:
                        info.message_queues.append(CLOSE_MESSAGE)
                        info.shutdown_message_in_queue = True

        # circuit for pairs inputs outputs for simplify logic
        def closing_pair(s):
            info = get_socket_info(s)

            if info.tail_sending:
                self.__log.error('closing socket with tail: "%s" bytes' % (len(info.tail_sending),))

            if info.message_queues:
                self.__log.warning('closing socket with message_queues: "%s" messages' % (len(info.message_queues),))

            # trigger event
            try:
                self.on__connection_close(info.public(), info.tail_sending, info.message_queues)
            except Exception, e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                self.__log.critical('on__connection_close() error: %s; Traceback: %r' % (e, traceback.extract_tb(exc_traceback, 10)))

            # append_close_message(s.pair)
            append_close_in_socket_message_queues(info.pair)

            s.close()
            inputs.remove(s)
            if s in outputs: outputs.remove(s)
            del sock_info[s]

        def accept_new_client(s):
            # A "readable" server socket is ready to accept a connection
            client, client_address = s.accept() # similar to client.getpeername()
            client_proxy_address = client.getsockname()
            client_id = id(client)
            self.__log.info('new connection from %s -> proxy.socket%s' % (client_address, client_proxy_address))

            # trigger event
            try:
                if not self.filter__accept_connection(client_id, client_address, client_proxy_address):
                    self.__log.info('drop new connection %s by filter' % (client_address,))
                    return
            except Exception, e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                self.__log.critical('filter__accept_connection() error: %s; Traceback: %r' % (e, traceback.extract_tb(exc_traceback, 10)))
                return

            client.setblocking(0)

            # start forwarding
            self.__log.info('forwarding')
            forward_family, forward_socket_type, forward_address = self.get_forwarding_address()
            forward = socket.socket(forward_family,
                forward_socket_type)
            forward.setblocking(0)

            try:
                forward.connect(forward_address)
            except socket.error as e:
                if e.errno == errno.EINPROGRESS or e.errno == errno.EWOULDBLOCK:
                    self.__log.info('forwarding connect to %s except EINPROGRESS or EWOULDBLOCK (%r)' % (
                        forward_address, e.errno))  # it is normal to have EINPROGRESS here
                else:
                    self.__log.error(e.message)
                    client.close()
                    forward.close()
                    return

            forward_id, forward_proxy_address = id(forward), forward.getsockname()
            inputs.append(client)
            inputs.append(forward)

            client_info = set_socket_info(client, client_id, client_address, client_proxy_address, forward, forward_id,
                forward_address, forward_proxy_address, True)
            forward_info = set_socket_info(forward, forward_id, forward_address, forward_proxy_address, client,
                client_id,
                client_address, client_proxy_address, False)

            # trigger event
            try:
                self.on__accept_proxy_connection(client_info.public(), forward_info.public())
            except Exception, e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                self.__log.critical('on__accept_proxy_connection() error: %s; Traceback: %r' % (e, traceback.extract_tb(exc_traceback, 10)))

        try:
            while not self.__shutdown_request and inputs:
                # XXX: Consider using another file descriptor or
                # connecting to the socket to wake this up instead of
                # polling. Polling reduces our responsiveness to a
                # shutdown request and wastes cpu at all other times.

                # Wait for at least one of the sockets to be ready for processing
                self.__log.debug("waiting for the next event; inputs = %r; outputs = %r; " % (psock(inputs), psock(outputs)))

                # trigger event
                try:
                    self.on__start_event_loop()
                except Exception, e:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    self.__log.critical('on__start_event_loop() error: %s Traceback: %r' % (e, traceback.extract_tb(exc_traceback, 10)))

                try:
                    readable, writable, exceptional = select.select(inputs, outputs, inputs, poll_interval)
                except Exception, e:
                    self.__log.error("error on select: %s", e)
                    clear_bead_socket(inputs, outputs, self.__log)
                    continue

                self.__log.debug("event has occurred; readable = %r; writable = %r; exceptional = %r;" % (
                    psock(readable), psock(writable), psock(exceptional)))

                if not inputs and not outputs and not exceptional:
                    self.__log.debug('no event')
                    continue

                # Handle inputs
                for s in readable:
                    if s is self.proxy:
                        accept_new_client(s)
                        continue

                    info = get_socket_info(s)
                    if len(info.message_queues) > self.SOCKET_QUEUE_MAX_SIZE:
                        self.__log.warning(
                            'SOCKET_QUEUE_MESSAGES_MAX_SIZE limit in %s -> %s ' % (info.address, info.pair_address))

                        # maybe delete this block; for debugging
                        if info.pair not in outputs:
                            self.__log.error(
                                'socket pair not in outputs and SOCKET_QUEUE_MESSAGES_MAX_SIZE limit in %s -> %s (try appending)' % (
                                    info.address, info.pair_address))
                            outputs.append(info.pair)
                        continue

                    try:
                        data = s.recv(65536)

                    except socket.error as e:
                        self.__log.error('[client %s -socket-> proxy.socket%s].recv() except: errno = %s, msg = %r' % (
                            info.address, info.proxy_address, e.errno, e.message))

                        self.__log.info('closing pair (%s) -socket> (proxy.socket%s) after recv error' % (
                            info.address, info.proxy_address))
                        closing_pair(s)

                        if s in writable: writable.remove(s)
                        if s in exceptional: writable.remove(s)

                    else:

                        self.__log.info('received "%r" bytes  from (%s) -socket> (proxy.socket%s)' % (
                            len(data), info.address, info.proxy_address))
                        self.__log.debug('received: %s' % (hexdump(data, 0),))

                        # trigger event
                        try:
                            filtered_data = self.filter__recv_data(data, info.public())
                        except Exception, e:
                            exc_type, exc_value, exc_traceback = sys.exc_info()
                            self.__log.critical('filter__recv_data() error: %s; Traceback: %r' % (e, traceback.extract_tb(exc_traceback, 10)))
                            filtered_data = data
                        else:
                            self.__log.info('after filtering "%r" bytes from (%s) -socket> (proxy.socket%s)' % (
                                len(filtered_data), info.address, info.proxy_address))
                            self.__log.debug('after filtering: %s', hexdump(filtered_data, 0))

                        # append message to pair queues if pair not closed
                        append_in_socket_message_queues(info.pair, filtered_data)

                        # Interpret empty result as closed connection
                        if not filtered_data:
                            self.__log.info('closing pair 1 (%s) -socket> (proxy.socket%s) after reading empty data' % (
                                info.address, info.proxy_address))
                            closing_pair(s)

                            if s in writable: writable.remove(s)
                            if s in exceptional: writable.remove(s)

                # Handle outputs
                for s in writable:
                    info = get_socket_info(s)
                    if info.message_queues or info.tail_sending:

                        # first tail sending (sending old date)
                        if info.tail_sending:
                            self.__log.info('tail sending "%r" bytes to (%s) <socket- (proxy.socket%s)' % (
                                len(info.tail_sending), info.address, info.proxy_address))

                            try:
                                send = s.send(info.tail_sending)

                                # detect new tail
                                if len(info.tail_sending) != send:
                                    new_tail = info.tail_sending[send:]
                                    self.__log.info('tail on (tail) sending: "%r" bytes to (%s) <socket- (proxy.socket%s)' % (
                                        len(new_tail), info.address, info.proxy_address))
                                    info.tail_sending = new_tail
                                else:
                                    info.tail_sending = None

                            except socket.error, e:
                                self.__log.error(
                                    '[client %s <socket- proxy.socket%s].send() on tail except: errno = %s, msg = %r' % (
                                        info.address, info.proxy_address, e.errno, e.message))

                                self.__log.info('closing pair (%s) <socket- (proxy.socket%s) after send tail error' % (
                                    info.address, info.proxy_address))
                                closing_pair(s)

                                if s in exceptional: writable.remove(s)

                            continue

                        # get next message from queue if no tail_sanding and fite them
                        next_msg = info.message_queues.popleft()
                        self.__log.info('sending "%r" bytes to (%s) <socket- (proxy.socket%s)' % (
                            len(next_msg), info.address, info.proxy_address))
                        self.__log.debug('sending: %s', hexdump(next_msg, 0))

                        # trigger event
                        try:
                            filtered_next_msg = self.filter__send_data(next_msg, info.public())
                        except Exception, e:
                            exc_type, exc_value, exc_traceback = sys.exc_info()
                            self.__log.critical('filter__send_data() error: %s; Traceback: %r' % (e, traceback.extract_tb(exc_traceback, 10)))
                            filtered_next_msg = next_msg
                        else:
                            self.__log.info('after filtering "%r" bytes from (%s) <socket- (proxy.socket%s)' % (
                                len(filtered_next_msg), info.address, info.proxy_address))
                            self.__log.debug('after filtering: %s', hexdump(filtered_next_msg, 0))

                        # if pair close connection
                        if not filtered_next_msg:
                            self.__log.info('closing pair 2 (%s) <socket- (proxy.socket%s) after reading no data' % (
                                info.address, info.proxy_address))
                            closing_pair(s)

                            if s in exceptional: writable.remove(s)

                        else:
                            try:
                                sendet = s.send(filtered_next_msg)

                                # detect tail on send
                                if sendet != len(filtered_next_msg):
                                    new_tail = filtered_next_msg[sendet:]
                                    self.__log.info('tail on sending: "%r" bytes to (%s) <socket- (proxy.socket%s)' % (
                                        len(new_tail), info.address, info.proxy_address))
                                    info.tail_sending = new_tail

                            except socket.error, e:
                                self.__log.error(
                                    '[client %s <socket- proxy.socket%s].send() except: errno = %s, msg = %r' % (
                                        info.address, info.proxy_address, e.errno, e.message))

                                self.__log.info('closing pair (%s) <socket- (proxy.socket%s) after send error' % (
                                    info.address, info.proxy_address))
                                closing_pair(s)

                                if s in exceptional: writable.remove(s)
                    else:
                        # No messages waiting so stop checking for writability.
                        self.__log.debug('output queue for (%s) <socket- (proxy.socket%s) is empty' % (
                            info.address, info.proxy_address))
                        outputs.remove(s)

                # Handle "exceptional conditions"
                for s in exceptional:
                    self.__log.error('handling exceptional condition for proxy.socket%s <socket> socket%s ' %
                                   (s.getsockname(), s.getpeername()))

                    if s is self.proxy:
                        self.__log.critical('handling exceptional condition for proxy server')
                        self.proxy.close()
                        inputs.remove(self.proxy)
                        continue

                    info = get_socket_info(s)
                    # Stop listening for input on the connection
                    self.__log.info('closing pair (%s) <!socket!> proxy.socket%s after handling exceptional condition' % (
                        info.address, info.proxy_address))
                    closing_pair(s)

        finally:
            [closing_pair(x) for x in inputs if x != self.proxy]
            self.proxy.close()
            self.__shutdown_request = False
            self.__is_shut_down.set()

            # trigger event
            try:
                self.on__stop()
            except Exception, e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                self.__log.critical('on__stop() error: %s; Traceback: %r' % (e, traceback.extract_tb(exc_traceback, 10)))

            self.__log.info('stop proxy')


    def shutdown(self):
        """Stops the serve_forever loop.

        Blocks until the loop has finished. This must be called while
        serve_forever() is running in another thread, or it will
        deadlock.
        """
        self.__shutdown_request = True
        self.__is_shut_down.wait()

    # for override

    def filter__accept_connection(self, client_id, client_address, client_proxy_address):
        return True

    def on__accept_proxy_connection(self, client_sock_info, forward_sock_info):
        pass

    def filter__recv_data(self, data, sock_info):
        return data

    def filter__send_data(self, data, sock_info):
        return data

    def on__connection_close(self, sock_info, sending_tail, message_queues):
        pass

    def on__start_event_loop(self):
        pass

    def on__init(self):
        pass

    def on__stop(self):
        pass


#------------------------------------------------------
# main entry
# use as module
# python -m proxy.core
#------------------------------------------------------
if __name__ == "__main__":
    examples = """example:
 {0} -l critical 8000 "hackerdom.ru:80";
 {0} "192.168.0.101:8000" "hackerdom.ru:80";
If you have any problem write them on http://github.com/pahaz/
""".format(os.path.split(sys.argv[0])[1])


    level_name = 'critical'

    import argparse
    from proxy import ext

    parser = argparse.ArgumentParser(description="This TCP proxy server is no blocking and use select.", epilog=examples)
    parser.add_argument("proxy", help="the proxy \"ip:port\"")
    parser.add_argument("destination", help="the destination \"host:port\"")
    parser.add_argument("module", nargs='?', help="the extension proxy class", default="NoBlockProxy")
    parser.add_argument('-l', '--core-log-level', help='level core logging; if default module then level debug else level critical')
    args = parser.parse_args()

    print args

    if ':' in args.proxy:
        PROXY_HOST, PROXY_PORT = args.proxy.split(':',1)#"0.0.0.0"
    else:
        PROXY_HOST, PROXY_PORT = "0.0.0.0", args.proxy

    PROXY_PORT = int(PROXY_PORT)

    if ':' in args.destination:
        HOST, PORT = args.destination.split(':',1) # "0.0.0.0"
    else:
        print "error parse destination HOST_DNS:HOST_PORT"
        sys.exit(1)

    PORT = int(PORT)

    CLS = NoBlockProxy
    if args.module != "NoBlockProxy":
        try:
            CLS = getattr(ext, args.module)
        except:
            print "error import module: %s" % (args.module,)
            sys.exit(1)
    else:
        level_name = 'debug'

    if args.core_log_level:
        level_name = args.core_log_level

    level = LEVELS.get(level_name, logging.NOTSET)

    logging.basicConfig(format="%(created)-15f:%(levelname)7s:%(name)s: %(message)s")
    p = CLS(PROXY_HOST, PROXY_PORT, HOST, PORT, False)
    p.set_proxy_core_log_level(level)
    p.init()
    p.serve_forever()