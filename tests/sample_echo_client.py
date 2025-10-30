#!/usr/bin/env python3
import os, sys
from robox_sdk_lite.Logger import *
from robox_sdk_lite.roio_proto import *
from robox_sdk_lite.roio_client import RoIOClient
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
        echo_client = RoIOClient(target=r_addr)
    else:
        echo_client = RoIOClient()

    def echo_func(msg):
        """"定义把消息原样发回去的行为"""
        logger.info(f"ECHO: {msg}")
        # time.sleep(1)  # 延迟一会儿再echo
        echo_client.publish_to_channel(msg.channel_id, msg.body)
    # 指定处理消息的方式为echo_func
    echo_client.set_callback(echo_func) #override the callback function upon published

    echo_client.start()

    echo_client.subscribe_to_channel(CHANNEL_ID)
    #echo_roio_client.publish_to_channel(CHANNEL_ID, b"Hello World")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        echo_client.stop()
        print("Exiting...")
