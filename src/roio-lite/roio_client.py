#!/usr/bin/env python3
import os, sys
from Logger import *
from UdpSocket import UdpSocket
from roio_proto import *
from threading import Thread, RLock, Event
import socket
import queue
from typing import Optional, Tuple, Set, Callable, Any


class RoIOClient(Thread):
    def __init__(self,
                 target: Tuple[str, int] = (os.getenv('ROIO_HOST', '127.0.0.1'), int(os.getenv('ROIO_PORT', '3333'))),
                 cb: Optional[Callable[[RoIOMsg], None]] = None,
                 max_queue_size: int = 5,  # 可配置的队列容量
                 udp_timeout: int = 1,  # 一般ROIO Client和Agent在局域网内, 响应时间一般不会超过1秒, 所以设置timeout为1秒
                 pub_no_ack = False
                 ):
        super().__init__(name='roio-msgloop', daemon=False)
        self.udp = UdpSocket(l_addr=None, timeout=udp_timeout)
        self.target = target

        self.agent_gone = False  #可以根据这个, 决定发送Subscribe消息频度, agent还在, 就间隔30s发一次, agent退出过, 就需要每隔1s发

        self.q_resp = queue.Queue(max_queue_size)  # 用于接收响应
        self.q = queue.Queue(max_queue_size) # 接收发布到本节点的消息

        self.lock = RLock()
        self.running_event = Event()
        self.keepalive_event = Event()
        self.processor_event = Event()

        self.sub_channels = set() #记住订阅了的channel
        self.t_keepalive = Thread(name="roio-keepalive", target=self.__keepalive, daemon=False)

        # 如果传入了处理被publish消息回调方法就用用户指定的，否则用默认方法只打印
        self.msg_process_cb = cb if cb else self.print_msg_func
        self.t_process = Thread(name="roio-processor", target=self.__process_queue, daemon=False)

        self.pub_no_ack = pub_no_ack

    def set_callback(self, cb:Optional[Callable[[RoIOMsg], None]]):
        """用于对象生成之后设置消息处理回调方法"""
        self.msg_process_cb = cb

    def print_msg_func(self, msg:RoIOMsg):
        # 处理被publish到的消息,可以被override成用户想要的动作
        logger.info(f"print recv msg: channel_id={msg.channel_id}: body={msg.body.decode('utf8')}")

    def __keepalive(self):
        self.keepalive_event.set()
        ts = time.time()
        logger.info("enter")
        while self.keepalive_event.is_set():
            now = time.time()
            if (self.agent_gone and now - ts>=1) or (not self.agent_gone and now - ts >=30):
                ts = now
                for ch in list(self.sub_channels):
                    if ch in self.sub_channels:
                        self.subscribe_to_channel(ch)
            time.sleep(0.1)
        logger.info("quit")

    def __process_queue(self):
        # 多线程中调用处理消息
        self.processor_event.set()
        logger.info("enter")
        while self.processor_event.is_set():
            try:
                msg = self.q.get(timeout=0.1)
                self.msg_process_cb(msg)
            except queue.Empty:
                continue 
        logger.info("quit")
        
    def run(self):
        logger.info("enter")
        self.t_keepalive.start()
        self.t_process.start()
        self.running_event.set()

        while self.running_event.is_set():
            try:
                self._msg_loop()
            except socket.timeout:
                pass

        logger.info("quit")

    def _msg_loop(self):
        bs, r_addr = self.udp.recvfrom()
        if bs is None:
            return
        logger.debug(f"{r_addr}>>{bs}")

        msg = RoIOMsg.unpack(bs)
        if msg is None:
            logger.warning(f"received invalid data to parse to msg: {bs}")
            return

        logger.debug(f"recv_msg: {msg}")
        if not msg.is_req:
            # 如果是响应消息,放入队列，给主线程处理
            if self.pub_no_ack and msg.msg_type == MSG_TYPE.PUBLISH:
                # drop PUB ACK
                return
            logger.debug(f"enque resp: {r_addr}: {msg}")
            while True:
                try:
                    self.q_resp.put_nowait((msg, r_addr))
                    break
                except queue.Full:
                    m_discard = self.q_resp.get_nowait()
                    logger.warning(f"resp queue is full, discard oldest msg: {m_discard}")
        else:
            if msg.msg_type == MSG_TYPE.PUBLISH:
                #logger.info(f"recv {r_addr}>>{msg}")
                while True:
                    try:
                        self.q.put_nowait(msg) # 放入队列,给主线程处理
                        break
                    except queue.Full:
                        m_discard = self.q.get_nowait()
                        logger.warning(f"msg queue is full, discard oldest msg: {m_discard}")
                self.respondto(r_addr, msg, RESULT.ACK)
            elif msg.msg_type == MSG_TYPE.GONE:
                # agent退出通知
                logger.warning("ROIO Agent is GONE")
                self.agent_gone = True
            else:
                logger.warning(f"Unexpected msg: {r_addr}>>{msg}")

    def stop(self):
        logger.info("ROIO client stopping")
        # 先停止keepalive线程
        self.keepalive_event.clear()
        self.t_keepalive.join(timeout=1)
        # unsubscribe所有订阅的channel
        for ch in list(self.sub_channels):
            self.subscribe_to_channel(ch, unsubscribe=True)
        self.sub_channels.clear()

        # 停止消息处理线程
        self.processor_event.clear()
        self.t_process.join(timeout=1)

        # 停止收消息线程
        self.running_event.clear()
        self.join(timeout=2)
        self.udp.close()

    def subscribe_to_channel(self, channel_id, unsubscribe=False):
        if channel_id not in CHANNEL_RANGE:
            raise Exception("subscribe failed, channel_id out of range [0, 255]")
        with self.lock:
            msg = RoIOMsg()
            msg.msg_type = MSG_TYPE.SUBSCRIBE if not unsubscribe else MSG_TYPE.UNSUBSCRIBE
            oper = "subscribe" if not unsubscribe else "unsubscribe"
            msg.channel_id = channel_id
            msg.update_tid()
            msg.update_ts()
            logger.debug(f"{self.target}<<<{msg}")
            bs = msg.pack()
            self.udp.sendto(bs, self.target)

            if unsubscribe:
                self.sub_channels.remove(channel_id)  #移除订阅的channel
            else:
                self.sub_channels.add(channel_id) # 记住订阅了的channel

            for i in range(2):
                try:
                    rsp, r_addr = self.q_resp.get(timeout=0.5)
                    if msg.transaction_id == rsp.transaction_id and msg.msg_type == rsp.msg_type and msg.channel_id == rsp.channel_id:
                        res = rsp.result_code == RESULT.SUCCESS
                        if not res:
                            logger.info(f"{oper} to channel {channel_id} failed")
                            self.agent_gone = True
                        else:
                            logger.info(f"{oper} to channel {channel_id} ok")
                        self.agent_gone = False
                        return res
                except KeyboardInterrupt:
                    break
                except queue.Empty:
                    #logger.debug(f"wait for response: {i}")
                    pass
            logger.info(f"{oper} to channel {channel_id} timeout")
            self.agent_gone = True #subscribe失败, 认为agent已经退出
            return False
        
    def publish_to_channel(self, channel_id, bs):
        if channel_id not in CHANNEL_RANGE:
            raise Exception("publish failed, channel_id out of range [0, 255]")
        with self.lock:
            msg = RoIOMsg()
            msg.msg_type = MSG_TYPE.PUBLISH
            msg.channel_id = channel_id
            msg.body = bs
            msg.update_tid()
            msg.update_ts()
            logger.debug(f"{self.target}<<<{msg}")

            bs = msg.pack()
            self.udp.sendto(bs, self.target)

            if self.pub_no_ack:
                return True
            else:
                for i in range(2):
                    try:
                        rsp, r_addr = self.q_resp.get(timeout=0.5)
                        if msg.transaction_id == rsp.transaction_id and msg.msg_type == rsp.msg_type and msg.channel_id == rsp.channel_id:
                            logger.debug(f"{r_addr}>>>{rsp}")
                            return rsp.result_code == RESULT.ACK
                        else:
                            logger.warning(f"{r_addr}>>>{rsp}, unmatch request: {msg}")
                    except queue.Empty:
                        logger.debug(f"wait for response: {i}")
                        pass
                return False
    
    def respondto(self, r_addr, request:RoIOMsg, result_code:RESULT, body:GenericBody = None):
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
        self.udp.sendto(bs, self.target)
        return self.udp.sendto(bs, r_addr)

    
if __name__ == "__main__":
    if '-d' in sys.argv:
        logger.setLevel(logging.DEBUG)
        sys.argv.remove('-d')

    r_addr = None
    for a in sys.argv[1:]:
        v = a.split(":")
        if len(v)==2:
            r_addr = (v[0], int(v[1]))

    roio_client = RoIOClient(target=r_addr) if r_addr else RoIOClient()
    roio_client.start()

    CHANNEL_ID=int(os.getenv("CH_ID", "0"))

    # 测试unsubscribe
    #roio.subscribe_to_channel(CHANNEL_ID)
    #roio.subscribe_to_channel(CHANNEL_ID, unsubscribe=True)
    #try:
    #    time.sleep(1)
    #except:
    #    pass
    roio_client.subscribe_to_channel(CHANNEL_ID)

    try:
        while True:
            # 主线程获取用户输入用于发布
            user_input = input("Enter message to publish (or 'exit' to quit): \n")
            if len(user_input) < 1:
                continue
            if user_input.lower() == 'exit':
                break
            bs = user_input.encode("utf8")
            roio_client.publish_to_channel(CHANNEL_ID, bs)
    except KeyboardInterrupt:
        pass
    finally:
        roio_client.stop()
        print("Exiting...")
