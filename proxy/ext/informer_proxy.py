import logging

__author__ = 'pahaz'

from proxy.core import NoBlockProxy

class InformerProxy(NoBlockProxy):
    def log(self, ss, client_address, client_id, client_proxy_address, forward_proxy_address, forward_id, forward_address):
        print ss % (client_address, client_id, client_proxy_address, forward_proxy_address, forward_id, forward_address)

    def on__init(self):
        self.clients = []
        self.forwards = []

    def on__accept_proxy_connection(self, client_sock_info, forward_sock_info):
        self.log('[%s]  <-socket-%s-> [%s PROXY %s] <-socket-%s-> [%s]', client_sock_info.address, client_sock_info.id, client_sock_info.proxy_address,
            forward_sock_info.proxy_address, forward_sock_info.id, forward_sock_info.address)

        self.clients.append(client_sock_info.id)
        self.forwards.append(forward_sock_info.id)

    def filter__recv_data(self, data, sock_info):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                self.log('[%s]  --socket-%s>> [%s PROXY %s] --socket-%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                    sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)
            else:
                # pair closed!
                self.log('[%s]  --socket-%s>> [%s PROXY %s] ---------%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                    sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

        elif  sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                self.log('[%s]  --socket-%s-- [%s PROXY %s] <<socket-%s-- [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)
            else:
                # pair closed!
                self.log('[%s]  ---------%s-- [%s PROXY %s] <<socket-%s-- [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)

        else:
            self.log('WTF recv? [%s]  --%s-- [%s PROXY %s] --%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

        return data

    def filter__send_data(self, data, sock_info):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                self.log('[%s]  <<socket-%s-- [%s PROXY %s] --socket-%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                    sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)
            else:
                # pair closed!
                self.log('[%s]  <<socket-%s-- [%s PROXY %s] ---------%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                    sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

        elif  sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                self.log('[%s]  --socket-%s-- [%s PROXY %s] --socket-%s>> [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)
            else:
                # pair closed!
                self.log('[%s]  ---------%s-- [%s PROXY %s] --socket-%s>> [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)

        else:
            self.log('WTF send? [%s]  --%s-- [%s PROXY %s] --%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

        return data

    def on__connection_close(self, sock_info):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                self.log('[%s]  ---------%s-- [%s PROXY %s] --socket-%s-- [%s]', sock_info.address, sock_info.id,
                    sock_info.proxy_address, sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)
            else:
                # sock_info.pair_id is closed!
                self.log('[%s]  ---------%s-- [%s PROXY %s] ---------%s-- [%s]', sock_info.address, sock_info.id,
                    sock_info.proxy_address, sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)
            self.clients.remove(sock_info.id)

        elif sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                self.log('[%s]  --socket-%s-- [%s PROXY %s] ---------%s-- [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)
            else:
                # sock_info.pair_id is closed!
                self.log('[%s]  ---------%s-- [%s PROXY %s] ---------%s-- [%s]', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address, sock_info.proxy_address, sock_info.id, sock_info.address)
            self.forwards.remove(sock_info.id)

        else:
            self.log('WTF close? [%s]  --%s-- [%s PROXY %s] --%s-- [%s]', sock_info.address, sock_info.id, sock_info.proxy_address,
                sock_info.pair_proxy_address, sock_info.pair_id, sock_info.pair_address)

    def on__start_event_loop(self):
        pass

#------------------------------------------------------
# main entry
# use as module
# python -m proxy.core
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
    p = InformerProxy(PROXY_HOST, PROXY_PORT, HOST, PORT, False)
    p.set_proxy_core_log_level(logging.CRITICAL)
    p.init()
    p.serve_forever()