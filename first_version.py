import logging
import socket
import sys
#-------------------------------------------------------------
# Hexdump Cool :)
# default width 16
#--------------------------------------------------------------
import threading

FILTER=''.join([(len(repr(chr(x)))==3) and chr(x) or '.' for x in range(256)])
def hexdump( src, width=16 ):
    if width == 0: return src.translate(FILTER)

    result=[]
    for i in xrange(0, len(src), width):
        s = src[i:i+width]
        hexa = ' '.join(["%02X"%ord(x) for x in s])
        printable = s.translate(FILTER)
        result.append("%04X   %s   %s\n" % (i, hexa, printable))
    return ''.join(result)

import logging
import select
import socket
from collections import deque

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

IPV_6 = False
SOCKET_QUEUE_MAX_SIZE = 30
PULL_INTERVAL = 10

__author__ = 'stribog'

def start_proxy(proxy_port, forward_host, forward_port):
    log = logging.getLogger('proxy[%s]' % (proxy_port, ))


    strm_out = logging.StreamHandler(sys.__stdout__)
    log.setLevel(logging.DEBUG)
    log.addHandler(strm_out)


    log.info('setup proxy for proxy %s -> (%s:%s).' % (proxy_port, forward_host, forward_port))

    proxy_family, proxy_ip = (socket.AF_INET6, "::") if IPV_6 else\
    (socket.AF_INET, "0.0.0.0")
    proxy = socket.socket(proxy_family, socket.SOCK_STREAM)
    proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    proxy.setblocking(0)
    proxy.bind((proxy_ip, proxy_port))
    proxy.listen(5)

    proxy_address = (proxy_ip, proxy_port)
    forward_family, forward_socktype, forward_address = get_address(forward_host, forward_port)

    # Sockets from which we expect to read
    inputs = [ proxy ]

    # Sockets to which we expect to write
    outputs = [ ]

    # Outgoing message queues (socket:Queue)
    message_queues = {}

    # Proxy pairs (socket -> socket, sockname) , sockname - for log printing if pair socket closed.
    pairs = {}

    while inputs:

        # Wait for at least one of the sockets to be ready for processing
        log.debug("waiting for the next event")
        #log.debug("inputs = %r; outputs = %r; pairs = %r;" % (inputs, outputs, pairs))

        try:
            readable, writable, exceptional = select.select(inputs, outputs, inputs, PULL_INTERVAL)
        except Exception as err:
            log.error(err.message)
            log.info("cleaning bead sockets")
            for s in readable:
                try:
                    select([s], [], [], 0)
                except:
                    log.warning('find bead: %s' % s.getsockname())
                    inputs.remove(s)

            for s in writable:
                try:
                    select([], [s], [], 0)
                except:
                    log.warning('find bead: %s' % s.getsockname())
                    outputs.remove(s)

            continue

        #log.debug("readable = %r; writable = %r; exceptional = %r;" % (readable, writable, exceptional))

        if not inputs and not outputs and not exceptional:
            log.debug('no event')
            continue

        # Handle inputs
        for s in readable:

            if s is proxy:
                # A "readable" server socket is ready to accept a connection
                client, client_address = s.accept()
                log.info('new connection from %s' % (client_address,))
                client.setblocking(0)

                log.info('forwarding')
                server = socket.socket(forward_family,
                    forward_socktype)
                server.setblocking(0)

                try:
                    server.connect(forward_address)
                except socket.error as e:
                    if e.errno == socket.errno.EINPROGRESS or e.errno == socket.errno.EWOULDBLOCK:
                        log.warning('forwarding connect to %s except EINPROGRESS or EWOULDBLOCK (%r)' % (forward_address,e.errno))  # it is normal to have EINPROGRESS here
                    else:
                        log.error(e.message)
                        client.close()
                        server.close()
                        continue

                inputs.append(client)
                inputs.append(server)

                pairs[client] = server, forward_address
                pairs[server] = client, client_address

                # Give the connection a queue for data we want to send
                message_queues[client] = deque()
                message_queues[server] = deque()

                continue

            pair, pair_addr = pairs[s]
            if len(message_queues[s]) > SOCKET_QUEUE_MAX_SIZE:
                log.warning('SOCKET_QUEUE_MESSAGES_MAX_SIZE limit in %s -> %s ' % (s.getsockname(), pair_addr))
                continue

            try:
                data = s.recv(65536)
            except socket.error as e:
                log.error('[%s].recv() except: errno = %s, msg = %r' % (s.getsockname(), e.errno, e.message))

                log.info('closing pair (%s) -> (%s) after recv error' % (s.getsockname(), pair_addr))
                s.close()
                inputs.remove(s)
                if s in outputs: outputs.remove(s)
                del pairs[s]
                del message_queues[s]

                if s in writable: writable.remove(s)
                if s in exceptional: writable.remove(s)

            else:

                log.info('received "%r" bytes  from (%s) -> (%s)' % (len(data), s.getsockname(), pair_addr))
                #log.debug('received: %s' % (hexdump(data, 0),))

                p_in_q = pair in message_queues
                if p_in_q: message_queues[pair].append(data)
                else: log.warning('recv pair is closed')
                # Add output channel for response
                if pair not in outputs and p_in_q:
                    outputs.append(pair)

                if not data:
                    # Interpret empty result as closed connection
                    log.info('closing pair 1 (%s) -> (%s) after reading no data'% (s.getsockname(), pair_addr))

                    s.close()
                    inputs.remove(s)
                    if s in outputs: outputs.remove(s)
                    del pairs[s]
                    del message_queues[s]

                    if s in writable: writable.remove(s)
                    if s in exceptional: writable.remove(s)


        # Handle outputs
        for s in writable:
            queue = message_queues[s]
            pair, pair_addr = pairs[s]
            if len(queue):
                next_msg = message_queues[s].popleft()
                log.info('sending "%r" bytes to (%s) <- (%s)' % (len(next_msg), s.getsockname(), pair_addr))
                #log.debug('sending: %s' % hexdump(next_msg, 0))

                if not len(next_msg):

                    log.info('closing pair 2 (%s) -> (%s) after reading no data'% (s.getsockname(), pair_addr))

                    s.close()
                    inputs.remove(s)
                    if s in outputs: outputs.remove(s)
                    del pairs[s]
                    del message_queues[s]

                    if s in exceptional: writable.remove(s)

                else:

                    try:
                        s.send(next_msg)
                    except socket.error, e:
                        log.error('[%s].send() except errno = %s' % (s.getsockname(), e.errno))

                        log.info('closing pair (%s) <- (%s) after send error' % (s.getsockname(), pair_addr))
                        s.close()
                        inputs.remove(s)
                        if s in outputs: outputs.remove(s)
                        del pairs[s]
                        del message_queues[s]

                        if s in exceptional: writable.remove(s)
            else:
                # No messages waiting so stop checking for writability.
                log.debug('output queue for (%s) <- (%s) is empty' % (s.getsockname(), pair_addr))
                outputs.remove(s)

        # Handle "exceptional conditions"
        for s in exceptional:
            log.error('handling exceptional condition for %s', (s.getpeername(),))

            if s is proxy:
                log.critical('handling exceptional condition for proxy server')
                proxy.close()
                inputs.remove(proxy)
                continue

            pair, pair_addr = pairs[s]
            # Stop listening for input on the connection
            log.info('closing pair (%s) -!> (%s) after handling exceptional condition' % (s.getsockname(), pair_addr))
            s.close()
            inputs.remove(s)
            if s in outputs: outputs.remove(s)
            del pairs[s]
            del message_queues[s]