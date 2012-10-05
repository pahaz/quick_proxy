import socket

__author__ = 'pahaz'

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

def get_sock_settings(HOST, PORT):
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

    raise Exception('could not resolve hostname')
