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

    Xtreme = False
    if '-x' in sys.argv:
        sys.argv.remove('-x')
        Xtreme = True

    print(f"Xtreme: {Xtreme}")


    r_addr = None
    for a in sys.argv[1:]:
        v = a.split(":")
        if len(v)==2:
            r_addr = (v[0], int(v[1]))

    if r_addr is not None:
        roio_client = RoIOClient(target=r_addr, pub_no_ack=False)
    else:
        roio_client = RoIOClient(pub_no_ack=False)

    

    roio_client.start()

    PACKET_SIZE=1000
    HZ=200
    sleep_interval = 0.95/HZ

    try:
        counter_s = 0
        COUNT=100
        bs2send = b'A'*PACKET_SIZE
        ts_s = time.time()
        ts0 = ts_s
        while True:
            ts = time.time()

            roio_client.publish_to_channel(CHANNEL_ID, bs2send)

            counter_s += 1
            if counter_s%COUNT==0:
                now = time.time()
                td = now - ts_s # 当前统计窗口的耗时
                tt = now - ts0  # 一开始到现在的耗时
                ts_s = now
                logger.info(f"pkt_sz:{PACKET_SIZE}, current:{int(COUNT/td)}Hz, avg:{int(counter_s/tt)}Hz, tot_pub: {counter_s}")

            if Xtreme:
                # 最大压力模式
                continue 
            else:
                # 计算需要休息的时长，以接近预订的HZ
                d = sleep_interval + ts - time.time()
                if d>0:
                    time.sleep(d)

            
    except KeyboardInterrupt:
        pass
    finally:
        roio_client.stop()
        print("Exiting...")
