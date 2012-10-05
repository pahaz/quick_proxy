import logging

__author__ = 'pahaz'

from proxy.core import NoBlockProxy

def log(ss, client_address, client_id, client_proxy_address, forward_proxy_address, forward_id, forward_address):
    print (ss % (client_address, client_id, client_proxy_address, forward_proxy_address, forward_id, forward_address))\
        .replace("', ",':').replace("'",'').replace(")",'').replace('(', '')

class InformerProxy(NoBlockProxy):
    def on__init(self):
        self.clients = []
        self.forwards = []

    def on__accept_proxy_connection(self, client_sock_info, forward_sock_info, *args):
        log('%s  <-*-%s-> [%s PROXY %s] <-*-%s-> %s', client_sock_info.address, client_sock_info.id, client_sock_info.proxy_address[1],
            forward_sock_info.proxy_address[1], forward_sock_info.id, forward_sock_info.address)

        self.clients.append(client_sock_info.id)
        self.forwards.append(forward_sock_info.id)

    def filter__recv_data(self, data, sock_info, *args):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                log('%s  --*-%s>> [%s PROXY %s] --*-%s-- %s', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                    sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)
            else:
                # pair closed!
                log('%s  --*-%s>> [%s PROXY %s] ----%s-- %s', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                    sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)

        elif  sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                log('%s  --*-%s-- [%s PROXY %s] <<*-%s-- %s', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address)
            else:
                # pair closed!
                log('%s  ----%s-- [%s PROXY %s] <<*-%s-- %s', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address)

        else:
            log('WTF recv? [%s]  --%s-- [%s PROXY %s] --%s-- %s', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)

        return data

    def filter__send_data(self, data, sock_info, *args):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                log('%s  <<*-%s-- [%s PROXY %s] --*-%s-- %s', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                    sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)
            else:
                # pair closed!
                log('%s  <<*-%s-- [%s PROXY %s] ----%s-- %s', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                    sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)

        elif  sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                log('%s  --*-%s-- [%s PROXY %s] --*-%s>> %s', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address)
            else:
                # pair closed!
                log('%s  ----%s-- [%s PROXY %s] --*-%s>> %s', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address)

        else:
            log('WTF send? [%s]  --%s-- [%s PROXY %s] --%s-- %s', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)

        return data

    def on__connection_close(self, sock_info, *args):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                log('%s  ----%s-- [%s PROXY %s] --*-%s-- %s', sock_info.address, sock_info.id,
                    sock_info.proxy_address[1], sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)
            else:
                # sock_info.pair_id is closed!
                log('%s  ----%s-- [%s PROXY %s] ----%s-- %s', sock_info.address, sock_info.id,
                    sock_info.proxy_address[1], sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)
            self.clients.remove(sock_info.id)

        elif sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                log('%s  --*-%s-- [%s PROXY %s] ----%s-- %s', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address)
            else:
                # sock_info.pair_id is closed!
                log('%s  ----%s-- [%s PROXY %s] ----%s-- %s', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address)
            self.forwards.remove(sock_info.id)

        else:
            log('WTF close? [%s]  --%s-- [%s PROXY %s] --%s-- %s', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address)

    def on__start_event_loop(self, *args):
        pass
