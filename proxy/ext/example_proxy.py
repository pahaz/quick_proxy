__author__ = 'pahaz'

from proxy.core import NoBlockProxy

class ExampleProxy(NoBlockProxy):
    '''
    You proxy example.
    proxy = ExampleProxy(PROXY_HOST, PROXY_PORT, HOST, PORT, False) # False - no auto init call
    proxy.init() # start event and call on__init()
    proxy.serve_forever() # start proxy forever
                          # on each iteration trigger on__start_event_loop()

    '''
    def on__init(self, *args):
        '''
        Call if end of function proxy.init()
        '''

    def on__stop(self, *args):
        pass

    def on__accept_proxy_connection(self, client_sock_info, forward_sock_info, *args):
        pass

    def filter__recv_data(self, data, sock_info, *args):
        return data

    def filter__send_data(self, data, sock_info, *args):
        return data

    def on__connection_close(self, sock_info, sending_tail, message_queues, *args):
        """
        Call on connection close in client-proxy or proxy-server connection.

        @sock_info - PublicSocketInfo object.
        @sending_tail - pail last sending message or None if last message full send.
        @message_queues - queues object, contain no send messages queue.
        """

    def on__start_event_loop(self, *args):
        """
        Call on each proxy select iteration.
        """
