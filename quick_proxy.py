import threading
import logging
import select
import socket
import errno
from collections import deque

#-------------------------------------------------------------
# Hexdump Cool :)
# default width 16
#--------------------------------------------------------------
FILTER = ''.join([(len(repr(chr(x))) == 3) and chr(x) or '.' for x in range(256)])
def hexdump( src, width=16 ):
    if width == 0: return src.translate(FILTER)

    result = []
    for i in xrange(0, len(src), width):
        s = src[i:i + width]
        hexa = ' '.join(["%02X" % ord(x) for x in s])
        printable = s.translate(FILTER)
        result.append("%04X   %s   %s\n" % (i, hexa, printable))
    return ''.join(result)

def get_address(HOST, PORT):
    for res in socket.getaddrinfo(HOST, PORT, socket.AF_UNSPEC, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        try:
            s = socket.socket(af, socktype, proto)
        except socket.error, msg:
            continue
        try:
            s.connect(sa)
        except socket.error, msg:
            s.close()
            continue

        if s: s.close()
        return af, socktype, sa[:2]
    return None, None, None

class LoggingObject(object):
    def __init__(self, logger_name):
        self.log = logging.getLogger(logger_name)

    def add_log_handler(self, handler):
        self.log.addHandler(handler)

    def set_log_level(self, lvl):
        self.log.setLevel(lvl)

class NoBlockProxy(LoggingObject):
    SOCKET_QUEUE_MAX_SIZE = 30
    PULL_INTERVAL = 10

    proxy_allow_reuse_address = True
    proxy_socket_type = socket.SOCK_STREAM
    proxy_request_queue_size = 5
    max_packet_size = 8192

    def get_forwarding_address(self):
        if not self.forwarding_address_resolved:
            try:
                self.__forward_family, self.__forward_socket_type, self.__forward_address = get_address(
                    *self.__forward_address_init)
            except Exception, e:
                self.log.critical('error resolving forward adders: %r' % (e.message,))
                raise e
            else:
                self.log.debug(
                    'resolved forward adders; forward_family = %r; forward_socket_type = %r; forward_address = %r;' % (
                        self.__forward_family, self.__forward_socket_type, self.__forward_address))
                self.forwarding_address_resolved = True

        return self.__forward_family, self.__forward_socket_type, self.__forward_address

    def __init__(self, proxy_host, proxy_port, forward_host, forward_port, init_socket=True,
                 pre_resolving_forward_host=True):
        self.__proxy_address_init = (proxy_host, proxy_port)
        self.__forward_address_init = (forward_host, forward_port)
        LoggingObject.__init__(self, 'proxy[%s]' % (proxy_port, ))
        self.__is_shut_down = threading.Event()
        self.__shutdown_request = False

        self.proxy_init = False
        self.forwarding_address_resolved = False

        if init_socket: self.init(pre_resolving_forward_host)

    def init(self, pre_resolving_forward_host=True):
        """Called by constructor to bind the socket and activate the server.

        May be overridden.

        """
        if self.proxy_init:
            self.log.warning('proxy already init and setup')
            return

        proxy_host, proxy_port = self.__proxy_address_init
        forward_host, forward_port = self.__forward_address_init

        self.log.info(
            'init proxy server (*) <-> proxy(%r:%r) <-> (%r:%r)' % (proxy_host, proxy_port, forward_host, forward_port))

        # set proxy family
        proxy_family = socket.AF_INET6 if ":" in proxy_host else socket.AF_INET
        if not socket.has_ipv6 and proxy_family == socket.AF_INET6:
            self.log.critical('IPv6 is not supported on this platform but you proxy bind address is IPv6')
            raise ValueError('IPv6 is not supported on this platform but you bind address is IPv6')

        try:
            self.proxy = socket.socket(proxy_family, self.proxy_socket_type)
        except socket.error, e:
            self.log.critical('creating proxy socket error: %s' % (e,))
            raise OSError('socket error: %s; errno = %s' % (e.errno, e.message))

        if pre_resolving_forward_host: self.get_forwarding_address() # try pre resolving

        self.log.info('starting setup proxy %s bind%r' % (
            'REUSEADDR NOBLOCK' if self.proxy_allow_reuse_address else 'NOBLOCK', self.__proxy_address_init))

        try:
            if self.proxy_allow_reuse_address: self.proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.proxy.setblocking(0)
            self.proxy.bind(self.__proxy_address_init)
            self.proxy.listen(self.proxy_request_queue_size)
        except socket.error, e:
            self.proxy.close()
            self.log.critical('error on initial proxy: %s' % (e,))
            raise IOError('error on initial proxy')

        self.proxy_init = True

        # trigger event
        try:
            self.on__init()
        except Exception, e:
            self.log.critical('on__init() error: %s' % (e,))


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

        # small utils
        def clear_bead_socket(inputs, outputs, log):
            log.info("cleaning bead sockets")
            for s in inputs:
                try:
                    select([s], [], [], 0)
                except:
                    log.warning('find bead: %s' % (id(s),))
                    inputs.remove(s)

            for s in outputs:
                try:
                    select([], [s], [], 0)
                except:
                    log.warning('find bead: %s' % (id(s),))
                    outputs.remove(s)

        self.__is_shut_down.clear()

        # Sockets from which we expect to read
        inputs = [self.proxy]

        # Sockets to which we expect to write
        outputs = []

        # Outgoing message queues (socket:Queue)
        # message_queues = {}

        # socket info (socket -> client_id, client_address, client_proxy_address, pair_socket, pair_id, pair_address, pair_proxy_address
        sock_info = {}

        def enum(**enums):
            return type('PublicSockInfo', (), enums)

        class PublicSockInfo(object):
            def __init__(self, id, address, proxy_address, type, pair_id, pair_address, pair_proxy_address):
                self.__public_info = enum(id=id, address=address, proxy_address=proxy_address, type=type,
                    pair_id=pair_id,
                    pair_address=pair_address, pair_proxy_address=pair_proxy_address)
                self.id = id
                self.address = address
                self.proxy_address = proxy_address
                self.type = type
                self.pair_id = pair_id
                self.pair_address = pair_address
                self.pair_proxy_address = pair_proxy_address

            def public(self):
                return self.__public_info

        class SockInfo(PublicSockInfo):
            def __init__(self, pair, id, address, proxy_address, type, pair_id, pair_address, pair_proxy_address):
                self.pair = pair
                self.message_queues = deque()
                super(SockInfo, self).__init__(id, address, proxy_address, type, pair_id, pair_address,
                    pair_proxy_address)

        def get_socket_info(s):
            info = sock_info[s]
            self.log.debug(
                'socket info: id=%s; address=%s; proxy_address=%s; pair_id=%s; pair_address=%s, pair_proxy_address=%s, type=%s, message_queues=%s' % (
                info.id, info.address, info.proxy_address, info.pair_id, info.pair_address, info.pair_proxy_address,
                info.type, info.message_queues))
            return info

        def set_socket_info(s, id, address, proxy_address, pair, pair_id, pair_address, pair_proxy_address, type):
            new_sock_info = SockInfo(pair, id, address, proxy_address, type, pair_id, pair_address, pair_proxy_address)
            sock_info[s] = new_sock_info
            return new_sock_info

        #            sock_info[s] = SockInfo(id=id, address=address, proxy_address=proxy_address,
        #                pair=pair, pair_id=pair_id, pair_address=pair_address, pair_proxy_address=pair_proxy_address,
        #                type=type,
        #                message_queues=deque())

        def is_live_socket(s):
            return s in sock_info

        def append_in_socket_message_queues(s, data):
            sock_info[s].message_queues.append(data)

        # circuit for pairs inputs outputs for simplify logic
        def closing_pair(s):
            info = get_socket_info(s)

            # trigger event
            try:
                self.on__connection_close(info.public())
            except Exception, e:
                self.log.critical('on__connection_close() error: %s' % (e,))

            s.close()
            inputs.remove(s)
            if s in outputs: outputs.remove(s)
            del sock_info[s]

        def accept_new_client(s):
            # A "readable" server socket is ready to accept a connection
            client, client_address = s.accept() # similar to client.getpeername()
            client_proxy_address = client.getsockname()
            client_id = id(client)
            self.log.info('new connection from %s -> proxy.socket%s' % (client_address, client_proxy_address))

            # trigger event
            try:
                if not self.filter__accept_connection(client_id, client_address, client_proxy_address):
                    self.log.info('drop new connection %s by filter' % (client_address,))
                    return
            except Exception, e:
                self.log.critical('filter__accept_connection() error: %s' % (e,))
                return

            client.setblocking(0)

            # start forwarding
            self.log.info('forwarding')
            forward_family, forward_socket_type, forward_address = self.get_forwarding_address()
            forward = socket.socket(forward_family,
                forward_socket_type)
            forward.setblocking(0)

            try:
                forward.connect(forward_address)
            except socket.error as e:
                if e.errno == errno.EINPROGRESS or e.errno == errno.EWOULDBLOCK:
                    self.log.info('forwarding connect to %s except EINPROGRESS or EWOULDBLOCK (%r)' % (
                        forward_address, e.errno))  # it is normal to have EINPROGRESS here
                else:
                    self.log.error(e.message)
                    client.close()
                    forward.close()
                    return

            forward_id, forward_proxy_address = id(forward), forward.getsockname()
            inputs.append(client)
            inputs.append(forward)

            client_info = set_socket_info(client, client_id, client_address, client_proxy_address, forward, forward_id,
                forward_address, forward_proxy_address, 'client')
            forward_info = set_socket_info(forward, forward_id, forward_address, forward_proxy_address, client,
                client_id,
                client_address, client_proxy_address, 'forward')

            # trigger event
            try:
                self.on__accept_proxy_connection(client_info.public(), forward_info.public())
            except Exception, e:
                self.log.critical('on__accept_proxy_connection() error: %s' % (e,))

        try:
            while not self.__shutdown_request and inputs:
                # XXX: Consider using another file descriptor or
                # connecting to the socket to wake this up instead of
                # polling. Polling reduces our responsiveness to a
                # shutdown request and wastes cpu at all other times.

                # Wait for at least one of the sockets to be ready for processing
                self.log.debug("waiting for the next event; inputs = %r; outputs = %r; " % (inputs, outputs))

                # trigger event
                try:
                    self.on__start_event_loop()
                except Exception, e:
                    self.log.critical('on__start_event_loop() error: %s' % (e,))

                try:
                    readable, writable, exceptional = select.select(inputs, outputs, inputs, poll_interval)
                except Exception, e:
                    self.log.error("error on select: %s", e)
                    clear_bead_socket(inputs, outputs, self.log)
                    continue

                self.log.debug("event has occurred; readable = %r; writable = %r; exceptional = %r;" % (
                    readable, writable, exceptional))

                if not inputs and not outputs and not exceptional:
                    self.log.debug('no event')
                    continue

                # Handle inputs
                for s in readable:
                    if s is self.proxy:
                        accept_new_client(s)
                        continue

                    info = get_socket_info(s)
                    if len(info.message_queues) > self.SOCKET_QUEUE_MAX_SIZE:
                        self.log.warning(
                            'SOCKET_QUEUE_MESSAGES_MAX_SIZE limit in %s -> %s ' % (info.address, info.pair_address))

                        # maybe delete this block; for debugging
                        if info.pair not in outputs:
                            self.log.error(
                                'socket pair not in outputs and SOCKET_QUEUE_MESSAGES_MAX_SIZE limit in %s -> %s (try appending)' % (
                                info.address, info.pair_address))
                            outputs.append(info.pair)
                        continue

                    try:
                        data = s.recv(65536)
                    except socket.error as e:
                        self.log.error('[client %s -socket-> proxy.socket%s].recv() except: errno = %s, msg = %r' % (
                            info.address, info.proxy_address, e.errno, e.message))

                        self.log.info('closing pair (%s) -socket> (proxy.socket%s) after recv error' % (
                            info.address, info.proxy_address))
                        closing_pair(s)

                        if s in writable: writable.remove(s)
                        if s in exceptional: writable.remove(s)

                    else:
                        self.log.info('received "%r" bytes  from (%s) -socket> (proxy.socket%s)' % (
                            len(data), info.address, info.proxy_address))
                        self.log.debug('received: %s' % (hexdump(data, 0),))

                        # trigger event
                        try:
                            filtered_data = self.filter__recv_data(data, info.public())
                        except Exception, e:
                            self.log.critical('filter__recv_data() error: %s', e)
                            filtered_data = data

                        self.log.info('after filtering "%r" bytes from (%s) -socket> (proxy.socket%s)' % (
                            len(data), info.address, info.proxy_address))
                        self.log.debug('after filtering: %s', hexdump(filtered_data, 0))

                        # append message to pair queues if pair not closed
                        pair_socket_live = is_live_socket(info.pair)
                        if pair_socket_live:
                            append_in_socket_message_queues(info.pair, filtered_data)
                        else:
                            self.log.warning('recv pair is closed')

                        # Add output channel for response
                        if info.pair not in outputs and pair_socket_live:
                            outputs.append(info.pair)

                        # Interpret empty result as closed connection
                        if not filtered_data:
                            self.log.info('closing pair 1 (%s) -socket> (proxy.socket%s) after reading no data' % (
                                info.address, info.proxy_address))
                            closing_pair(s)

                            if s in writable: writable.remove(s)
                            if s in exceptional: writable.remove(s)

                # Handle outputs
                for s in writable:
                    info = get_socket_info(s)
                    if info.message_queues:
                        next_msg = info.message_queues.popleft()
                        self.log.info('sending "%r" bytes to (%s) <socket- (proxy.socket%s)' % (
                            len(next_msg), info.address, info.proxy_address))
                        self.log.debug('sending: %s', hexdump(next_msg, 0))

                        # trigger event
                        try:
                            filtered_next_msg = self.filter__send_data(next_msg, info.public())
                        except Exception, e:
                            self.log.critical('filter__send_data() error: %s', e)

                        self.log.info('after filtering "%r" bytes from (%s) <socket- (proxy.socket%s)' % (
                            len(filtered_next_msg), info.address, info.proxy_address))
                        self.log.debug('after filtering: %s', hexdump(filtered_next_msg, 0))

                        # if pair close connection
                        if not filtered_next_msg:
                            self.log.info('closing pair 2 (%s) <socket- (proxy.socket%s) after reading no data' % (
                                info.address, info.proxy_address))
                            closing_pair(s)

                            if s in exceptional: writable.remove(s)

                        else:
                            try:
                                s.send(filtered_next_msg)
                            except socket.error, e:
                                self.log.error(
                                    '[client %s <socket- proxy.socket%s].send() except: errno = %s, msg = %r' % (
                                        info.address, info.proxy_address, e.errno, e.message))

                                self.log.info('closing pair (%s) <socket- (proxy.socket%s) after send error' % (
                                    info.address, info.proxy_address))
                                closing_pair(s)

                                if s in exceptional: writable.remove(s)
                    else:
                        # No messages waiting so stop checking for writability.
                        self.log.debug('output queue for (%s) <socket- (proxy.socket%s) is empty' % (
                            info.address, info.proxy_address))
                        outputs.remove(s)

                # Handle "exceptional conditions"
                for s in exceptional:
                    self.log.error('handling exceptional condition for proxy.socket%s <socket> socket%s ' %
                                   (s.getsockname(), s.getpeername()))

                    if s is self.proxy:
                        self.log.critical('handling exceptional condition for proxy server')
                        self.proxy.close()
                        inputs.remove(self.proxy)
                        continue

                    info = get_socket_info(s)
                    # Stop listening for input on the connection
                    self.log.info('closing pair (%s) <!socket!> proxy.socket%s after handling exceptional condition' % (
                        info.address, info.proxy_address))
                    closing_pair(s)

        finally:
            [closing_pair(x) for x in inputs if x != self.proxy]
            self.proxy.close()
            self.__shutdown_request = False
            self.__is_shut_down.set()

    def shutdown(self):
        """Stops the serve_forever loop.

        Blocks until the loop has finished. This must be called while
        serve_forever() is running in another thread, or it will
        deadlock.
        """
        self.__shutdown_request = True
        self.__is_shut_down.wait()

    def filter__accept_connection(self, client_id, client_address, client_proxy_address):
        return True

    def on__accept_proxy_connection(self, client_sock_info, forward_sock_info):
        pass

    def filter__recv_data(self, data, sock_info):
        return data

    def filter__send_data(self, data, sock_info):
        return data

    def on__connection_close(self, sock_info):
        pass

    def on__start_event_loop(self):
        pass

    def on__init(self):
        pass


def log(ss, client_address, client_id, client_proxy_address, forward_proxy_address, forward_id, forward_address):
    print ss % (client_address, client_id, client_proxy_address, forward_proxy_address, forward_id, forward_address)


class ExampleInformer(NoBlockProxy):
    def on__init(self):
        self.clients = []
        self.forwards = []

    def on__accept_proxy_connection(self, client_sock_info, forward_sock_info):
        log('[%s]  <-socket-%s-> [%s PROXY %s] <-socket-%s-> [%s]', client_sock_info.address, client_sock_info.id, client_sock_info.proxy_address,
            forward_sock_info.proxy_address, forward_sock_info.id, forward_sock_info.address)

        self.clients.append(client_sock_info.id)
        self.forwards.append(forward_sock_info.id)

    def filter__recv_data(self, data, sock_info):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                log('[%s]  --socket-%s>> [%s PROXY %s] --socket-%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                    sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)
            else:
                # pair closed!
                log('[%s]  --socket-%s>> [%s PROXY %s] ---------%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                    sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

        elif  sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                log('[%s]  --socket-%s-- [%s PROXY %s] <<socket-%s-- [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)
            else:
                # pair closed!
                log('[%s]  ---------%s-- [%s PROXY %s] <<socket-%s-- [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)

        else:
            log('WTF recv? [%s]  --%s-- [%s PROXY %s] --%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

        return data

    def filter__send_data(self, data, sock_info):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                log('[%s]  <<socket-%s-- [%s PROXY %s] --socket-%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                    sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)
            else:
                # pair closed!
                log('[%s]  <<socket-%s-- [%s PROXY %s] ---------%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                    sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

        elif  sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                log('[%s]  --socket-%s-- [%s PROXY %s] --socket-%s>> [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)
            else:
                # pair closed!
                log('[%s]  ---------%s-- [%s PROXY %s] --socket-%s>> [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)

        else:
            log('WTF send? [%s]  --%s-- [%s PROXY %s] --%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

        return data

    def on__connection_close(self, sock_info):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                log('[%s]  ---------%s-- [%s PROXY %s] --socket-%s-- [%s]', sock_info.address, sock_info.id,
                    sock_info.proxy_address, sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)
            else:
                # sock_info.pair_id is closed!
                log('[%s]  ---------%s-- [%s PROXY %s] ---------%s-- [%s]', sock_info.address, sock_info.id,
                    sock_info.proxy_address, sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)
            self.clients.remove(sock_info.id)

        elif sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                log('[%s]  --socket-%s-- [%s PROXY %s] ---------%s-- [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)
            else:
                # sock_info.pair_id is closed!
                log('[%s]  ---------%s-- [%s PROXY %s] ---------%s-- [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)
            self.forwards.remove(sock_info.id)

        else:
            log('WTF close? [%s]  --%s-- [%s PROXY %s] --%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

    def on__start_event_loop(self):
        pass


#------------------------------------------------------
# main entry
#------------------------------------------------------
if __name__ == "__main__":
    import sys, os

    if len(sys.argv) == 5:
        # {0} PROXY_PORT to HOST PORT
        if sys.argv[2].lower() != 'to':
            print("Error use: key word 'to' missed")
            sys.exit(1)

        HOST = sys.argv[3]
        PORT = int(sys.argv[4])
        PROXY_PORT = int(sys.argv[1])
        PROXY_HOST = "0.0.0.0"

    elif len(sys.argv) == 6:
        # {0} PROXY_IP PROXY_PORT to HOST PORT
        if sys.argv[3].lower() != 'to':
            print("Error use: key word 'to' missed")
            sys.exit(1)

        HOST = sys.argv[4]
        PORT = int(sys.argv[5])
        PROXY_PORT = int(sys.argv[2])
        PROXY_HOST = sys.argv[1]

    else:
        print("""
        Uses:
            {0} [PROXY_IP] PROXY_PORT to HOST PORT

        Example:
            {0} 8000 to hackerdom.ru 80
            {0} 192.168.0.101 8000 to hackerdom.ru 80
        """.format(os.path.split(sys.argv[0])[1]))
        sys.exit(1)

    logging.basicConfig(format="%(created)-15f:%(levelname)7s:%(name)s: %(message)s")
    p = ExampleInformer(PROXY_HOST, PROXY_PORT, HOST, PORT, False)
    p.set_log_level(logging.WARNING)
    p.init()
    p.serve_forever()
