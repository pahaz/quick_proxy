from glob import glob
import logging

__author__ = 'pahaz'

from proxy.core import NoBlockProxy

def log(ss, client_address, client_id, client_proxy_address, forward_proxy_address, forward_id, forward_address, some_more_data=""):
    p = (ss % (client_address, client_id, client_proxy_address, forward_proxy_address, forward_id, forward_address, some_more_data))\
    .replace("', ",':').replace("'",'').replace(")",'').replace('(', '')
    print p
    return p

# fixed alexbers dumper class
class Dumper:
    def __init__(self, port):
        last_session_num = len(glob("port_%d_*.dmp" % port))
        self.filename = "port_%d_%09d.dmp" % (port, last_session_num + 1)
        self.file = open(self.filename, "ab")
        self.__closed = False

    def dump(self, title, data):
        if not self.__closed:
            self.file.write('\n%s "%s" bytes\n' % (title, len(data)))
            self.file.write(data)

    def close(self):
        self.__closed = True
        self.file.close()

class DumperProxy(NoBlockProxy):
    def on__init(self):
        self.clients = []
        self.forwards = []

        self.dumpers = {}

    def on__accept_proxy_connection(self, client_sock_info, forward_sock_info, *args):
        title = log('%s  <-*-%s-> [%s PROXY %s] <-*-%s-> %s %s', client_sock_info.address, client_sock_info.id, client_sock_info.proxy_address[1],
            forward_sock_info.proxy_address[1], forward_sock_info.id, forward_sock_info.address)

        self.clients.append(client_sock_info.id)
        self.forwards.append(forward_sock_info.id)
        dumper = Dumper(self.proxy_port)

        # for check errors
        if client_sock_info.id in self.dumpers or forward_sock_info.id  in self.dumpers:
            # close old dump
            if client_sock_info.id in self.dumpers:
                a = self.dumpers[client_sock_info.id]
                a.dump('WTF: NO_CLOSE!',''); a.close()
                del self.dumpers[client_sock_info.id]
            if forward_sock_info.id in self.dumpers:
                a = self.dumpers[forward_sock_info.id]
                a.dump('WTF: NO_CLOSE!',''); a.close()
                del self.dumpers[forward_sock_info.id]

            # new dump
            self.dumpers[client_sock_info.id] = dumper
            self.dumpers[forward_sock_info.id] = dumper
            dumper.dump(title,'')

            # rais clitical error
            raise ValueError("WTF? Find no closed old Dump!")

        self.dumpers[client_sock_info.id] = dumper
        self.dumpers[forward_sock_info.id] = dumper
        dumper.dump(title,'')

    def filter__recv_data(self, data, sock_info, *args):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                title = log('%s  --*-%s>> [%s PROXY %s] --*-%s-- %s %sb', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                    sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, len(data))
            else:
                # pair closed!
                title = log('%s  --*-%s>> [%s PROXY %s] ----%s-- %s %sb', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                    sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, len(data))

        elif  sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                title = log('%s  --*-%s-- [%s PROXY %s] <<*-%s-- %s %sb', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address, len(data))
            else:
                # pair closed!
                title = log('%s  ----%s-- [%s PROXY %s] <<*-%s-- %s %sb', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address, len(data))

        else:
            title = log('WTF recv? [%s]  --%s-- [%s PROXY %s] --%s-- %s %sb', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, len(data))

        # DUMP
        self.dumpers[sock_info.id].dump(title, data)

        return data

    def filter__send_data(self, data, sock_info, *args):
        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                title = log('%s  <<*-%s-- [%s PROXY %s] --*-%s-- %s %sb', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                    sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, len(data))
            else:
                # pair closed!
                title = log('%s  <<*-%s-- [%s PROXY %s] ----%s-- %s %sb', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                    sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, len(data))

        elif  sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                title = log('%s  --*-%s-- [%s PROXY %s] --*-%s>> %s %sb', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address, len(data))
            else:
                # pair closed!
                title = log('%s  ----%s-- [%s PROXY %s] --*-%s>> %s %sb', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address, len(data))

        else:
            title = log('WTF send? [%s]  --%s-- [%s PROXY %s] --%s-- %s %sb', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, len(data))

        # DUMP
        self.dumpers[sock_info.id].dump(title, '')

        return data

    def on__connection_close(self, sock_info, tail, queue, *args):
        lst = [str(len(x)) for x in queue]
        lst_lost_queue = 'b, '.join(lst)
        some_data = "lose {}b {}".format(len(tail) if tail else 0, 'queue data [{}b]'.format(lst_lost_queue) if lst else "")

        if sock_info.id in self.clients:
            if sock_info.pair_id in self.forwards:
                title = log('%s  ----%s-- [%s PROXY %s] --*-%s-- %s %s', sock_info.address, sock_info.id,
                    sock_info.proxy_address[1], sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, some_data)
            else:
                # sock_info.pair_id is closed!
                title = log('%s  ----%s-- [%s PROXY %s] ----%s-- %s %s', sock_info.address, sock_info.id,
                    sock_info.proxy_address[1], sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, some_data)

                # DUMP
                dumper = self.dumpers[sock_info.id]
                dumper.dump(title, "END.")
                dumper.close()
                del self.dumpers[sock_info.id]
                del self.dumpers[sock_info.pair_id]

            self.clients.remove(sock_info.id)

        elif sock_info.id in self.forwards:
            if sock_info.pair_id in self.clients:
                title = log('%s  --*-%s-- [%s PROXY %s] ----%s-- %s %s', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address, some_data)
            else:
                # sock_info.pair_id is closed!
                title = log('%s  ----%s-- [%s PROXY %s] ----%s-- %s %s', sock_info.pair_address, sock_info.pair_id,
                    sock_info.pair_proxy_address[1], sock_info.proxy_address[1], sock_info.id, sock_info.address, some_data)

                # DUMP
                dumper = self.dumpers[sock_info.id]
                dumper.dump(title, "END.")
                dumper.close()
                del self.dumpers[sock_info.id]
                del self.dumpers[sock_info.pair_id]

            self.forwards.remove(sock_info.id)

        else:
            title = log('WTF close? [%s]  --%s-- [%s PROXY %s] --%s-- %s %s', sock_info.address, sock_info.id, sock_info.proxy_address[1],
                sock_info.pair_proxy_address[1], sock_info.pair_id, sock_info.pair_address, some_data)

            # DUMP
            dumper = self.dumpers[sock_info.id]
            dumper.dump(title, "WTF END.")
            dumper.close()
            del self.dumpers[sock_info.id]
            del self.dumpers[sock_info.pair_id]


def on__start_event_loop(self, *args):
        pass
