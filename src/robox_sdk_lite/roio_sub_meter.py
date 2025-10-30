#!/usr/bin/env python3
import os, sys
from Logger import *
from roio_proto import *
from roio_client import RoIOClient
from threading import Thread, Lock


CHANNEL_ID=int(os.getenv("CH_ID", "0"))

if __name__ == "__main__":
    if '-d' in sys.argv:
        logger.setLevel(logging.DEBUG)
        sys.argv.remove('-d')

    r_addr = None
    for a in sys.argv[1:]:
        v = a.split(":")
        if len(v)==2:
            r_addr = (v[0], int(v[1]))

    if r_addr is not None:
        roio_client = RoIOClient(target=r_addr, pub_no_ack=False)
    else:
        roio_client = RoIOClient(pub_no_ack=False)

    
    COUNT=100
    counter_r = 0
    ts_r = time.time()
    ts0 = ts_r
    def recv_func(msg):
        """"计数"""
        global counter_r, ts_r, ts0

        if counter_r == 0:
            # 从收到第一个开始计时
            ts_r = time.time()
            ts0 = ts_r

        counter_r += 1
        if counter_r%COUNT == 0:
            now = time.time()
            td = now - ts_r
            tt = now - ts0
            ts_r = now
            logger.info(f"rcv: {int(COUNT/td)}Hz, avg: {int(counter_r/tt)}Hz, total_rcv: {counter_r}")

    roio_client.set_callback(recv_func) #override the callback function upon published

    roio_client.start()
    roio_client.subscribe_to_channel(CHANNEL_ID)

    try:
        ts_s = time.time()
        counter_s = 0
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        roio_client.stop()
        print("Exiting...")
