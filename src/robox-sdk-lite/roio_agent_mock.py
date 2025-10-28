#!/usr/bin/env python3
import os, sys
from Logger import *
from UdpSocket import UdpSocket
from roio_proto import *
from threading import Thread, Event
import socket

class Subscription:
    def __init__(self, r_addr, channel_id):
        self.r_addr = r_addr
        self.channel_id = channel_id
        self.last_act_ts = time.time()

    def __repr__(self):
        return f"Subscription(r_addr={self.r_addr}, channel_id={self.channel_id})"

    def check_valid(self, timeout=60):
        return time.time() - self.last_act_ts < timeout

    def update_ts(self):
        self.last_act_ts = time.time()

class RoIOAgentService(Thread):
    def __init__(self, local_addr=(os.getenv('ROIO_HOST', '0.0.0.0'), int(os.getenv('ROIO_PORT', '3333')))):
        super().__init__(name="roio", daemon=False)
        self.udp = UdpSocket(l_addr=local_addr, timeout=0.2)
        self.subscriptions = tuple({} for i in range(256)) # 初始化256个channelId的订阅
        #回调函数,执行上层ROIO-Tunnel转发给对端的Subscription
        self.on_recv_publish_cb = None 
        self.running_event = Event()

    def run(self):
        self.running_event.set()
        logger.info(f"roio started at {self.udp.socket.getsockname()}")
        while self.running_event.is_set():
            try:
                self.msg_loop()
            except socket.timeout:
                    continue
        logger.info(f"roio stopped")

    def say_goodbye(self):
        msg = RoIOMsg()
        msg.msg_type = MSG_TYPE.GONE
        msg.is_req = True
        msg.update_tid()
        msg.update_ts()
        bs = msg.pack()
        for subs in self.subscriptions:
            for k in list(subs.keys()):
                self.udp.sendto(bs, k)

    def stop(self):
        logger.info("stopping roio")
        self.running_event.clear()
        self.join(timeout=1)
        self.say_goodbye() # 发送GONE, 告诉对端agent断开
        self.udp.close()

    def respondto(self, r_addr, request:RoIOMsg, result_code:RESULT, body:GenericBody = None, need_encrypted = True):
        resp = RoIOMsg()
        resp.is_req = False
        resp.transaction_id = request.transaction_id
        resp.msg_type = request.msg_type
        resp.channel_id = request.channel_id
        resp.result_code = result_code
        resp.update_ts()
        resp.body = body
        bs = resp.pack()
        logger.debug(f"{r_addr}<---{resp}")
        return self.udp.sendto(bs, r_addr)

    def publish_to_channel(self, channel_id, bs, src_addr=None):
        if not (0<=channel_id<256):
            raise ValueError(f"Invalid channel_id: {channel_id}")
        subs = self.subscriptions[channel_id]
        logger.debug(f"Publishing to channel {channel_id} with {subs} subscribers")
        self.check_subscriptions(subs)
        if len(subs)<=0:
            return 0

        msg = RoIOMsg()
        msg.update_tid()
        msg.update_ts()
        msg.msg_type = MSG_TYPE.PUBLISH
        msg.channel_id = channel_id
        msg.body = bs
        bs2send = msg.pack()
        for r_addr in subs.keys():
            if src_addr == r_addr:
                # 跳过来源地址
                continue 
            try:
                logger.debug(f"publish to {r_addr}: {msg}")
                self.udp.sendto(bs2send, r_addr)
            except Exception as e:
                logger.warning(f"send to {r_addr} encounter exception {e}")

    def full_subscriptions_check(self):
        for subs in self.subscriptions:
            self.check_subscriptions(subs)

    def check_subscriptions(self, subscriptions):
        for k in list(subscriptions.keys()):
            sub = subscriptions[k]
            if not sub.check_valid():
                logger.info(f"discard timeout subscription: {sub}")
                subscriptions.pop(k)

    def msg_loop(self):
        bs, r_addr = self.udp.recvfrom()
        if bs is None:
            return
        is_encrypted = False
        logger.debug(f"recv raw_bs: {r_addr}>>{bs}")
        msg = RoIOMsg.unpack(bs)
        if msg is None:
            logger.warning(f"received invalid data to parse to msg: {bs}")
            return
        logger.debug(f"{r_addr}>>{msg}")
        if not (0 <= msg.channel_id < 256):
            self.respondto(r_addr, msg, RESULT.NOT_SUPPORTED_REQ)

        if msg.msg_type == MSG_TYPE.SUBSCRIBE or msg.msg_type == MSG_TYPE.UNSUBSCRIBE:
            if not msg.is_req:
                logger.warning(f"unexpected response: {msg}")
                return  # ignore respons
            sub_addr = r_addr
            if msg.body is not None:
                sub_addr = (msg.body.host, msg.body.port)

            subscription = self.subscriptions[msg.channel_id].get(sub_addr)
            if msg.msg_type == MSG_TYPE.UNSUBSCRIBE:
                # 删除订阅
                if subscription is not None:
                    self.subscriptions[msg.channel_id].pop(sub_addr)
                self.respondto(r_addr, msg, RESULT.SUCCESS, need_encrypted=is_encrypted)
            else:
                # 订阅
                if subscription is None:
                    self.subscriptions[msg.channel_id][sub_addr] = Subscription(r_addr=sub_addr, channel_id=msg.channel_id)
                else:
                    subscription.update_ts()
                logger.debug(f"Subscribed to channel {msg.channel_id} from {sub_addr}")
                self.respondto(r_addr, msg, RESULT.SUCCESS)
        elif msg.msg_type == MSG_TYPE.PUBLISH:
            if msg.is_req:
                if msg.body is not None:
                    if self.on_recv_publish_cb:
                        if self.on_recv_publish_cb(r_addr, msg.channel_id, msg.body):
                            self.respondto(r_addr, msg, RESULT.ACK, need_encrypted=is_encrypted)
                        else:
                            self.respondto(r_addr, msg, RESULT.FAILED, need_encrypted=is_encrypted)
                    else:
                        self.respondto(r_addr, msg, RESULT.NOT_SUPPORT, need_encrypted=is_encrypted)
            else:
                # Publish Ack的处理
                if msg.result_code == RESULT.ACK:
                    sub = self.subscriptions[msg.channel_id].get(r_addr)
                    if sub: sub.update_ts()
                else:
                    logger.warning(f"unexpected message type: {msg}")
                    pass
        else:
            self.respondto(r_addr, msg, RESULT.NOT_SUPPORTED_REQ, need_encrypted=is_encrypted)
            
            
if __name__=='__main__':
    if '-d' in sys.argv:
        logger.setLevel(logging.DEBUG)
        sys.argv.remove('-d')

    roio = RoIOAgentService()
    def on_publish(r_addr, channel_id, bs):
        # 回调方法，用于测试在本地环回发布消息
        # 正常来说收到本地publish消息应该是发给远端Agent端的，
        # 但是这里演示本agent内的传递
        logger.debug(f"publish: {bs} to {channel_id}")
        roio.publish_to_channel(channel_id, bs, src_addr=r_addr)
        return True
    roio.on_recv_publish_cb = on_publish
    roio.start()
    while True:
        try:
            time.sleep(1)
            if not roio.is_alive():
                break
            roio.full_subscriptions_check()
        except KeyboardInterrupt:
            break
    roio.stop()
    
