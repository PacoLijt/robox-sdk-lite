#!/usr/bin/env python3
from enum import Enum, unique
import random
import time
import struct

CHANNEL_RANGE=range(0x00, 0x100)

@unique
class MSG_TYPE(Enum):
    SUBSCRIBE = 201
    PUBLISH = 202
    UNSUBSCRIBE = 203
    GONE = 204  # 通知SUBSCRIBER AGENT退出了
    UNDEF = 255


class GenericBody:
    def pack(self):
        pass

    @staticmethod
    def unpack(bs):
        pass

    def __repr__(self):
        return str(self.__dict__)

class SubscribeBody(GenericBody):
    def __init__(self, host=None, port=0):
        self.host = host
        self.port = port
    
    def pack(self):
        return f"{self.host}:{self.port}".encode('ascii')

    @staticmethod
    def unpack(bs):
        if bs:
            try:
                host, port = bs.decode('ascii').split(':')
                return SubscribeBody(host, int(port))
            except Exception as e:
                print(e)
                return None


@unique
class RESULT(Enum):
    SUCCESS = 0
    FAILED = 1
    INVALID_ACCESS = 2
    NOT_SUPPORTED_REQ = 3
    ACK = 4

class RoIOMsg:
    HEADER_LEN = 20
    HEADER_PATTERN_PREFIX = ">IBBq"  # req: +6 bytes of access code; res: +1 byte result code + 5-byte RESPONSE_HEADER_TAIL
    HEADER_TAIL_LEN = 6
    RESPONSE_HEADER_TAIL = b'\x00\x00\x00##'
    REQUEST_HEADER_TAIL = b'\x00'*6


    MSG_BODY_TABLE = {
        MSG_TYPE.SUBSCRIBE: (SubscribeBody, None),
        MSG_TYPE.PUBLISH: (None, None),
        MSG_TYPE.UNSUBSCRIBE: (None, None),
        MSG_TYPE.GONE: (None, None),
    }

    tidCounter = random.randint(1000000, 9999999)
    @staticmethod
    def next_tid():
        if RoIOMsg.tidCounter >= 0xffffffff:
            RoIOMsg.tidCounter = 0
        tid = RoIOMsg.tidCounter
        RoIOMsg.tidCounter += 1
        return tid

    def __init__(self):
        self.transaction_id = 0
        self.msg_type = MSG_TYPE.UNDEF
        self.channel_id= 0
        self.is_req = True
        self.ts = 0
        self.result_code = RESULT.SUCCESS
        self.body = None

    def update_ts(self):
        self.ts = int(time.time())

    def update_tid(self):
        self.transaction_id = self.next_tid()

    def pack(self):
        bs = struct.pack(RoIOMsg.HEADER_PATTERN_PREFIX, self.transaction_id, self.msg_type.value,
                         self.channel_id, self.ts)
        if self.is_req:
            bs += RoIOMsg.REQUEST_HEADER_TAIL
        else:
            bs += struct.pack(">B", self.result_code.value)
            bs += RoIOMsg.RESPONSE_HEADER_TAIL
        if self.body is not None:
            if isinstance(self.body, bytes):
                bs += self.body
            elif  isinstance(self.body, GenericBody):
                bs += self.body.pack()
            else:
                raise Exception("body type error")
        return bs

    def parse_body(self):
        if isinstance(self.body, bytes):
            body_klass = self.find_body_klass()
            if body_klass is not None:
                obj = body_klass.unpack(self.body)
                if obj is not None:
                    self.body = obj

    def find_body_klass(self):
            return RoIOMsg.MSG_BODY_TABLE.get(self.msg_type, (None, None))[0 if self.is_req else 1]

    @staticmethod
    def unpack(bs):
        if len(bs) < RoIOMsg.HEADER_LEN:
            return None
        msg = RoIOMsg()
        (msg.transaction_id, msg.msg_type, msg.channel_id, msg.ts) = struct.unpack(RoIOMsg.HEADER_PATTERN_PREFIX,
                                                                                   bs[
                                                                                   0:RoIOMsg.HEADER_LEN - RoIOMsg.HEADER_TAIL_LEN])
        if bs[RoIOMsg.HEADER_LEN - RoIOMsg.HEADER_TAIL_LEN + 1:RoIOMsg.HEADER_LEN] == RoIOMsg.RESPONSE_HEADER_TAIL:
            msg.is_req = False
            msg.result_code, = struct.unpack(">B",
                                             bs[
                                             RoIOMsg.HEADER_LEN - RoIOMsg.HEADER_TAIL_LEN:RoIOMsg.HEADER_LEN - RoIOMsg.HEADER_TAIL_LEN + 1])
            msg.result_code = RESULT(msg.result_code)
        else:
            msg.is_req = True

        try:
            msg.msg_type = MSG_TYPE(msg.msg_type)
        except Exception as e:
            print(f"Invalid MSG_TYPE value={msg.msg_type},{e}")
            return None
        # if only the result code is success parse the body
        if msg.result_code == RESULT.SUCCESS:
            msg.body = bs[RoIOMsg.HEADER_LEN:]
            if len(msg.body) < 1:
                msg.body = None
            else:
                msg.parse_body()
        return msg

    def __repr__(self):
        if self.is_req:
            return "RequestMsg: tid={},msg_type={},channel_id={},ts={},body={}".format(
                self.transaction_id, self.msg_type, self.channel_id, self.ts, self.body)
        else:
            return "ResponseMsg: tid={},msg_type={},channel_id={},ts={},result_code={},body={}".format(
                self.transaction_id, self.msg_type, self.channel_id, self.ts, self.result_code, self.body)


if __name__ == '__main__':
    msg = RoIOMsg()
    msg.update_tid()
    msg.update_ts()
    msg.msg_type = MSG_TYPE.SUBSCRIBE
    msg.channel_id = 0x0f
    msg.body = SubscribeBody(host="192.168.1.1", port=13435)
    print(msg.body)
    print(msg)
    print(msg.pack())
    msg.msg_type = MSG_TYPE.PUBLISH
    msg.body = "hello world".encode("ascii")
    print(msg)
    print(msg.pack())
