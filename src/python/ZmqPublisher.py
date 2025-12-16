###############################################################################
# Copyright 2016-2022 SRI International.  All rights reserved.
#
# The material contained in this file is confidential and proprietary to SRI
# International and may not be reproduced, published, or disclosed to others
# without authorization from SRI International.
#
# DISCLAIMER OF WARRANTIES
#
# SRI International MAKES NO REPRESENTATIONS OR WARRANTIES ABOUT THE
# SUITABILITY OF THE SOFTWARE, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT
# LIMITED TO THE IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE, OR NON-INFRINGEMENT. SRI International SHALL NOT BE
# LIABLE FOR ANY DAMAGES SUFFERED BY LICENSEE AS A RESULT OF USING, MODIFYING
# OR DISTRIBUTING THIS SOFTWARE OR ITS DERIVATIVES
#
###############################################################################

import logging
from threading import Thread, Condition
import time

import zmq

from ZmqPPWrapper import ZmqPPWrapperType, ZmqPPEncoderFor


class ZmqPublisher:
    """
    ZeroMQ message publisher.
    NOTE: this class is not thread-safe (see http://api.zeromq.org/2-1:zmq-socket).
    """

    CONNECT_DELAY = 1.0 # time to wait after connect/bind (in seconds)

    def __init__(self,
                 context,
                 socketAddr,
                 topic='',
                 zmqEncoderType: ZmqPPWrapperType = ZmqPPWrapperType.BYTES,
                 invertConnection=False,
                 high_water_mark=None):
        """
        Args:

            context (Optional): ZeroMQ Context object. If 'None', a
                new context is created.

            socketAddr: ZeroMQ socket address (endpoint) string.

            topic[str] (Optional): default topic on which messages
                are published.

            zmqEncoderType (Option): encoder type; default:
                ZmqPPWrapperType.BYTES.

            invertConnection (Optional): invert typical ZeroMQ pub/sub
                pattern by make subscribers bind to a socket and
                publishers connect to it.  This is useful when
                publishers are less stable than subscribers.

            high_water_mark[int] (Optional): max number of messages
                that can be queued on this publisher.
        """
        self.__logger = logging.getLogger(__name__)
        self.__logger.info("Starting ZmqPublisher")
        self.__logger.info("\tSocket address: %s" % socketAddr)
        self.__logger.info("\tTopic: %s" % topic)

        if context is None:
            self.__logger.debug("Creating new ZeroMQ context")
            context = zmq.Context()

        self.socket = context.socket(zmq.PUB)  # @UndefinedVariable

        if high_water_mark:
            self.socket.set_hwm(high_water_mark)

        # TODO: think about the send high-water mark # @UndefinedVariable
        self.socket.setsockopt(zmq.LINGER, 0)  # @UndefinedVariable

        # In a typical ZMQ pub/sub pattern, the publisher binds to socket and
        # the subscriber connects to it.  However, in a situation where publisher
        # applications are less stable than the subscribers, it is useful to be
        # able to invert the pattern.
        if invertConnection is False:
            self.__logger.debug("Binding to socket: %s" % socketAddr)
            self.socket.bind(socketAddr)
        else:
            self.__logger.debug("Connecting to socket: %s" % socketAddr)
            self.socket.connect(socketAddr)

        self.zmqType    = zmqEncoderType
        self.zmqEncoder = ZmqPPEncoderFor (zmqEncoderType)

        # wait for socket bind/connect to complete
        time.sleep(self.CONNECT_DELAY)

        self.topic = self._convert_to_bytes (topic)

        self._zmq_queue = list ()       # Tuples: (<topic>, b<string JSON object>)
        self._zmq_qlock = Condition ()

    def _convert_to_bytes (self, arg):
        return arg if isinstance (arg, bytes) else bytes (arg, 'utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.terminate()

    def terminate(self):
        """
        Terminate the publisher.  publishMsg() should not be invoked
        after terminate() is called.
        """
        self.__logger.info("Cleaning up ZmqPublisher resources")
        # close the publisher socket. This will interrupt blocking receive
        if self.socket and not self.socket.closed:
            self.socket.close()
            self.socket = None

    def queue_message (self, msg, topic=None):
        """
        Queue message for asynchronous publication.
        Args:
            msg: outgoing message of type zmqEncoderType.
            topic[bytes or str] (Optional): message-specific topic
        """
        if self.socket:
            with self._zmq_qlock:
                self._zmq_queue.append ((topic, msg))
                self._zmq_qlock.notify ()

    def run (self, threadName=None):
        """
        Run a daemon thread that provisionally publishes queued messages.
        Arg:
            threadName[str] (Optional): thread name
        """
        if self.socket:

            def _zmq_publish ():
                while self.socket:
                    with self._zmq_qlock:
                        self._zmq_qlock.wait ()
                        while self._zmq_queue:
                            _topic, _msg = self._zmq_queue.pop (0)
                            self.publishMsg (_msg, _topic)

            _thread = Thread (target = _zmq_publish,
                              name   = threadName if threadName else 'ZMQ Msg Publication',
                              args   = (),
                              daemon = True)
            _thread.start ()

    def publishMsg (self, msg, topic=None):
        """
        Publish a single message on this publisher's topic.
        Args:
            msg: outgoing message of type zmqEncoderType.
            topic[bytes or str] (Optional): message-specific topic
        """
        if self.socket:
            self.socket.send_multipart ([self._convert_to_bytes (topic) if topic else self.topic, self.zmqEncoder (msg)])
