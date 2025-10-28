
# ROIO目录结构



```javascript
ROIO
├── roio_proto.py           # ROIO协议和消息定义
├── roio_client.py          # ROIOClient类的实现， __main__方法实现了从stdin获取输入消息后publish出去的功能
├── roio_echo_client.py     # 实现了被publish到的消息的原样echo回去的ROIO Client实现样例
├── roio_pub_meter.py       # 以1000byte包大小，目标200Hz的频率publish的性能测试工具
├── roio_sub_meter.py       # 跑在roio_pub_meter.py对端接收和统计包数量的工具，pub_meter发送的数量跟sub_meter应该对上
├── roio_agent_mock.py      # 一个模拟ROIO Agent的类，用于测试ROIOClient， 纯本地模拟ROIO Agent收到pub消息后，发给订阅者，这里没有通过RoDN的传递消息的过程
├── Logger.py               # 日志功能依赖
├── __init__.py
└── UdpSocket.py            # UDP socket功能依赖
```


# 概述

ROIOClient是一个面向实时通信场景设计的客户端类，主要用于与ROIO Agent建立UDP通信，对ROIO channel进行subscribe/unsubscribe，定期subscription的自动心跳保活， 并对接收到的publish消息，按用户定义的回调函数进行处理。适用于需要点对点实时交互的应用场景（如即时通讯、监控数据上报、机器人控制，游戏客户端等）。


下图展示了一个方向publish消息到另外一个方向的过程，只要通信双方约定好通道号(channelId)， 就能够实现相互发送消息，比如把从RCA到Robot方向的控制消息放到channelId==1, 把反方向的状态回报放到channel==2

或者按channelId区分控制的关节等。

```mermaidjs
sequenceDiagram
  participant A as ROIO-Client1<br>(Cust Controller)
  participant B as ROIO-Agent1<br>(RCA)
  participant C as ROIO-Agent2<br>(RoBOX)
  participant D as ROIO-Client2<br>(Cust Robot Control Unit)
  autonumber
  B --> C: IF3 establish remote tunnel
  D -->> C: Subscribe to channel 0
  C -->> D: Subscribe Success
  A -->> B: publish to channel 0: [bytes]
  B -->> A: publish ack
  B -->> C: IF3 PUB channel 0: [bytes]
  C -->> D: publish channel 0: [bytes]
  D -->> C: publish ack
  
  
```

# 初始化ROIOClient


```python
class RoIOClient(Thread):
    def __init__(self,
                 target: Tuple[str, int] = (os.getenv('ROIO_HOST', '127.0.0.1'), int(os.getenv('ROIO_PORT', '3333'))),
                 cb: Optional[Callable[[RoIOMsg], None]] = None,
                 max_queue_size: int = 5,  # 可配置的队列容量
                 udp_timeout: int = 1,  # 一般ROIO Client和Agent在局域网内, 响应时间一般不会超过1秒, 所以设置timeout为1秒
                 pub_no_ack = False
                 ):
                 ...
 
     def set_callback(self, cb:Optional[Callable[[RoIOMsg], None]]):
        """用于对象生成之后设置消息处理回调方法, 同__init__的cb参数的作用"""
        self.msg_process_cb = cb
            
```

## ROIO相关环境变量

| 环境变量名 | 含义 | 默认值 |
|----|----|----|
| ROIO_HOST | ROIOClient连接的ROIO-Agent的Hostname或者IP地址 | 127.0.0.1 |
| ROIO_PORT | ROIOClient连接的ROIO-Agent的端口号 | 3333 |
| CH_ID | meter测试和echo测试用的channel号，收发两端要一致才能通信成功用户自己实现的ROIO-Client不需要依赖这个环境变量，可以自行选择0-255之间的通道号 | 0 |

## 样例：处理消息回调函数


```python
    # 例子详细实现见roio_echo_client.py
    echo_roio_client = ROIOClient()

    def echo_func(msg):
        """"定义把消息原样发回去的行为"""
        logger.info(f"ECHO: {msg}")
        # msg.channel_id  # PUBLISH消息的通道ID
        # msg.body        # 消息携带的字节流 
        echo_roio_client.publish_to_channel(msg.channel_id, msg.body)
    # 指定处理消息的方式为echo_func
    echo_roio_client.set_callback(echo_func) #override the callback function upon published
    
    # 启动roio_client线程
    echo_roio_client.start()
    
    CHANNEL_ID=0x00
    echo_roio_client.subscribe_to_channel(CHANNEL_ID)
    echo_roio_client.publish_to_channel(CHANNEL_ID, b"Hello World")

```


# Subscribe/Unsubscribe到通道

ROIO支持0-255 256个通道，

```python
#roio_proto.py
CHANNEL_RANGE=range(0x00, 0x100)   # 0-255
```

调用该方法后，本端ROIO Agent收到远端发来的对应Channel的消息后，会PUBLISH给Subsribed的ROIO Client

```python
class RoIOClient(Thread):
...
    def subscribe_to_channel(self, 
                              channel_id,    # 0-255, 不在范围内会raise Exception
                              unsubscribe=False):   # 默认是False表示subscribe，如果是True表示unsubscribe
        ...
```


# Publish字节流到指定通道


调用该方法后，SDK会把消息PUBLISH给本端ROIO Agent, ROIO Agent负责发送给远端ROIO Agent， ROIO Agent再PUBLISH给subscribe在对应ChannelID上的远端ROIO Client


```python
 class RoIOClient(Thread):
...
    def publish_to_channel(self, 
    channel_id, 
    bs   #字节流，不要超过MTU-20, 一般最大大约是1400 BYTES上下
    ):
...
```


# start/stop RoIOClient对象

RoIOClient内部有3个线程，

* roio-msgloop线程负责udp socket消息的收发，
* roio-keepalive线程负责定期保活已有的subscribption
* roio-processor线程负责收到PUBLISH的消息调用用户注册的回调方法处理

需要通过start/stop函数来启动/停止所有线程， 注意停止后不能重新start，需要重新初始化一个ROIOClient对象再start


