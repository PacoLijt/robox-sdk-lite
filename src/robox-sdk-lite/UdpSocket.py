#!/usr/bin/env python3

import socket
MAX_BUFFER = 1440


class UdpSocket:
    def __init__(self, l_addr=None, timeout=1.5):
        self.l_addr = l_addr
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.l_addr:
            self.socket.bind(self.l_addr)
        self.socket.settimeout(timeout)

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def sendto(self, bs, r_addr):
        return self.socket.sendto(bs, r_addr)

    def recvfrom(self, size=MAX_BUFFER):
        return self.socket.recvfrom(size)

    def send_and_recv(self, bs, r_addr, recv_size=MAX_BUFFER):
        self.sendto(bs, r_addr)
        return self.recvfrom(size=recv_size)
