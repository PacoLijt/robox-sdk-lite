# Project Structure

```javascript
robox-sdk-lite
├── roio_proto.py           # RoIO protocol and message definitions
├── roio_client.py          # Implementation of the RoIOClient class. The __main__ method implements functionality to get input messages from stdin and publish them
├── roio_echo_client.py     # Sample implementation of an RoIO Client that echoes back received messages
├── roio_pub_meter.py       # Performance testing tool that publishes packets at 1000 bytes size with a target frequency of 200Hz
├── roio_sub_meter.py       # Tool running on the receiving end of roio_pub_meter to receive and count packets. The number sent by pub_meter should match what sub_meter receives
├── roio_agent_mock.py      # A mock RoIO Agent class for testing RoIOClient. This simulates locally how the RoIO Agent receives pub messages and forwards them to subscribers without going through RoDN message transmission process
├── Logger.py               # Logging functionality dependency
├── __init__.py
└── UdpSocket.py            # UDP socket functionality dependency
```

# Overview

`RoIOClient` is a client class designed for real-time communication scenarios, mainly used to establish UDP communication with RoIO Agent, subscribe/unsubscribe to RoIO channels, automatically maintain periodic subscription heartbeat, and process received publish messages according to user-defined callback functions. It's suitable for application scenarios requiring point-to-point real-time interaction (such as instant messaging, monitoring data reporting, robot control, game clients, etc.).

The diagram below shows the process of publishing a message from one direction to another. As long as both communicating parties agree on the channel ID, they can send messages to each other. For example, control messages from RCA to Robot can be placed in channelId==1, while status feedback in the opposite direction can be put in channel==2.

Alternatively, channels can be distinguished by channelId to control different joints.

```mermaidjs
sequenceDiagram
  participant A as RoIO-Client1<br>(Cust Controller)
  participant B as RoIO-Agent1<br>(RCA)
  participant C as RoIO-Agent2<br>(RoBOX)
  participant D as RoIO-Client2<br>(Cust Robot Control Unit)
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

# Initializing RoIOClient

```python
class RoIOClient(Thread):
    def __init__(self,
                 target: Tuple[str, int] = (os.getenv('RoIO_HOST', '127.0.0.1'), int(os.getenv('RoIO_PORT', '3333'))),
                 cb: Optional[Callable[[RoIOMsg], None]] = None,
                 max_queue_size: int = 5,  # Configurable queue capacity
                 udp_timeout: int = 1,  # Generally, RoIO Client and Agent are within LAN where response time typically doesn't exceed 1 second, so timeout is set to 1 second
                 pub_no_ack = False
                 ):
                 ...
 
     def set_callback(self, cb:Optional[Callable[[RoIOMsg], None]]):
        """Used to set the message processing callback method after object creation, same function as the cb parameter in __init__"""
        self.msg_process_cb = cb
```

## RoIO Related Environment Variables

| Environment Variable | Meaning | Default Value |
|----|----|----|
| RoIO_HOST | Hostname or IP address of the RoIO-Agent that RoIOClient connects to | 127.0.0.1 |
| RoIO_PORT | Port number of the RoIO-Agent that RoIOClient connects to | 3333 |
| CH_ID | Channel number used for meter testing and echo testing. Both sending and receiving ends must have consistent values to communicate successfully. User-implemented RoIO-Clients don't need to rely on this environment variable and can choose any channel ID between 0-255 | 0 |

## Example: Message Handling Callback Function

```python
    # Detailed implementation example can be found in roio_echo_client.py
    echo_roio_client = RoIOClient()

    def echo_func(msg):
        """"Define behavior to send the message back as-is"""
        logger.info(f"ECHO: {msg}")
        # msg.channel_id  # Channel ID of the PUBLISH message
        # msg.body        # Byte stream carried by the message 
        echo_roio_client.publish_to_channel(msg.channel_id, msg.body)
    # Specify message handling method as echo_func
    echo_roio_client.set_callback(echo_func) #override the callback function upon published
    
    # Start the roio_client thread
    echo_roio_client.start()
    
    CHANNEL_ID=0x00
    echo_roio_client.subscribe_to_channel(CHANNEL_ID)
    echo_roio_client.publish_to_channel(CHANNEL_ID, b"Hello World")
```

# Subscribe/Unsubscribe to Channels

RoIO supports 256 channels from 0-255:

```python
#roio_proto.py
CHANNEL_RANGE=range(0x00, 0x100)   # 0-255
```

After calling this method, when the local RoIO Agent receives messages from the remote side for the corresponding Channel, it will PUBLISH them to the subscribed RoIO Client:

```python
class RoIOClient(Thread):
...
    def subscribe_to_channel(self, 
                              channel_id,    # 0-255, out-of-range values will raise Exception
                              unsubscribe=False):   # Defaults to False for subscribe, True for unsubscribe
        ...
```

# Publish Byte Stream to Specified Channel

After calling this method, the SDK will PUBLISH the message to the local RoIO Agent, which is responsible for sending it to the remote RoIO Agent. The remote RoIO Agent then PUBLISHes it to the remote RoIO Client subscribed to the corresponding ChannelID:

```python
 class RoIOClient(Thread):
...
    def publish_to_channel(self, 
    channel_id, 
    bs   #Byte stream, shouldn't exceed MTU-20, generally maximum around 1400 BYTES
    ):
...
```

# Starting/Stopping RoIOClient Object

RoIOClient has 3 internal threads:
* roio-msgloop thread handles UDP socket message sending/receiving
* roio-keepalive thread periodically maintains existing subscriptions
* roio-processor thread processes received PUBLISH messages by calling user-registered callback methods

All threads need to be started/stopped through start/stop functions. Note that once stopped, it cannot be restarted - you need to reinitialize a new RoIOClient object and then start it.
